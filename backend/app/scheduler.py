"""Generación automática (mientras el servidor del portal esté encendido):
- Cortes de suscripciones: último día de cada mes.
- F6 y T1.2: último día de cada trimestre (marzo, junio, septiembre, diciembre). En ese momento también
  se generan los cortes mensuales del trimestre que falten, para que cada trimestre tenga sus 3 cortes.
- Al arrancar: genera lo que quedó pendiente si el servidor estaba apagado el día de cierre.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .config import settings
from .generator import REPORTS, SYSTEM_EMAIL, SYSTEM_NAME, GenerationError, request_generation
from .periods import Period, current_period

log = logging.getLogger("portal.scheduler")
_scheduler: BackgroundScheduler | None = None


def _generate_current(report_key: str, trigger: str = "schedule") -> None:
    report = REPORTS[report_key]
    period = current_period(report.kind)
    try:
        request_generation(report_key, period.id, user_email=SYSTEM_EMAIL, user_name=SYSTEM_NAME, trigger=trigger)
        log.info("Generación programada lanzada: %s %s", report_key, period.id)
    except GenerationError as exc:
        log.warning("No se lanzó %s %s: %s", report_key, period.id, exc)


def _monthly_job() -> None:
    for key, report in REPORTS.items():
        if report.kind == "month":
            _generate_current(key)


def _has_version(report_key: str, period_id: str) -> bool:
    """Ya tiene una versión disponible o en proceso (las fallidas no cuentan)."""
    return any(v["status"] in ("available", "processing") for v in db.versions_for(report_key, period_id))


def ensure_quarter_cuts(quarter: Period, trigger: str) -> None:
    """Genera los cortes mensuales cerrados del trimestre que no tengan versión."""
    if "cortes" not in REPORTS:
        return
    for month in quarter.months():
        if month.is_closed() and not _has_version("cortes", month.id):
            try:
                request_generation("cortes", month.id, user_email=SYSTEM_EMAIL, user_name=SYSTEM_NAME, trigger=trigger)
                log.info("Corte del trimestre %s: generando %s", quarter.id, month.id)
            except GenerationError as exc:
                log.warning("No se lanzó el corte %s: %s", month.id, exc)


def _quarterly_job() -> None:
    for key, report in REPORTS.items():
        if report.kind == "quarter":
            _generate_current(key)
    ensure_quarter_cuts(current_period("quarter"), "schedule")


def catch_up() -> None:
    """Si el servidor estaba apagado el día de cierre, genera el último periodo cerrado que no tenga versión."""
    if settings.DATA_SOURCE == "erpnext" and not (settings.ERPNEXT_API_KEY and settings.ERPNEXT_API_SECRET):
        log.warning("Recuperación omitida: faltan ERPNEXT_API_KEY / ERPNEXT_API_SECRET en backend/.env")
        return
    for key, report in REPORTS.items():
        period = current_period(report.kind)
        if not period.is_closed():
            period = period.prev()
        if not db.versions_for(key, period.id):
            try:
                request_generation(key, period.id, user_email=SYSTEM_EMAIL, user_name=SYSTEM_NAME, trigger="catch_up")
                log.info("Recuperación: generando %s %s", key, period.id)
            except GenerationError as exc:
                log.warning("Recuperación omitida %s %s: %s", key, period.id, exc)
    # Cortes del último trimestre cerrado y del trimestre en curso (meses ya cerrados).
    quarter = current_period("quarter")
    ensure_quarter_cuts(quarter.prev(), "catch_up")
    ensure_quarter_cuts(quarter, "catch_up")


def start() -> BackgroundScheduler | None:
    global _scheduler
    if not settings.SCHEDULER_ENABLED or _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone=settings.TIMEZONE)
    hour, minute = settings.SCHEDULE_HOUR, settings.SCHEDULE_MINUTE
    kinds = {r.kind for r in REPORTS.values()}
    if "month" in kinds:
        sched.add_job(_monthly_job, CronTrigger(day="last", hour=hour, minute=minute, timezone=settings.TIMEZONE),
                      id="mensual", replace_existing=True, misfire_grace_time=6 * 3600, coalesce=True)
    if "quarter" in kinds:
        sched.add_job(_quarterly_job,
                      CronTrigger(month="3,6,9,12", day="last", hour=hour, minute=minute, timezone=settings.TIMEZONE),
                      id="trimestral", replace_existing=True, misfire_grace_time=6 * 3600, coalesce=True)
    sched.start()
    _scheduler = sched
    for job in sched.get_jobs():
        log.info("Tarea programada %s → próxima ejecución %s", job.id, job.next_run_time)
    if settings.CATCH_UP_ON_START:
        catch_up()
    return sched


def next_runs() -> dict[str, str | None]:
    if _scheduler is None:
        return {}
    return {job.id: job.next_run_time.isoformat() if job.next_run_time else None for job in _scheduler.get_jobs()}


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
