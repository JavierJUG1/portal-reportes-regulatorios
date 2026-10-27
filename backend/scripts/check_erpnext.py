"""Prueba la conexión con ERPNext usando la configuración de backend/.env.

Uso (desde backend/):
    .venv/Scripts/python -m scripts.check_erpnext

Verifica, sin generar ni guardar nada:
  1. Credenciales (ERPNEXT_API_KEY / ERPNEXT_API_SECRET) y usuario autenticado.
  2. Endpoint monthly_subscription_snapshot con desde/corte del último mes cerrado.
  3. Lectura de Subscription Plan (clasificación de planes de F6, T1.2 y cortes).
  4. Lectura de User (roles: solo System Manager genera reportes desde el portal).
"""
from __future__ import annotations

import sys
import time

from app.config import settings
from app.erpnext import ERPNextClient, ERPNextError
from app.periods import current_period


def _check(label: str, fn) -> bool:
    started = time.monotonic()
    try:
        detail = fn()
    except ERPNextError as exc:
        print(f"  ✗ {label}: {exc.user_message}\n      {exc.detail}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ {label}: {exc!r}")
        return False
    print(f"  ✓ {label} ({time.monotonic() - started:.1f}s) {detail}")
    return True


def main() -> int:
    print(f"ERPNext: {settings.ERPNEXT_URL}  ·  método: {settings.SNAPSHOT_METHOD}  ·  empresa: {settings.ERPNEXT_COMPANY}")
    if not settings.ERPNEXT_API_KEY or not settings.ERPNEXT_API_SECRET:
        print("  ✗ Falta ERPNEXT_API_KEY o ERPNEXT_API_SECRET en backend/.env")
        return 1
    client = ERPNextClient()
    month = current_period("month").prev()
    user = {"email": ""}

    def auth() -> str:
        user["email"] = client.logged_user()
        return f"→ usuario {user['email']}"

    def roles() -> str:
        enabled, found = client.user_roles(user["email"])
        allowed = [r for r in settings.GENERATE_ROLES if r in found]
        return f"→ habilitado={enabled}, roles de generación: {', '.join(allowed) or 'ninguno'}"

    results = [
        _check("Autenticación", auth),
        _check(
            f"Snapshot {month.label} (desde={month.start}, corte={month.end})",
            lambda: (lambda s: f"→ {s['total']} suscripciones, estados {s.get('resumen_estado')}")(
                client.snapshot(month.start, month.end)
            ),
        ),
        _check("Subscription Plan", lambda: f"→ {len(client.subscription_plans())} planes"),
        _check("User (roles)", roles),
    ]
    client.close()
    ok = all(results)
    print("Conexión lista: el portal puede generar F6, T1.2 y cortes." if ok else "Hay pruebas con error (ver arriba).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
