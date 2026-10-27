"""Res. 7811 - T.1.2 Formato unificado ISP (trimestral): ingresos, accesos y quejas."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..classify import load_isp_customers, speed_value
from ..config import settings
from ..periods import Period
from .base import BuildContext, geo_stats, int_code, load_json_config, load_template, reset_sheet, to_bytes, write_rows

TECNOLOGIA_NA = 999
NO_APLICA = 99
VEREDA_SIN_CODIGO = 98
CODE8 = "[<100]0;00000000"  # códigos DANE de 8 dígitos con cero inicial; 98/99 se ven tal cual


# ---------------------------------------------------------------- INGRESOS
def ingresos(period: Period, ctx: BuildContext) -> tuple[list[list[Any]], dict[str, Any]]:
    cfg = load_json_config("ingresos_items.json")
    servicios: dict[str, int] = cfg["servicios"]
    excluir = set(cfg.get("excluir", []))
    totals: dict[int, float] = defaultdict(float)
    sin_mapear: dict[str, float] = {}
    for row in ctx.client.revenue_by_item(period.start, period.end):
        item, net = row.get("item_code") or "", float(row.get("net") or 0)
        if item in servicios:
            totals[servicios[item]] += net
        elif item not in excluir and abs(net) >= 1:
            sin_mapear[item] = net

    # Internet a otros ISP (lista config/clientes_isp.json): lo que se clasificó como 101 pasa a 110.
    isp_customers = load_isp_customers()
    isp_total = 0.0
    if isp_customers:
        for row in ctx.client.revenue_by_item(period.start, period.end, customers=isp_customers):
            if servicios.get(row.get("item_code") or "") == 101:
                isp_total += float(row.get("net") or 0)
        totals[101] -= isp_total
        totals[110] += isp_total

    if sin_mapear:
        ctx.warn("Ítems facturados sin clasificar en ingresos (no sumados): "
                 + ", ".join(f"{k} ({v:,.0f})" for k, v in sorted(sin_mapear.items())))
    rows = [[period.year, period.number, service, int(round(value))]
            for service, value in sorted(totals.items()) if round(value) != 0]
    return rows, {"ingresos": {str(s): int(round(v)) for s, v in totals.items()},
                  "clientes_isp": len(isp_customers)}


# ----------------------------------------------------------------- ACCESOS
def servicio_t12(r: dict[str, Any]) -> int | None:
    """Servicio/paquete con el que la suscripción entra como acceso al T1.2, o None si no se reporta.

    El corte mensual usa esta misma regla, así el corte del mes de cierre cuadra con el T1.2 del trimestre.
    """
    if r.get("status_al_corte") not in settings.T12_STATUSES:
        return None
    cls = r["_cls"]
    if cls["es_isp"]:
        # Venta mayorista a otros ISP: se reporta solo en ingresos (110), no como acceso.
        return None
    servicio = cls["servicio_paquete"]
    if servicio is not None and cls["tv_solo_gratis"] and not settings.INCLUDE_FREE_TV:
        servicio = 1 if cls["tiene_internet"] else None
    return servicio


def accesos(period: Period, ctx: BuildContext) -> tuple[list[list[Any]], dict[str, Any]]:
    rows = ctx.enriched(period.start, period.end)
    counts: Counter[tuple] = Counter()
    sin_velocidad = 0
    mayoristas = 0
    for r in rows:
        servicio = servicio_t12(r)
        if servicio is None:
            if r["_cls"]["es_isp"] and r.get("status_al_corte") in settings.T12_STATUSES:
                mayoristas += 1
            continue
        cls = r["_cls"]
        loc = r["_geo"]
        clase = int(loc["clase"])
        centro = int(loc["cp_codigo"]) if clase == 2 and loc.get("cp_codigo") else NO_APLICA
        vereda = (int(loc["vereda_codigo"]) if loc.get("vereda_codigo") else VEREDA_SIN_CODIGO) if clase == 3 else NO_APLICA
        tiene_internet = servicio in (1, 4, 5, 7)
        down = speed_value(cls["velocidad_bajada_mbps"]) if tiene_internet else 0
        up = speed_value(cls["velocidad_subida_mbps"]) if tiene_internet else 0
        if tiene_internet and not down:
            sin_velocidad += 1
        tecnologia = settings.T12_TECNOLOGIA_INTERNET if tiene_internet else TECNOLOGIA_NA
        valor = int(round(cls["valor_plan"]))
        key = (int_code(loc["dane_municipio"]), clase, centro, vereda, cls["segmento_t12"], servicio,
               down, up, tecnologia, valor)
        counts[key] += 1
    if sin_velocidad:
        ctx.warn(f"{sin_velocidad} acceso(s) de Internet sin velocidad identificable en sus planes (se reporta 0).")
    out = [[period.year, period.number, *key[:9], total, key[9]] for key, total in sorted(counts.items())]
    return out, {"accesos": sum(counts.values()), "accesos_isp_excluidos": mayoristas, **geo_stats(rows)}


# ------------------------------------------------------------------ QUEJAS
def quejas(period: Period, ctx: BuildContext) -> tuple[list[list[Any]], dict[str, Any]]:
    cfg = load_json_config("quejas_issue_types.json")
    tipos: dict[str, dict[str, Any]] = cfg["tipos"]
    default_service = int(cfg.get("servicio_por_defecto", 3))
    cerrados = set(cfg.get("estados_cerrados", ["Resolved", "Closed"]))
    reposicion = set(cfg.get("recursos_reposicion", []))
    apelacion = set(cfg.get("recursos_apelacion", []))
    tip_recursos = cfg.get("tipologia_recursos", "J1")
    por_tipologia: dict[str, str] = cfg.get("resultado_por_tipologia", {})

    issues = ctx.client.issues(period.start, period.end)
    agg: dict[tuple, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    month_index = {m.number: i for i, m in enumerate(period.months(), start=1)}
    contadas = 0
    for issue in issues:
        fecha = str(issue.get("opening_date") or "")[:10]
        if len(fecha) < 7:
            continue
        mes = month_index.get(int(fecha[5:7]))
        if mes is None:
            continue
        tipo = issue.get("issue_type") or ""
        if tipo in reposicion or tipo in apelacion:
            bucket = agg[(mes, default_service, tip_recursos)]
            bucket[3 if tipo in reposicion else 4] += 1
            continue
        regla = tipos.get(tipo)
        if not regla:
            continue
        servicio = int(regla.get("servicio", default_service))
        bucket = agg[(mes, servicio, regla["tipologia"])]
        bucket[0] += 1
        contadas += 1
        if issue.get("status") in cerrados:
            resultado = regla.get("resultado") or por_tipologia.get(regla["tipologia"]) or "segun_culpa"
            if resultado == "segun_culpa":
                # Solo cuando ERPNext indica explícitamente que la falla NO fue de GIGA se resuelve en contra.
                culpa = str(issue.get("custom_interrupcion_culpa") or "").strip().lower()
                resultado = "en_contra" if culpa == "no" else "a_favor"
            bucket[1 if resultado == "a_favor" else 2] += 1
    out = [[period.year, period.number, mes, servicio, tip, *vals]
           for (mes, servicio, tip), vals in sorted(agg.items())]
    return out, {"quejas": contadas, "issues_consultados": len(issues)}


SHEETS = {
    "ingresos": ("T1_2_ISP_INGRESOS", ingresos, {4: "0"}),
    "accesos": ("T1_2_ISP_ACCESOS", accesos, {3: "00000", 5: CODE8, 6: CODE8, 13: "0"}),
    "quejas": ("T1_2_ISP_QUEJAS", quejas, {}),
}


def build(period: Period, ctx: BuildContext) -> tuple[bytes, dict[str, Any]]:
    """Llena las pestañas de T12_SHEETS (por defecto solo ACCESOS) y quita las demás; INFO se conserva."""
    wb = load_template(settings.TEMPLATE_T12)
    stats: dict[str, Any] = {}
    for key, (sheet, builder, fmts) in SHEETS.items():
        if key not in settings.T12_SHEETS:
            wb.remove(wb[sheet])
            continue
        rows, sheet_stats = builder(period, ctx)
        ws = wb[sheet]
        reset_sheet(ws)
        write_rows(ws, rows, fmts)
        stats[f"filas_{key}"] = len(rows)
        stats.update(sheet_stats)
    wb.active = 0
    stats["pestañas"] = wb.sheetnames
    return to_bytes(wb), stats
