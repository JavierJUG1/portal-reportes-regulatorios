"""Reconstrucción de cada suscripción tal como estaba el último día del corte.

La API monthly_subscription_snapshot entrega el estado al corte (reconstruido desde tabVersion), pero los
demás datos (planes, estrato, ciudad, coordenadas, TV deshabilitada) son los ACTUALES. Aquí se deshacen,
del más reciente al más antiguo, los cambios registrados en tabVersion después del corte:

- planes agregados / quitados / cambiados en la tabla "plans";
- campos custom_estrato, custom_cliente_b2b, custom_ciudad_l, custom_latitude, custom_longitude,
  custom_disabled_tv (vale el "antes" del primer cambio posterior al corte);
- estado: cuando el primer cambio posterior al corte tiene el estado anterior vacío ("" → X), la API usa el
  estado actual; en ese caso se toma el último estado registrado antes del corte.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any

from . import periods
from .classify import PlanCatalog, split_plans
from .config import settings
from .erpnext import ERPNextError

log = logging.getLogger("portal.al_corte")


def _is_timeout(exc: ERPNextError) -> bool:
    """504 del proxy de ERPNext o tiempo de espera agotado (ventana con demasiadas versiones)."""
    return exc.detail.startswith("504 ") or "Timeout" in exc.detail or "tardó demasiado" in exc.user_message

FIELD_MAP = {
    "custom_estrato": "estrato",
    "custom_cliente_b2b": "cliente_b2b",
    "custom_ciudad_l": "ciudad",
    "custom_latitude": "latitude",
    "custom_longitude": "longitude",
    "custom_disabled_tv": "tv_deshabilitada",
}
LIKES = ['%["plans",%', '%["status","",%'] + [f'%["{f}",%' for f in FIELD_MAP]


def limite(corte: date) -> str:
    """Primer instante posterior al corte (los cambios desde aquí no aplican al corte)."""
    return f"{(corte + timedelta(days=1)).isoformat()} 00:00:00"


GRID_START = datetime(2020, 1, 6)  # lunes: las semanas consultadas siempre caen en la misma grilla
CACHE_DIR = settings.DB_PATH.parent / "version_cache" / hashlib.sha1("|".join(LIKES).encode()).hexdigest()[:10]
WORKERS = 3


def _week_start(dt: datetime) -> datetime:
    return GRID_START + timedelta(days=((dt - GRID_START).days // 7) * 7)


def load_events(client: Any, since: str) -> dict[str, list[dict[str, Any]]]:
    """Eventos de tabVersion desde `since`, por semanas en paralelo.

    Las versiones de ERPNext no se modifican después de creadas, así que cada semana ya terminada se guarda
    en data/version_cache y no se vuelve a consultar.
    """
    start = datetime.fromisoformat(since)
    now = periods.now().replace(tzinfo=None)
    weeks = []
    w = _week_start(start)
    while w <= now:
        weeks.append(w)
        w += timedelta(days=7)

    def _versions(start_w: datetime, stop_w: datetime) -> list[dict[str, Any]]:
        """Una ventana de tabVersion; si ERPNext se demora (504/timeout), la parte en mitades hasta 1 hora."""
        try:
            return client.subscription_versions(start_w, stop_w, LIKES)
        except ERPNextError as exc:
            if stop_w - start_w <= timedelta(hours=1) or not _is_timeout(exc):
                raise
            mid = start_w + (stop_w - start_w) / 2
            log.info("tabVersion %s–%s tardó demasiado; se consulta en dos partes", start_w, stop_w)
            return _versions(start_w, mid) + _versions(mid, stop_w)

    def fetch(week: datetime) -> list[dict[str, Any]]:
        stop = week + timedelta(days=7)
        cache = CACHE_DIR / f"{week:%Y%m%d}.json"
        if cache.exists():
            with open(cache, encoding="utf-8") as fh:
                return json.load(fh)
        evs = [e for e in (parse_version(v) for v in _versions(week, stop)) if e]
        if stop < now - timedelta(hours=1):
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps(evs, ensure_ascii=False), encoding="utf-8")
            tmp.replace(cache)
        return evs

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        chunks = list(pool.map(fetch, weeks))
    by_sub: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for evs in chunks:
        for ev in evs:
            if ev["m"] >= since:
                by_sub[ev["s"]].append(ev)
    for evs in by_sub.values():
        evs.sort(key=lambda e: (e["m"], e["id"]), reverse=True)  # más reciente primero
    return by_sub


def parse_version(v: dict[str, Any]) -> dict[str, Any] | None:
    """Extrae de una versión los cambios que importan para el corte (o None si no hay ninguno)."""
    try:
        data = json.loads(v.get("data") or "{}")
    except ValueError:
        return None
    ev: dict[str, Any] = {"s": v["docname"], "m": str(v["modified"])[:19], "id": str(v.get("name", "")),
                          "add": [], "rem": [], "chg": [], "fields": {}, "status_vacio": False}
    for field, row in data.get("added", []) or []:
        if field == "plans" and isinstance(row, dict):
            ev["add"].append(row.get("plan"))
    for field, row in data.get("removed", []) or []:
        if field == "plans" and isinstance(row, dict):
            ev["rem"].append(row.get("plan"))
    for rc in data.get("row_changed", []) or []:
        if rc and rc[0] == "plans" and len(rc) > 3:
            for f, old, new in rc[3]:
                if f == "plan":
                    ev["chg"].append([old, new])
    for f, old, new in data.get("changed", []) or []:
        if f in FIELD_MAP:
            ev["fields"][f] = old
        elif f == "status" and old == "":
            ev["status_vacio"] = True
    if ev["add"] or ev["rem"] or ev["chg"] or ev["fields"] or ev["status_vacio"]:
        return ev
    return None


def _segmento(estrato: Any, b2b: Any) -> int:
    """Misma regla del Server Script: B2B o estrato 7 → 7; estrato 1–6; si no, 8."""
    est = str(estrato or "").strip()
    if str(b2b or "0") in ("1", "True", "true") or est == "7":
        return 7
    return int(est) if est in ("1", "2", "3", "4", "5", "6") else 8


def ajustar(rows: list[dict[str, Any]], corte: date, events: dict[str, list[dict[str, Any]]],
            disabled_now: set[str], catalog: PlanCatalog, client: Any) -> dict[str, int]:
    """Modifica `rows` (snapshot de la API) para dejar cada suscripción como estaba al corte."""
    lim = limite(corte)
    stats: Counter[str] = Counter()
    fix_status: list[dict[str, Any]] = []
    for r in rows:
        sub = r.get("subscription")
        plans = set(split_plans(r.get("planes_todos")))
        original = set(plans)
        vals: dict[str, Any] = {}
        status_vacio = False
        for ev in events.get(sub, []):
            if ev["m"] < lim:
                break
            for p in ev["add"]:
                plans.discard(p)
            for p in ev["rem"]:
                if p:
                    plans.add(p)
            for old, new in ev["chg"]:
                plans.discard(new)
                if old:
                    plans.add(old)
            vals.update(ev["fields"])  # termina con el "antes" del primer cambio posterior al corte
            status_vacio = status_vacio or ev["status_vacio"]

        if plans != original:
            r["planes_todos"] = " | ".join(sorted(plans)) or None
            r["planes_tv"] = " | ".join(sorted(p for p in plans if "Giga Fibra TV" in p)) or None
            r["precio_planes"] = sum(catalog.get(p).cost for p in plans)
            r["planes_corregidos_al_corte"] = True
            stats["planes"] += 1
        tv_off = vals.pop("custom_disabled_tv", 1 if sub in disabled_now else 0)
        r["tv_deshabilitada"] = str(tv_off) in ("1", "True", "true")
        for field, old in vals.items():
            key = FIELD_MAP[field]
            if r.get(key) != old:
                r[key] = old
                stats[key] += 1
        if "custom_estrato" in vals or "custom_cliente_b2b" in vals:
            r["segmento"] = _segmento(r.get("estrato"), r.get("cliente_b2b"))
        if status_vacio and r.get("fuente_status") == "actual":
            fix_status.append(r)

    if fix_status:
        before = client.last_status_before([r["subscription"] for r in fix_status], lim)
        for r in fix_status:
            st = before.get(r["subscription"])
            if st and st != r.get("status_al_corte"):
                r["status_al_corte"] = st
                r["fuente_status"] = "tabVersion (cadena)"
                r["habilitada"] = st in ("Active", "Past Due Date")
                stats["estado"] += 1
    stats["tv_deshabilitada_al_corte"] = sum(1 for r in rows if r.get("tv_deshabilitada") and r.get("planes_tv"))
    log.info("Ajustes al corte %s: %s", corte, dict(stats))
    return dict(stats)
