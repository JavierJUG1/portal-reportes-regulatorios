"""Orquestación: consulta ERPNext → arma el Excel → guarda → registra la versión."""
from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from . import db
from .config import settings
from .erpnext import ERPNextError, get_client
from .periods import Period, now, parse_period
from .reports import cortes, f6, t12
from .reports.base import BuildContext
from .storage import get_storage

log = logging.getLogger("portal.generator")

SYSTEM_EMAIL = "system"
SYSTEM_NAME = "Sistema"


@dataclass(frozen=True)
class ReportDef:
    key: str
    name: str
    short: str
    kind: str  # quarter | month
    prefix: str
    icon: str
    frequency: str
    builder: Callable[[Period, BuildContext], tuple[bytes, dict[str, Any]]]
    unit_singular: str
    unit_plural: str

    def filename(self, period: Period, version: int) -> str:
        return f"{self.prefix}_{period.file_token()}_v{version}.xlsx"


ALL_REPORTS: dict[str, ReportDef] = {
    "f6": ReportDef("f6", "Reporte F6", "F6", "quarter", "F6", "file", "Trimestral", f6.build, "periodo", "periodos"),
    "t12": ReportDef("t12", "Reporte T1.2", "T1.2", "quarter", "T12", "file", "Trimestral", t12.build,
                     "periodo", "periodos"),
    "cortes": ReportDef("cortes", "Cortes de suscripciones mensuales", "Cortes", "month", "Cortes", "users",
                        "Mensual", cortes.build, "mes", "meses"),
}
# Solo los reportes habilitados (ENABLED_REPORTS) se listan, programan y generan.
REPORTS: dict[str, ReportDef] = {k: v for k, v in ALL_REPORTS.items() if k in settings.ENABLED_REPORTS}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gen")
_lock = threading.Lock()


class GenerationError(Exception):
    pass


def get_report(key: str) -> ReportDef:
    if key not in REPORTS:
        raise KeyError(key)
    return REPORTS[key]


def request_generation(report_key: str, period_id: str, *, user_email: str, user_name: str, trigger: str,
                       wait: bool = False) -> dict[str, Any]:
    """Crea una nueva versión en proceso y la genera en segundo plano (o en línea si wait=True)."""
    report = get_report(report_key)
    period = parse_period(report.kind, period_id)
    if not period.is_closed():
        raise GenerationError(f"El periodo {period.label} aún no ha cerrado (cierre {period.end:%d/%m/%Y}).")
    with _lock:
        running = [v for v in db.versions_for(report.key, period.id) if v["status"] == "processing"]
        if running:
            return running[0]
        version = db.create_version(report.key, period.id, user_email, user_name, trigger)
    if wait:
        _run(version["id"])
        return db.get_version(version["id"])  # type: ignore[return-value]
    _executor.submit(_run, version["id"])
    return version


def _run(version_id: int) -> None:
    version = db.get_version(version_id)
    if not version:
        return
    report = ALL_REPORTS[version["report"]]
    period = parse_period(report.kind, version["period"])
    started = time.monotonic()
    client = None
    try:
        client = get_client()
        ctx = BuildContext(client, origen=version["trigger"])
        data, stats = report.builder(period, ctx)
        filename = report.filename(period, version["version"])
        key = get_storage().save(report.key, period.year, filename, data)
        stats.update({
            "ajustes_al_corte": ctx.ajustes,
            "advertencias": ctx.warnings,
            "consultas": ctx.queries,
            "duracion_s": round(time.monotonic() - started, 1),
        })
        db.finish_version(version_id, filename=filename, storage_key=key, size_bytes=len(data), stats=stats)
        db.set_kv("last_sync", now().isoformat())
        log.info("Generado %s %s v%s en %.1fs", report.key, period.id, version["version"], stats["duracion_s"])
    except ERPNextError as exc:
        log.warning("Error ERPNext generando %s %s: %s", report.key, period.id, exc.detail)
        db.fail_version(version_id, error=exc.user_message, detail=exc.detail)
    except Exception as exc:  # noqa: BLE001
        log.exception("Error generando %s %s", report.key, period.id)
        db.fail_version(version_id, error="Ocurrió un error inesperado al armar el archivo.",
                        detail=f"{exc!r}\n{traceback.format_exc()}")
    finally:
        if client is not None:
            client.close()
