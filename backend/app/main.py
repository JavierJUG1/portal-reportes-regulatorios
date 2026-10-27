"""API del Portal de reportes regulatorios (CRC y MinTIC)."""
from __future__ import annotations

import logging
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from . import auth, db, permissions, scheduler
from .config import settings
from .generator import (ALL_REPORTS, REPORTS, SYSTEM_EMAIL, GenerationError, ReportDef, get_report,
                        request_generation)
from .periods import MESES, Period, all_periods, current_period, fmt_date, fmt_datetime, parse_period
from .storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("portal")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.connect()
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Portal de reportes regulatorios · CRC y MinTIC", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

STATUS_ORDER = ("available", "processing", "error", "not_generated", "pending")


# ------------------------------------------------------------------ helpers
def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def version_out(v: dict[str, Any] | None, report: ReportDef | None = None) -> dict[str, Any] | None:
    if not v:
        return None
    report = report or ALL_REPORTS[v["report"]]
    period = parse_period(report.kind, v["period"])
    when = _dt(v.get("generated_at")) or _dt(v.get("created_at"))
    return {
        "id": v["id"], "report": v["report"], "report_name": report.name, "report_short": report.short,
        "report_icon": report.icon, "period": v["period"], "period_label": period.label,
        "version": v["version"], "status": v["status"], "filename": v.get("filename"),
        "created_at": v.get("created_at"), "generated_at": v.get("generated_at"),
        "generated_at_label": fmt_datetime(when) if when else "—",
        "generated_date_label": fmt_date(when) if when else "—",
        "generated_by": v.get("generated_by"), "generated_by_name": v.get("generated_by_name"),
        # Generaciones del calendario (y del CLI sin usuario): se muestran como "Generado por el sistema".
        "generated_by_system": v.get("generated_by") == SYSTEM_EMAIL,
        "trigger": v.get("trigger"), "error": v.get("error"), "size_bytes": v.get("size_bytes"),
        "warnings": (v.get("stats") or {}).get("advertencias", []) if isinstance(v.get("stats"), dict) else [],
        "quarter": _quarter_ref(period) if period.kind == "month" else None,
    }


def _quarter_ref(month: Period) -> dict[str, Any]:
    q = month.quarter()
    return {"period": q.id, "label": q.label, "year": q.year, "number": q.number, "mes_trim": month.month_in_quarter}


def _stats(v: dict[str, Any] | None) -> dict[str, Any]:
    stats = (v or {}).get("stats")
    return stats if isinstance(stats, dict) else {}


def _versions_by_period(report: ReportDef) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for v in db.versions_for(report.key):
        out.setdefault(v["period"], []).append(v)  # orden: versión desc
    return out


def _row_state(period: Period, versions: list[dict[str, Any]]) -> tuple[dict | None, dict | None, str]:
    latest = versions[0] if versions else None
    available = next((v for v in versions if v["status"] == "available"), None)
    status = latest["status"] if latest else ("not_generated" if period.is_closed() else "pending")
    return latest, available, status


def _link(report: ReportDef, period: Period, versions: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumen corto de un periodo de otro reporte (relación corte mensual ↔ reporte trimestral)."""
    latest, available, status = _row_state(period, versions)
    return {"report": report.key, "short": report.short, "period": period.id, "label": period.label,
            "sub_label": period.sub_label, "closed": period.is_closed(), "status": status,
            "latest": version_out(latest, report), "available": version_out(available, report), "check": None}


def _check(label: str, report_value: Any, cut_value: Any) -> dict[str, Any] | None:
    """Cuadre entre el total del reporte trimestral y el del corte mensual (si ambos están disponibles)."""
    if report_value is None or cut_value is None:
        return None
    return {"label": label, "report_value": int(report_value), "cut_value": int(cut_value),
            "ok": int(report_value) == int(cut_value)}


def _f6_month_value(f6_version: dict[str, Any] | None, mes: int) -> int | None:
    meses = _stats(f6_version).get("meses") or []
    return meses[mes - 1].get("conexiones") if len(meses) >= mes else None


Related = dict[str, dict[str, list[dict[str, Any]]]]


def _related_maps() -> Related:
    """Versiones por periodo de todos los reportes habilitados (para armar las relaciones)."""
    return {key: _versions_by_period(r) for key, r in REPORTS.items()}


def _related(report: ReportDef, period: Period, maps: Related, own_available: dict | None) -> dict[str, Any] | None:
    if report.kind == "quarter":
        if "cortes" not in REPORTS:
            return None
        cortes = REPORTS["cortes"]
        items = []
        for mes, month in enumerate(period.months(), start=1):
            link = _link(cortes, month, maps["cortes"].get(month.id, []))
            link["mes_trim"] = mes
            cut = _stats(next((v for v in maps["cortes"].get(month.id, []) if v["status"] == "available"), None))
            if report.key == "f6":
                link["check"] = _check("Suscriptores F6", _f6_month_value(own_available, mes), cut.get("suscriptores_f6"))
            elif report.key == "t12" and mes == 3:
                link["check"] = _check("Accesos T1.2", _stats(own_available).get("accesos"), cut.get("accesos_t12"))
            items.append(link)
        return {"quarter": None, "items": items}
    # Corte mensual → reportes de su trimestre
    quarter, mes = period.quarter(), period.month_in_quarter
    cut = _stats(own_available)
    items = []
    for key, r in REPORTS.items():
        if r.kind != "quarter":
            continue
        versions = maps[key].get(quarter.id, [])
        link = _link(r, quarter, versions)
        q_available = next((v for v in versions if v["status"] == "available"), None)
        if key == "f6":
            link["check"] = _check("Suscriptores F6", _f6_month_value(q_available, mes), cut.get("suscriptores_f6"))
        elif key == "t12" and mes == 3:
            link["check"] = _check("Accesos T1.2", _stats(q_available).get("accesos"), cut.get("accesos_t12"))
        items.append(link)
    return {"quarter": _quarter_ref(period), "items": items}


def period_row(report: ReportDef, period: Period, versions: list[dict[str, Any]],
               maps: Related | None = None) -> dict[str, Any]:
    latest, available, status = _row_state(period, versions)
    return {
        "period": period.id, "label": period.label, "year": period.year, "number": period.number,
        "start": period.start.isoformat(), "end": period.end.isoformat(), "closed": period.is_closed(),
        "closing_label": f"Cierre {fmt_date(period.end)}", "status": status,
        "latest": version_out(latest, report), "available": version_out(available, report),
        "versions_count": len(versions),
        "related": _related(report, period, maps, available) if maps is not None else None,
    }


def report_summary(report: ReportDef, maps: Related | None = None) -> dict[str, Any]:
    maps = maps or _related_maps()
    by_period = maps[report.key]
    target = current_period(report.kind)
    if not target.is_closed():
        target = target.prev()
    row = period_row(report, target, by_period.get(target.id, []), maps)
    latest_available = None
    for p in all_periods(report.kind):
        av = next((v for v in by_period.get(p.id, []) if v["status"] == "available"), None)
        if av:
            latest_available = version_out(av, report)
            break
    return {
        "key": report.key, "name": report.name, "short": report.short, "icon": report.icon,
        "frequency": report.frequency, "kind": report.kind,
        "unit": {"singular": report.unit_singular, "plural": report.unit_plural},
        "current": row, "latest_available": latest_available,
    }


def enabled_versions() -> list[dict[str, Any]]:
    """Versiones de los reportes habilitados (las de reportes deshabilitados no se muestran)."""
    return [v for v in db.all_versions() if v["report"] in REPORTS]


def _enabled_version(vid: int) -> dict[str, Any]:
    v = db.get_version(vid)
    if not v or v["report"] not in REPORTS:
        raise HTTPException(status_code=404, detail="Versión no encontrada")
    return v


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


# --------------------------------------------------------------------- auth
class DebugLogin(BaseModel):
    email: str
    name: str = ""
    role_label: str = "Regulatorio · Analista"


@app.get("/api/auth/config")
def auth_config() -> dict[str, Any]:
    return {"mode": settings.AUTH_MODE, "oauth_ready": auth.oauth_configured(), "env_label": settings.ENV_LABEL,
            "erpnext_url": settings.ERPNEXT_URL}


@app.get("/api/auth/me")
def me(user: dict = Depends(auth.require_user)) -> dict[str, Any]:
    can_generate, reason = permissions.generation_access(user)
    return {**user, "can_generate": can_generate, "generate_denied_reason": reason,
            "generate_roles": settings.GENERATE_ROLES}


@app.post("/api/auth/debug-login")
def debug_login(body: DebugLogin, response: Response) -> dict[str, Any]:
    if settings.AUTH_MODE != "debug":
        raise HTTPException(status_code=404, detail="No disponible")
    if "@" not in body.email:
        raise HTTPException(status_code=422, detail="Ingresa un correo válido.")
    if not auth.email_allowed(body.email):
        raise HTTPException(status_code=403, detail="Usa un correo corporativo de Gigafibra.")
    user = auth.make_user(body.email, body.name, body.role_label, source="debug")
    auth.set_session(response, user)
    return user


@app.get("/api/auth/login")
def oauth_login(next: str = "") -> Response:  # noqa: A002 - nombre del parámetro en la URL
    if settings.AUTH_MODE != "erpnext" or not auth.oauth_configured():
        raise HTTPException(status_code=404, detail="SSO de ERPNext no configurado")
    response = RedirectResponse("about:blank", status_code=302)
    response.headers["location"] = auth.oauth_start_url(response, next)
    return response


@app.get("/api/auth/callback")
def oauth_callback(request: Request, code: str = "", state: str = "", error: str = "") -> Response:
    if error or not code:
        return RedirectResponse(f"/login?error={quote(error or 'cancelado')}", status_code=302)
    try:
        user = auth.oauth_finish(request, code, state)
    except HTTPException as exc:
        return RedirectResponse(f"/login?error={quote(str(exc.detail))}", status_code=302)
    response = RedirectResponse(auth.oauth_next(request) or settings.POST_LOGIN_REDIRECT, status_code=302)
    response.delete_cookie(auth.OAUTH_COOKIE, path="/")
    auth.set_session(response, user)
    return response


@app.post("/api/auth/logout")
def logout(response: Response) -> dict[str, bool]:
    auth.clear_session(response)
    return {"ok": True}


# --------------------------------------------------------------------- data
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "data_source": settings.DATA_SOURCE, "storage": settings.STORAGE_BACKEND}


@app.get("/api/meta")
def meta(_: dict = Depends(auth.require_user)) -> dict[str, Any]:
    last = db.get_kv("last_sync")
    return {
        "env_label": settings.ENV_LABEL,
        "data_source": settings.DATA_SOURCE,
        "last_sync": last,
        "last_sync_label": fmt_datetime(_dt(last)) if last else None,
        "schedule": scheduler.next_runs(),
        "reports": [{"key": r.key, "name": r.name, "short": r.short, "kind": r.kind} for r in REPORTS.values()],
    }


@app.get("/api/dashboard")
def dashboard(_: dict = Depends(auth.require_user)) -> dict[str, Any]:
    recent = [version_out(v) for v in enabled_versions()[:5]]
    maps = _related_maps()
    return {"reports": [report_summary(r, maps) for r in REPORTS.values()], "recent": recent}


@app.get("/api/reports/{key}")
def report_detail(key: str, _: dict = Depends(auth.require_user)) -> dict[str, Any]:
    try:
        return report_summary(get_report(key))
    except KeyError:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")


@app.get("/api/reports/{key}/periods")
def report_periods(
    key: str,
    year: int | None = None,
    sub: int | None = None,
    status: str | None = None,
    sort: str = "period_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(8, ge=1, le=100),
    _: dict = Depends(auth.require_user),
) -> dict[str, Any]:
    try:
        report = get_report(key)
    except KeyError:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    maps = _related_maps()
    by_period = maps[report.key]
    periods = all_periods(report.kind)
    rows = [period_row(report, p, by_period.get(p.id, []), maps) for p in periods]
    years = sorted({r["year"] for r in rows}, reverse=True)
    if year:
        rows = [r for r in rows if r["year"] == year]
    if sub:
        rows = [r for r in rows if r["number"] == sub]
    if status:
        wanted = {"not_generated", "pending"} if status == "not_generated" else {status}
        rows = [r for r in rows if r["status"] in wanted]
    if sort.startswith("generated"):
        def gen_key(r: dict[str, Any]) -> str:
            return (r["latest"] or {}).get("generated_at") or (r["latest"] or {}).get("created_at") or ""
        with_date = [r for r in rows if gen_key(r)]
        without = [r for r in rows if not gen_key(r)]
        with_date.sort(key=gen_key, reverse=sort.endswith("desc"))
        rows = with_date + without
    elif sort == "period_asc":
        rows.reverse()
    total = len(rows)
    start = (page - 1) * page_size
    return {"items": rows[start:start + page_size], "total": total, "page": page, "page_size": page_size,
            "years": years, "unit": {"singular": report.unit_singular, "plural": report.unit_plural},
            "sub_options": ([{"value": i, "label": f"Trimestre {i}"} for i in range(1, 5)] if report.kind == "quarter"
                            else [{"value": i + 1, "label": m} for i, m in enumerate(MESES)])}


@app.post("/api/reports/{key}/periods/{period_id}/generate")
def generate(key: str, period_id: str, user: dict = Depends(auth.require_user)) -> dict[str, Any]:
    try:
        report = get_report(key)
        permissions.require_generator(user)  # solo System Manager (GENERATE_ROLES) en ERPNext
        version = request_generation(report.key, period_id, user_email=user["email"], user_name=user["name"],
                                     trigger="on_demand")
    except KeyError:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    except (GenerationError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return version_out(version, report)  # type: ignore[return-value]


@app.get("/api/versions/{vid}")
def version_detail(vid: int, _: dict = Depends(auth.require_user)) -> dict[str, Any]:
    return version_out(_enabled_version(vid))  # type: ignore[return-value]


@app.get("/api/versions/{vid}/download")
def download(vid: int, _: dict = Depends(auth.require_user)) -> Response:
    v = _enabled_version(vid)
    if v["status"] != "available" or not v.get("storage_key"):
        raise HTTPException(status_code=404, detail="El archivo no está disponible.")
    try:
        data = get_storage().read(v["storage_key"])
    except FileNotFoundError:
        raise HTTPException(status_code=410, detail="El archivo ya no se encuentra en el almacenamiento.")
    filename = v["filename"]
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
                 "X-Filename": quote(filename), "Cache-Control": "no-store"},
    )


@app.get("/api/history")
def history(
    q: str = "",
    report: str | None = None,
    year: int | None = None,
    sub: str | None = None,
    status: str | None = None,
    sort: str = "generated_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(8, ge=1, le=100),
    _: dict = Depends(auth.require_user),
) -> dict[str, Any]:
    versions = enabled_versions()
    vigente: dict[tuple[str, str], dict[str, Any]] = {}
    for v in versions:
        if v["status"] == "available":
            k = (v["report"], v["period"])
            if k not in vigente or v["version"] > vigente[k]["version"]:
                vigente[k] = v
    items = []
    for v in versions:
        out = version_out(v)
        assert out is not None
        cur = vigente.get((v["report"], v["period"]))
        out["tag"] = ("vigente" if cur and cur["id"] == v["id"]
                      else "reemplazada" if cur and v["version"] < cur["version"] else None)
        period = parse_period(REPORTS[v["report"]].kind, v["period"])
        out["year"], out["kind"], out["number"] = period.year, period.kind, period.number
        items.append(out)
    years = sorted({i["year"] for i in items}, reverse=True)
    if report:
        items = [i for i in items if i["report"] == report]
    if year:
        items = [i for i in items if i["year"] == year]
    if sub:  # "T3" (trimestre) o "M9" (mes)
        kind = "quarter" if sub.upper().startswith("T") else "month"
        try:
            number = int(sub[1:])
        except ValueError:
            number = -1
        items = [i for i in items if i["kind"] == kind and i["number"] == number]
    if status:
        items = [i for i in items if i["status"] == status]
    if q.strip():
        needle = _norm(q.strip())
        items = [i for i in items if needle in _norm(" ".join(str(x or "") for x in (
            i["report_name"], i["report_short"], i["period_label"], i["filename"], i["generated_by_name"],
            "generado por el sistema automatico" if i["generated_by_system"] else "", f"v{i['version']}")))]
    if sort == "generated_asc":
        items.reverse()
    elif sort.startswith("period"):
        items.sort(key=lambda i: (i["year"], i["number"] if i["kind"] == "month" else i["number"] * 3, i["version"]),
                   reverse=sort.endswith("desc"))
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": total, "page": page, "page_size": page_size,
            "years": years}


# ------------------------------------------------------------ frontend SPA
_dist = Path(settings.FRONTEND_DIST)


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str) -> Response:
    if full_path.startswith("api/"):
        return JSONResponse({"detail": "No encontrado"}, status_code=404)
    if not _dist.exists():
        return JSONResponse({"detail": "Frontend no compilado. Ejecuta `npm run build` en frontend/."},
                            status_code=503)
    candidate = (_dist / full_path).resolve()
    if full_path and candidate.is_file() and _dist.resolve() in candidate.parents:
        # Los archivos de /assets llevan hash en el nombre: se pueden guardar en caché indefinidamente.
        cache = "public, max-age=31536000, immutable" if full_path.startswith("assets/") else "no-cache"
        return FileResponse(candidate, headers={"Cache-Control": cache})
    # index.html sin caché, para que cada actualización del portal se vea de inmediato.
    return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})
