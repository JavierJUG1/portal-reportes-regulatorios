"""Permisos del portal.

Todos los usuarios con sesión consultan y descargan. Solo los usuarios de ERPNext con uno de los roles de
GENERATE_ROLES (por defecto "System Manager") pueden generar reportes: nuevas versiones, periodos sin
archivo y reintentos. Las generaciones automáticas del calendario no pasan por aquí (las hace el sistema).

El rol se consulta en ERPNext (no se confía en la cookie de sesión) y se recuerda ROLE_CACHE_SECONDS,
así quitar o dar el rol en ERPNext se refleja en el portal en pocos minutos.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from fastapi import HTTPException

from .config import settings
from .erpnext import ERPNextError, get_client

log = logging.getLogger("portal.permissions")

_cache: dict[str, tuple[float, bool, list[str]]] = {}
_lock = threading.Lock()


def _roles_label() -> str:
    roles = settings.GENERATE_ROLES
    return roles[0] if len(roles) == 1 else ", ".join(roles[:-1]) + f" o {roles[-1]}"


def denied_message() -> str:
    return f"Solo los usuarios con el rol {_roles_label()} en ERPNext pueden generar reportes."


def erpnext_roles(email: str) -> tuple[bool, list[str]]:
    """(habilitado, roles) del usuario en ERPNext, con caché. Lanza ERPNextError si ERPNext no responde."""
    email = email.strip().lower()
    now = time.monotonic()
    with _lock:
        hit = _cache.get(email)
        if hit and now - hit[0] < settings.ROLE_CACHE_SECONDS:
            return hit[1], hit[2]
    client = get_client()
    try:
        enabled, roles = client.user_roles(email)
    finally:
        client.close()
    with _lock:
        _cache[email] = (now, enabled, roles)
    return enabled, roles


def generation_access(user: dict[str, Any]) -> tuple[bool, str | None]:
    """(puede generar, motivo si no puede). Si no se puede verificar en ERPNext, se niega."""
    if not settings.GENERATE_ROLES:
        return True, None
    try:
        enabled, roles = erpnext_roles(user["email"])
    except ERPNextError as exc:
        log.warning("No se pudo verificar el rol de %s: %s", user.get("email"), exc.detail)
        return False, exc.user_message
    if not enabled:
        return False, "Tu usuario no está habilitado en ERPNext."
    if not set(settings.GENERATE_ROLES) & set(roles):
        return False, denied_message()
    return True, None


def require_generator(user: dict[str, Any]) -> None:
    allowed, reason = generation_access(user)
    if not allowed:
        log.info("Generación denegada a %s: %s", user.get("email"), reason)
        raise HTTPException(status_code=403, detail=reason or denied_message())
