"""Acceso a datos de ERPNext.

- ERPNextClient: API REST real (token key:secret). Fuente principal:
  /api/method/monthly_subscription_snapshot?desde=AAAA-MM-DD&corte=AAAA-MM-DD
- FixtureClient: lee JSON locales con la misma forma que la API (solo para pruebas).
"""
from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from .config import settings

log = logging.getLogger("portal.erpnext")


class ERPNextError(Exception):
    """Error con mensaje apto para mostrar al usuario (sin trazas ni rutas internas)."""

    def __init__(self, user_message: str, detail: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail or user_message


def _frappe_error_text(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text[:500]
    if isinstance(data, dict):
        if data.get("_server_messages"):
            try:
                msgs = json.loads(data["_server_messages"])
                return " ".join(json.loads(m).get("message", "") if m.startswith("{") else m for m in msgs)
            except (ValueError, TypeError, AttributeError):
                return str(data["_server_messages"])[:500]
        if data.get("exception"):
            return str(data["exception"])[:500]
        if data.get("message"):
            return str(data["message"])[:500]
    return str(data)[:500]


class ERPNextClient:
    def __init__(self) -> None:
        if not settings.ERPNEXT_API_KEY or not settings.ERPNEXT_API_SECRET:
            raise ERPNextError(
                "El portal no tiene credenciales configuradas para consultar ERPNext.",
                "Faltan ERPNEXT_API_KEY / ERPNEXT_API_SECRET en backend/.env",
            )
        self.http = httpx.Client(
            base_url=settings.ERPNEXT_URL,
            headers={
                "Authorization": f"token {settings.ERPNEXT_API_KEY}:{settings.ERPNEXT_API_SECRET}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(settings.ERPNEXT_TIMEOUT, connect=20),
        )

    def close(self) -> None:
        self.http.close()

    # -- HTTP -----------------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, data: dict[str, Any]) -> Any:
        return self._request("POST", path, data=data)

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None,
                 data: dict[str, Any] | None = None) -> Any:
        try:
            resp = self.http.request(method, path, params=params, data=data)
        except httpx.TimeoutException as exc:
            raise ERPNextError("ERPNext tardó demasiado en responder. Intenta de nuevo en unos minutos.", repr(exc))
        except httpx.HTTPError as exc:
            raise ERPNextError("No fue posible conectarse con ERPNext.", repr(exc))
        if resp.status_code in (401, 403):
            raise ERPNextError(
                "ERPNext rechazó la consulta (credenciales o permisos insuficientes).",
                f"{resp.status_code} {path}: {_frappe_error_text(resp)}",
            )
        if resp.status_code >= 400:
            raise ERPNextError(
                "ERPNext devolvió un error al consultar la información.",
                f"{resp.status_code} {path}: {_frappe_error_text(resp)}",
            )
        try:
            return resp.json()
        except ValueError as exc:
            raise ERPNextError("ERPNext devolvió una respuesta inválida.", f"{path}: {resp.text[:300]}") from exc

    def _get_list(self, doctype: str, **params: Any) -> list[dict[str, Any]]:
        q: dict[str, Any] = {}
        for key, value in params.items():
            q[key] = json.dumps(value) if isinstance(value, (list, dict)) else value
        q.setdefault("limit_page_length", 0)
        data = self._get(f"/api/resource/{doctype}", q)
        return data.get("data", []) if isinstance(data, dict) else []

    # -- Fuentes --------------------------------------------------------------
    def logged_user(self) -> str:
        return self._get("/api/method/frappe.auth.get_logged_user").get("message", "")

    def user_roles(self, email: str) -> tuple[bool, list[str]]:
        """(habilitado, roles) del usuario en ERPNext. Si el usuario no existe → (False, [])."""
        try:
            resp = self.http.get(f"/api/resource/User/{quote(email, safe='@')}")
        except httpx.HTTPError as exc:
            raise ERPNextError("No fue posible verificar tu rol en ERPNext. Intenta de nuevo.", repr(exc))
        if resp.status_code == 404:
            return False, []
        if resp.status_code >= 400:
            raise ERPNextError("No fue posible verificar tu rol en ERPNext. Intenta de nuevo.",
                               f"{resp.status_code} User: {_frappe_error_text(resp)}")
        doc = (resp.json() or {}).get("data") or {}
        roles = [r.get("role") for r in doc.get("roles") or [] if isinstance(r, dict) and r.get("role")]
        return bool(doc.get("enabled")), roles

    def snapshot(self, desde: date, corte: date) -> dict[str, Any]:
        data = self._get(
            f"/api/method/{settings.SNAPSHOT_METHOD}",
            {"desde": desde.isoformat(), "corte": corte.isoformat(), "company": settings.ERPNEXT_COMPANY},
        )
        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, dict) or "data" not in message:
            raise ERPNextError("La API de suscripciones devolvió un formato inesperado.", str(data)[:300])
        return message

    def subscription_plans(self) -> list[dict[str, Any]]:
        return self._get_list(
            "Subscription Plan",
            fields=["name", "item", "cost", "custom_internet", "custom_television", "custom_download",
                    "custom_upload", "custom_include_tv_free", "custom_extrato", "custom_setbox", "custom_aquiler"],
        )

    def _sales_filters(self, start: date, end: date) -> list[list[Any]]:
        return [
            ["Sales Invoice", "docstatus", "=", 1],
            ["Sales Invoice", "company", "=", settings.ERPNEXT_COMPANY],
            ["Sales Invoice", "posting_date", "between", [start.isoformat(), end.isoformat()]],
        ]

    def revenue_by_item(self, start: date, end: date, customers: list[str] | None = None) -> list[dict[str, Any]]:
        """Suma de net_amount (sin impuestos, neto de descuentos y notas crédito) por ítem facturado."""
        filters = self._sales_filters(start, end)
        if customers is not None:
            if not customers:
                return []
            filters.append(["Sales Invoice", "customer", "in", customers])
        item_col = "`tabSales Invoice Item`.`item_code`"
        # /api/resource ignora group_by en esta versión de Frappe (devuelve una sola fila);
        # frappe.desk.reportview.get sí agrupa.
        try:
            data = self._post("/api/method/frappe.desk.reportview.get", {
                "doctype": "Sales Invoice",
                "fields": json.dumps([f"{item_col} as item_code", "sum(`tabSales Invoice Item`.`net_amount`) as net"]),
                "filters": json.dumps(filters),
                "group_by": item_col,
                "page_length": 0,
            })
            msg = data.get("message") if isinstance(data, dict) else None
            if isinstance(msg, dict) and "keys" in msg:
                rows = [dict(zip(msg["keys"], values)) for values in msg.get("values", [])]
            else:
                rows = msg or []
            return [{"item_code": r.get("item_code"), "net": float(r.get("net") or 0)} for r in rows]
        except ERPNextError as exc:
            log.warning("Agregación de ingresos no disponible, se usa paginación: %s", exc.detail)
        totals: dict[str, float] = defaultdict(float)
        start_at, page = 0, 5000
        while True:
            rows = self._get_list(
                "Sales Invoice",
                fields=[f"{item_col} as item_code", "`tabSales Invoice Item`.`net_amount` as net"],
                filters=filters,
                limit_start=start_at,
                limit_page_length=page,
            )
            for r in rows:
                totals[r.get("item_code") or ""] += float(r.get("net") or 0)
            if len(rows) < page:
                break
            start_at += page
        return [{"item_code": k, "net": v} for k, v in totals.items()]

    def issues(self, start: date, end: date) -> list[dict[str, Any]]:
        return self._get_list(
            "Issue",
            fields=["name", "issue_type", "status", "opening_date", "custom_interrupcion_culpa", "custom_subscription"],
            filters=[["opening_date", "between", [start.isoformat(), end.isoformat()]]],
        )

    # -- Historial (tabVersion) para reconstruir cada suscripción al día de corte --------
    def subscription_versions(self, start: datetime, stop: datetime, likes: list[str]) -> list[dict[str, Any]]:
        """Versiones de Subscription con modified en [start, stop) cuyo data contiene alguno de `likes`."""
        return self._get_list(
            "Version",
            fields=["name", "docname", "modified", "data"],
            filters=[["ref_doctype", "=", "Subscription"],
                     ["modified", ">=", start.strftime("%Y-%m-%d %H:%M:%S")],
                     ["modified", "<", stop.strftime("%Y-%m-%d %H:%M:%S")]],
            or_filters=[["data", "like", like] for like in likes],
            order_by="modified asc",
        )

    def last_status_before(self, docnames: list[str], before: str) -> dict[str, str]:
        """Último estado registrado (valor nuevo) antes de `before` para cada suscripción."""
        out: dict[str, str] = {}
        for i in range(0, len(docnames), 100):
            chunk = self._get_list(
                "Version",
                fields=["docname", "modified", "data"],
                filters=[["ref_doctype", "=", "Subscription"], ["docname", "in", docnames[i:i + 100]],
                         ["modified", "<", before], ["data", "like", '%["status","%']],
                order_by="modified desc",
            )
            for v in chunk:
                if v["docname"] in out:
                    continue
                for field, _old, new in json.loads(v.get("data") or "{}").get("changed", []):
                    if field == "status" and new:
                        out[v["docname"]] = new
                        break
        return out

    def disabled_tv_subscriptions(self) -> set[str]:
        rows = self._get_list(
            "Subscription", fields=["name"],
            filters=[["company", "=", settings.ERPNEXT_COMPANY], ["custom_disabled_tv", "=", 1]],
        )
        return {r["name"] for r in rows}


# ---------------------------------------------------------------------------
# Fixture (pruebas locales): replica la lógica del Server Script "API Monthly Subscription Snapshot".
# ---------------------------------------------------------------------------
_DANE_SCRIPT = {"Bogotá": 11001, "Bogota": 11001, "Soacha": 25754, "Tenjo": 25799, "Chía": 25175, "Chia": 25175}
_INTERNET_WORDS = ("Mbps", "Gbps", "Gb ", "Internet", "Corporativo", "ISP")


def _velocidad_kbps(texto: str | None) -> int | None:
    if not texto:
        return None
    t = texto.replace(",", ".")
    for unidad, factor in (("Gbps", 1000000), ("Mbps", 1000), ("Gb", 1000000)):
        pos = t.find(unidad)
        while pos != -1:
            i = pos
            while i > 0 and t[i - 1] == " ":
                i -= 1
            j = i
            while j > 0 and (t[j - 1].isdigit() or t[j - 1] == "."):
                j -= 1
            num = t[j:i]
            if num:
                try:
                    return int(float(num) * factor)
                except ValueError:
                    pass
            pos = t.find(unidad, pos + 1)
    return None


class FixtureClient:
    _cache: dict[str, Any] = {}
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.dir = Path(settings.FIXTURE_DIR)
        if not (self.dir / "subscriptions_raw.json").exists():
            raise ERPNextError("No hay datos de prueba (fixtures) configurados en FIXTURE_DIR.")

    def close(self) -> None:
        pass

    def _load(self, name: str) -> Any:
        with self._lock:
            if name not in self._cache:
                with open(self.dir / name, encoding="utf-8") as fh:
                    self._cache[name] = json.load(fh)
            return self._cache[name]

    def logged_user(self) -> str:
        return "fixture@local"

    def user_roles(self, email: str) -> tuple[bool, list[str]]:
        # Pruebas locales sin ERPNext: roles definidos en FIXTURE_USER_ROLES.
        return True, list(settings.FIXTURE_USER_ROLES)

    def snapshot(self, desde: date, corte: date) -> dict[str, Any]:
        raw = self._load("subscriptions_raw.json")
        changes = self._load("status_changes.json")
        corte_s, desde_s = corte.isoformat(), desde.isoformat()
        limite = (corte + timedelta(days=1)).isoformat()
        first: dict[str, dict[str, Any]] = {}
        for c in changes:
            if c["modified"] >= limite:
                prev = first.get(c["subscription"])
                if prev is None or c["modified"] < prev["modified"]:
                    first[c["subscription"]] = c
        anno, mes = corte.year, corte.month
        trimestre = (mes - 1) // 3 + 1
        mes_trim = mes - 3 * (trimestre - 1)
        rows: list[dict[str, Any]] = []
        resumen: dict[str, int] = defaultdict(int)
        for base in raw:
            if base["creation"] > corte_s:
                continue
            if base["status_actual"] == "Cancelled" and base.get("cancelation_date") and base["cancelation_date"] < desde_s:
                continue
            r = dict(base)
            r["fecha_corte"] = corte_s
            cambio = first.get(r["subscription"])
            if cambio and cambio.get("status_anterior"):
                r["status_al_corte"] = cambio["status_anterior"]
                r["fuente_status"] = "tabVersion"
                r["primer_cambio_posterior"] = cambio["modified"]
            else:
                r["status_al_corte"] = r["status_actual"]
                r["fuente_status"] = "actual"
                r["primer_cambio_posterior"] = None
            planes = [p for p in (r.get("planes_todos") or "").split(" | ") if p]
            r["planes_otros"] = " | ".join(
                p for p in planes if not any(w in p for w in _INTERNET_WORDS) and "Giga Fibra TV" not in p
            ) or None
            r.update({
                "anno": anno, "trimestre": trimestre, "mes_del_trimestre": mes_trim,
                "codigo_dane_municipio": _DANE_SCRIPT.get(r.get("ciudad")),
                "codigo_dane_centro_poblado": 0, "nombre_centro_poblado": "0",
            })
            planes_tv = r.get("planes_tv") or ""
            r["tiene_tv"] = bool(planes_tv)
            r["tiene_tv_pago"] = bool(planes_tv) and "Free" not in planes_tv
            r["tiene_internet"] = bool(r.get("planes_internet"))
            r["velocidad_bajada_kbps"] = _velocidad_kbps(r.get("planes_internet"))
            r["tecnologia_internet"] = 4 if r["tiene_internet"] else None
            r["tecnologia_tv"] = 5 if r["tiene_tv"] else None
            r["es_corporativo"] = r.get("segmento") == 7
            r["habilitada"] = r["status_al_corte"] in ("Active", "Past Due Date")
            resumen[r["status_al_corte"]] += 1
            rows.append(r)
        return {"corte": corte_s, "anno": anno, "trimestre": trimestre, "mes_del_trimestre": mes_trim,
                "total": len(rows), "resumen_estado": dict(resumen), "data": rows}

    def subscription_plans(self) -> list[dict[str, Any]]:
        return self._load("subscription_plans.json")

    def revenue_by_item(self, start: date, end: date, customers: list[str] | None = None) -> list[dict[str, Any]]:
        data = self._load("revenue.json")
        key = f"{start.isoformat()}_{end.isoformat()}"
        if customers is not None:
            if not customers:
                return []
            rows = data.get(f"isp:{key}")
            if rows is None:
                raise ERPNextError("No hay datos de ingresos de prueba para este periodo.")
            wanted = set(customers)
            totals: dict[str, float] = defaultdict(float)
            for r in rows:
                if r["customer"] in wanted:
                    totals[r["item_code"]] += float(r["net"])
            return [{"item_code": k, "net": v} for k, v in totals.items()]
        if key not in data:
            raise ERPNextError("No hay datos de ingresos de prueba para este periodo.")
        return data[key]

    def issues(self, start: date, end: date) -> list[dict[str, Any]]:
        s, e = start.isoformat(), end.isoformat()
        return [i for i in self._load("issues.json") if s <= (i.get("opening_date") or "") <= e]

    # Los fixtures no incluyen tabVersion: no se aplica reconstrucción al corte.
    def subscription_versions(self, start: datetime, stop: datetime, likes: list[str]) -> list[dict[str, Any]]:
        return []

    def last_status_before(self, docnames: list[str], before: str) -> dict[str, str]:
        return {}

    def disabled_tv_subscriptions(self) -> set[str]:
        return set()


def get_client() -> ERPNextClient | FixtureClient:
    if settings.DATA_SOURCE == "fixture":
        return FixtureClient()
    return ERPNextClient()
