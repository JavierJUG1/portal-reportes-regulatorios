"""Foto mensual: respuesta de la API guardada al cierre de cada mes.

La API `monthly_subscription_snapshot` reconstruye al corte solo el estado de cada suscripción; los planes,
la dirección, el estrato y las coordenadas los entrega como están en el momento de la consulta. Por eso el
portal guarda ("congela") la respuesta del mes cuando lo consulta por primera vez después del cierre
—normalmente el último día del mes a las 23:50, con la generación automática del corte— junto con el
catálogo de planes de ese momento. Desde entonces el F6, el T1.2 y el corte de ese mes se arman con esa foto,
sin volver a consultar ERPNext: regenerarlos da los mismos datos aunque después cambien las suscripciones.

Cada foto queda en FOTOS_DIR/AAAA-MM.json.gz. Si se toma después del día de corte (servidor apagado al
cierre, o un mes antiguo generado por primera vez) se marca como "tardía": el estado sigue al corte, pero los
planes y la ubicación son los del día en que se tomó. Para volver a tomarla a propósito: scripts.fotos.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from .config import settings
from .periods import Period, fmt_datetime, now

log = logging.getLogger("portal.fotos")

FORMATO = 1
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def month_of(desde: date, corte: date) -> Period | None:
    """El mes calendario completo que cubre [desde, corte], o None si el rango no es un mes completo."""
    month = Period("month", desde.year, desde.month)
    return month if desde == month.start and corte == month.end else None


def path(month: Period) -> Path:
    return settings.FOTOS_DIR / f"{month.id}.json.gz"


def _lock(month: Period) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(month.id, threading.Lock())


def load(month: Period) -> dict[str, Any] | None:
    p = path(month)
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def info(foto: dict[str, Any]) -> dict[str, Any]:
    """Resumen de la foto (sin los datos), para estadísticas, el Excel y la consola."""
    tomada = datetime.fromisoformat(foto["tomada"])
    return {"periodo": foto["periodo"], "corte": foto["corte"], "tomada": foto["tomada"],
            "tomada_label": fmt_datetime(tomada), "tardia": foto["tardia"], "origen": foto["origen"],
            "suscripciones": int(foto["snapshot"].get("total") or len(foto["snapshot"].get("data") or [])),
            "planes": len(foto.get("planes") or [])}


def save(month: Period, snapshot: dict[str, Any], planes: list[dict[str, Any]], origen: str) -> dict[str, Any]:
    """Guarda la foto (escritura atómica). Si ya existía, la anterior se conserva como .anterior-<fecha>."""
    taken = now()
    foto = {
        "formato": FORMATO,
        "periodo": month.id,
        "desde": month.start.isoformat(),
        "corte": month.end.isoformat(),
        "tomada": taken.isoformat(),
        "tardia": taken.date() > month.end,
        "origen": origen,
        "snapshot": snapshot,
        "planes": planes,
    }
    p = path(month)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.replace(p.with_name(f"{month.id}.anterior-{taken:%Y%m%d-%H%M%S}.json.gz"))
    tmp = p.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(foto, fh, ensure_ascii=False)
    os.replace(tmp, p)
    log.info("Foto %s guardada (%s, %s suscripciones%s)", month.id, origen, foto["snapshot"].get("total"),
             ", tardía" if foto["tardia"] else "")
    return foto


def obtener(month: Period, consultar: Callable[[], tuple[dict[str, Any], list[dict[str, Any]]]],
            origen: str = "generacion") -> tuple[dict[str, Any], bool]:
    """Foto del mes: la guardada, o la consulta y la guarda si el mes ya cerró. Devuelve (foto, era_nueva).

    `consultar()` devuelve (respuesta del snapshot, catálogo de planes). Un mes que aún no cierra no se
    congela: se consulta y se usa sin guardar (el portal no genera periodos abiertos).
    """
    with _lock(month):
        foto = load(month)
        if foto is not None:
            return foto, False
        snapshot, planes = consultar()
        if not month.is_closed():
            taken = now()
            return {"formato": FORMATO, "periodo": month.id, "desde": month.start.isoformat(),
                    "corte": month.end.isoformat(), "tomada": taken.isoformat(), "tardia": False,
                    "origen": "sin_guardar", "snapshot": snapshot, "planes": planes}, True
        return save(month, snapshot, planes, origen), True


def listar() -> list[dict[str, Any]]:
    out = []
    for p in sorted(settings.FOTOS_DIR.glob("????-??.json.gz")):
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            foto = json.load(fh)
        out.append({**info(foto), "archivo": p.name, "tamano_mb": round(p.stat().st_size / 1e6, 2)})
    return out
