"""Crea o actualiza en ERPNext el OAuth Client del portal y guarda sus datos en backend/.env.

Usa las credenciales de API de backend/.env (ERPNEXT_URL, ERPNEXT_API_KEY, ERPNEXT_API_SECRET); el usuario
de API necesita permiso para crear y modificar *OAuth Client* (p. ej. System Manager).

Uso (desde backend/; también se puede ejecutar el archivo directamente desde cualquier carpeta):
    # Ver qué haría, sin cambiar nada
    .venv/Scripts/python -m scripts.configurar_oauth --simular

    # Crear/actualizar el OAuth Client con la URL de regreso de backend/.env y la del servidor
    .venv/Scripts/python -m scripts.configurar_oauth \\
        --redirect http://10.20.67.35/portal_reportes_crc/api/auth/callback

Qué hace (se puede ejecutar varias veces; no duplica nada):
  1. Busca el OAuth Client por nombre de aplicación ("Portal reportes regulatorios").
  2. Si no existe lo crea: Skip Authorization, Authorization Code, Code, scopes "openid all" y las URLs de
     regreso (OAUTH_REDIRECT_URI de backend/.env más las de --redirect). Si existe, agrega las URLs que falten
     y corrige esos campos, sin quitar las URLs que ya tenga.
  3. Escribe OAUTH_CLIENT_ID y OAUTH_CLIENT_SECRET en backend/.env (con --sin-env no toca el archivo).
     El secret nunca se muestra completo.

Después hay que reiniciar el portal para que tome el nuevo backend/.env.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

# Se puede ejecutar como módulo (desde backend/) o como archivo desde cualquier carpeta (botón "Run" de VS Code).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BASE_DIR, settings  # noqa: E402

DOCTYPE = "OAuth Client"
APP_NAME = "Portal reportes regulatorios"
FIELDS = {
    "skip_authorization": 1,  # entra directo si ya hay sesión en ERPNext
    "grant_type": "Authorization Code",
    "response_type": "Code",
    "scopes": "openid all",
}
ENV_PATH = BASE_DIR / ".env"


class ConfigError(Exception):
    pass


def _mask(value: str | None) -> str:
    if not value:
        return "(vacío)"
    return value[:4] + "…" + f" ({len(value)} caracteres)"


def _client() -> httpx.Client:
    if not settings.ERPNEXT_API_KEY or not settings.ERPNEXT_API_SECRET:
        raise ConfigError("Faltan ERPNEXT_API_KEY / ERPNEXT_API_SECRET en backend/.env.")
    return httpx.Client(
        base_url=settings.ERPNEXT_URL,
        headers={"Authorization": f"token {settings.ERPNEXT_API_KEY}:{settings.ERPNEXT_API_SECRET}",
                 "Accept": "application/json"},
        timeout=30,
    )


def _check(resp: httpx.Response, action: str) -> Any:
    if resp.status_code in (401, 403):
        raise ConfigError(f"ERPNext no permitió {action}: el usuario de API necesita permiso sobre OAuth Client "
                          f"(HTTP {resp.status_code}).")
    if resp.status_code >= 400:
        detail = resp.text[:300].replace("\n", " ")
        raise ConfigError(f"ERPNext devolvió un error al {action} (HTTP {resp.status_code}): {detail}")
    return resp.json().get("data")


def _resource(name: str | None = None) -> str:
    path = f"/api/resource/{quote(DOCTYPE)}"
    return f"{path}/{quote(name)}" if name else path


def find_client(http: httpx.Client, app_name: str) -> dict[str, Any] | None:
    rows = _check(http.get(_resource(), params={
        "filters": json.dumps([["app_name", "=", app_name]]),
        "fields": json.dumps(["name"]),
        "limit_page_length": 0,
    }), "buscar el OAuth Client") or []
    if len(rows) > 1:
        raise ConfigError(f"Hay {len(rows)} OAuth Client llamados '{app_name}' en ERPNext; deja solo uno.")
    if not rows:
        return None
    return _check(http.get(_resource(rows[0]["name"])), "leer el OAuth Client")


def _uris(text: str | None) -> list[str]:
    return [u for u in re.split(r"\s+", text or "") if u]


def plan_changes(current: dict[str, Any] | None, redirects: list[str], app_name: str) -> dict[str, Any]:
    """Campos a crear (si no existe) o a modificar (solo los que cambian)."""
    if current is None:
        return {"app_name": app_name, **FIELDS, "redirect_uris": " ".join(redirects),
                "default_redirect_uri": redirects[0]}
    changes: dict[str, Any] = {}
    for field, value in FIELDS.items():
        if str(current.get(field) or "") != str(value):
            changes[field] = value
    existing = _uris(current.get("redirect_uris"))
    merged = existing + [u for u in redirects if u not in existing]
    if merged != existing:
        changes["redirect_uris"] = " ".join(merged)
    if not current.get("default_redirect_uri") or current["default_redirect_uri"] not in merged:
        changes["default_redirect_uri"] = redirects[0]
    return changes


def write_env(client_id: str, client_secret: str, path: Path = ENV_PATH) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    for key, value in (("OAUTH_CLIENT_ID", client_id), ("OAUTH_CLIENT_SECRET", client_secret)):
        line = f"{key}={value}"
        if re.search(rf"^{key}=.*$", text, flags=re.M):
            text = re.sub(rf"^{key}=.*$", lambda _m, ln=line: ln, text, count=1, flags=re.M)
        else:
            text = text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    # Consolas de Windows sin UTF-8: los símbolos (✓, →) no rompen el script.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Crea o actualiza el OAuth Client del portal en ERPNext")
    parser.add_argument("--redirect", action="append", default=[], metavar="URL",
                        help="URL de regreso adicional (se puede repetir); siempre se incluye OAUTH_REDIRECT_URI")
    parser.add_argument("--app-name", default=APP_NAME, help=f"nombre de la aplicación (por defecto '{APP_NAME}')")
    parser.add_argument("--simular", action="store_true", help="muestra lo que haría sin cambiar ERPNext ni .env")
    parser.add_argument("--sin-env", action="store_true", help="no escribe OAUTH_CLIENT_ID/SECRET en backend/.env")
    args = parser.parse_args()

    app_name = args.app_name
    redirects: list[str] = []
    for url in [settings.OAUTH_REDIRECT_URI, *args.redirect]:
        if url and url not in redirects:
            if not url.startswith(("http://", "https://")) or not url.endswith("/api/auth/callback"):
                print(f"✗ URL de regreso inválida: {url} (debe terminar en /api/auth/callback)")
                return 2
            redirects.append(url)

    print(f"ERPNext: {settings.ERPNEXT_URL}  ·  OAuth Client: '{app_name}'")
    print("URLs de regreso: " + ", ".join(redirects))
    try:
        with _client() as http:
            current = find_client(http, app_name)
            changes = plan_changes(current, redirects, app_name)
            if current is None:
                print("→ No existe: se crea con " + ", ".join(f"{k}={v}" for k, v in changes.items()
                                                             if k != "app_name"))
            elif changes:
                print(f"→ Existe ({current['name']}): se actualiza " + ", ".join(f"{k}={v}" for k, v in changes.items()))
            else:
                print(f"→ Existe ({current['name']}) y ya está bien configurado.")

            if args.simular:
                print("Simulación: no se cambió nada.")
                return 0

            if current is None:
                doc = _check(http.post(_resource(), json=changes), "crear el OAuth Client")
                print(f"✓ OAuth Client creado: {doc['name']}")
            elif changes:
                doc = _check(http.put(_resource(current["name"]), json=changes), "actualizar el OAuth Client")
                print("✓ OAuth Client actualizado")
            else:
                doc = current
    except (ConfigError, httpx.HTTPError) as exc:
        print(f"✗ {exc}")
        return 1

    client_id, client_secret = doc.get("client_id") or doc["name"], doc.get("client_secret") or ""
    print(f"  Client ID: {client_id}")
    print(f"  Client secret: {_mask(client_secret)}")
    print(f"  URLs de regreso en ERPNext: {doc.get('redirect_uris')}")
    if args.sin_env:
        print("No se modificó backend/.env (--sin-env).")
    else:
        write_env(client_id, client_secret)
        print(f"✓ OAUTH_CLIENT_ID y OAUTH_CLIENT_SECRET guardados en {ENV_PATH}")
    print("Siguiente paso: reiniciar el portal para que tome la configuración.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
