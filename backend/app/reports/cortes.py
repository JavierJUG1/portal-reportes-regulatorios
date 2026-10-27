"""Corte mensual de suscripciones: estado de todas las suscripciones al último día del mes.

Cada corte queda ligado a su trimestre: los meses 1, 2 y 3 del trimestre son el MES 1, 2 y 3 del F6
(misma consulta a la API y misma regla), y el corte del mes 3 es la base de los accesos del T1.2.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..config import settings
from ..periods import Period, fmt_datetime, now
from .base import BuildContext, geo_stats, to_bytes
from .f6 import cuenta_f6
from .t12 import servicio_t12

ORANGE = "FF6900"
INK = "111111"
SOFT = "FFECE0"
ALT = "F5F5F5"
BORDER = "E4E4E7"
SECONDARY = "52525B"

HEADER_FILL = PatternFill("solid", fgColor=INK)
HEADER_FONT = Font(name="Roboto", bold=True, color="FFFFFF", size=10)
RELATION_FILL = PatternFill("solid", fgColor=ORANGE)  # columnas que ligan el corte con el F6 / T1.2
THIN = Side(style="thin", color=BORDER)

STATUS_ES = {
    "Active": "Activa", "Past Due Date": "Vencida", "Unpaid": "Sin pago (suspendida)",
    "Temporarily Suspended": "Suspensión temporal", "Cancelled": "Cancelada", "Completed": "Completada",
    "Trialling": "En prueba",
}
CLASE_ES = {1: "Cabecera municipal", 2: "Centro poblado", 3: "Rural disperso"}
SERVICIO_ES = {1: "Internet fijo", 3: "Televisión", 5: "Internet + TV (Duo Play 2)", None: "Sin servicio reportable"}

COLUMNS: list[tuple[str, int, str | None]] = [
    ("Suscripción", 18, None), ("Cliente", 34, None), ("Estado al corte", 18, None), ("Cuenta en F6", 10, None),
    ("Cuenta en T1.2", 10, None), ("Estado actual", 18, None),
    ("Fuente del estado", 14, None), ("Primer cambio posterior", 20, None), ("Creación", 12, "yyyy-mm-dd"),
    ("Inicio", 12, "yyyy-mm-dd"), ("Cancelación", 12, "yyyy-mm-dd"), ("Ciudad (ERPNext)", 16, None),
    ("Código DANE municipio", 12, "00000"), ("Municipio DANE", 24, None), ("Clase DANE", 18, None),
    ("Código centro poblado", 14, "[<100]0;00000000"), ("Centro poblado", 22, None),
    ("Código vereda", 12, "[<100]0;00000000"), ("Vereda", 22, None), ("Origen de la ubicación", 16, None),
    ("Latitud", 12, "0.000000"), ("Longitud", 12, "0.000000"), ("Estrato", 8, None), ("Cliente B2B", 10, None),
    ("Segmento F6", 10, None), ("Segmento T1.2", 10, None), ("Servicio / paquete", 24, None), ("Internet", 9, None), ("TV", 7, None),
    ("Velocidad bajada (Mbps)", 12, "#,##0.##"), ("Velocidad subida (Mbps)", 12, "#,##0.##"),
    ("Valor plan sin IVA", 14, "#,##0"), ("Precio total ERPNext", 14, "#,##0"), ("Descuento %", 10, "0.##"),
    ("Planes", 60, None), ("Conjunto", 28, None), ("Ubicación", 16, None), ("Usuario PPPoE", 20, None),
    ("Serial ONU", 20, None), ("ID plataforma TV", 14, None),
]
RELATION_COLUMNS = {"Cuenta en F6", "Cuenta en T1.2"}
FORMATS = [fmt for _, _, fmt in COLUMNS]


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _yes(value: bool) -> str:
    return "Sí" if value else "No"


def _summary_block(ws, start_row: int, title: str, rows: list[tuple[str, Any]]) -> int:
    ws.cell(row=start_row, column=1, value=title).font = Font(name="Roboto", bold=True, size=11, color=INK)
    r = start_row + 1
    for label, value in rows:
        a = ws.cell(row=r, column=1, value=label)
        b = ws.cell(row=r, column=2, value=value)
        a.font = Font(name="Roboto", size=10, color=SECONDARY)
        b.font = Font(name="Roboto", size=10, bold=True, color=INK)
        if isinstance(value, (int, float)):
            b.number_format = "#,##0"
        a.border = b.border = Border(bottom=THIN)
        r += 1
    return r + 1


def build(period: Period, ctx: BuildContext) -> tuple[bytes, dict[str, Any]]:
    snap = ctx.snapshot(period.start, period.end)
    rows = ctx.enriched(period.start, period.end)

    wb = Workbook()
    resumen = wb.active
    resumen.title = "Resumen"
    data_ws = wb.create_sheet("Suscripciones")

    # ---- Hoja de detalle
    for c, (title, width, _) in enumerate(COLUMNS, start=1):
        cell = data_ws.cell(row=1, column=c, value=title)
        cell.fill = RELATION_FILL if title in RELATION_COLUMNS else HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        data_ws.column_dimensions[get_column_letter(c)].width = width
    data_ws.row_dimensions[1].height = 32

    by_status: Counter[str] = Counter()
    by_mpio: Counter[str] = Counter()
    by_service: Counter[str] = Counter()
    by_segment: Counter[int] = Counter()
    f6_by_status: Counter[str] = Counter()
    accesos_t12 = 0
    for i, r in enumerate(rows, start=2):
        cls, loc = r["_cls"], r["_geo"]
        status = r.get("status_al_corte") or ""
        en_f6 = cuenta_f6(r)
        en_t12 = servicio_t12(r) is not None
        if en_f6:
            f6_by_status[status] += 1
        accesos_t12 += en_t12
        by_status[STATUS_ES.get(status, status)] += 1
        if status in settings.T12_STATUSES:
            by_mpio[f'{loc["dane_municipio"]} · {loc.get("dane_municipio_nombre", "")}'] += 1
            by_service[SERVICIO_ES.get(cls["servicio_paquete"], "—")] += 1
            by_segment[cls["segmento_t12"]] += 1
        values = [
            r.get("subscription"), r.get("cliente"), STATUS_ES.get(status, status), _yes(en_f6), _yes(en_t12),
            STATUS_ES.get(r.get("status_actual") or "", r.get("status_actual")), r.get("fuente_status"),
            str(r.get("primer_cambio_posterior") or "") or None, _date(r.get("creation")), _date(r.get("start_date")),
            _date(r.get("cancelation_date")), r.get("ciudad"), int(loc["dane_municipio"]),
            loc.get("dane_municipio_nombre"), CLASE_ES.get(loc["clase"]), loc.get("cp_codigo"), loc.get("cp_nombre"),
            loc.get("vereda_codigo"), loc.get("vereda_nombre"), loc.get("geo_fuente"),
            r.get("latitude") or None, r.get("longitude") or None, r.get("estrato"),
            _yes(bool(r.get("cliente_b2b"))), cls["segmento_f6"], cls["segmento_t12"], SERVICIO_ES.get(cls["servicio_paquete"]),
            _yes(cls["tiene_internet"]), _yes(cls["tiene_tv"]), cls["velocidad_bajada_mbps"],
            cls["velocidad_subida_mbps"], round(cls["valor_plan"]), r.get("total_price"), r.get("adjustment_price"),
            r.get("planes_todos"), r.get("conjunto"), r.get("ubicacion"), r.get("pppoe_username"),
            r.get("onu_serial"), r.get("id_plataforma_tv"),
        ]
        for c, value in enumerate(values, start=1):
            if value is None:
                continue
            cell = data_ws.cell(row=i, column=c, value=value)
            fmt = FORMATS[c - 1]
            if fmt:
                cell.number_format = fmt
    data_ws.freeze_panes = "C2"
    suscriptores_f6 = sum(f6_by_status.values())
    data_ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(len(rows) + 1, 2)}"

    # ---- Hoja de resumen
    resumen.column_dimensions["A"].width = 46
    resumen.column_dimensions["B"].width = 22
    title = resumen.cell(row=1, column=1, value=f"Corte de suscripciones · {period.label}")
    title.font = Font(name="Roboto", bold=True, size=16, color=INK)
    resumen.cell(row=2, column=1, value="GIGA FIBRA SAS · Portal de reportes regulatorios").font = Font(
        name="Roboto", size=10, color=SECONDARY)
    resumen["A3"].fill = PatternFill("solid", fgColor=ORANGE)
    resumen["B3"].fill = PatternFill("solid", fgColor=ORANGE)
    resumen.row_dimensions[3].height = 4
    r = 5
    r = _summary_block(resumen, r, "Parámetros de la consulta", [
        ("Inicio del periodo (desde)", period.start.isoformat()),
        ("Fecha de corte", period.end.isoformat()),
        ("Fuente", f"ERPNext · {settings.SNAPSHOT_METHOD}"),
        ("Generado", fmt_datetime(now())),
        ("Total de suscripciones en el corte", int(snap.get("total") or len(rows))),
    ])
    quarter, mes = period.quarter(), period.month_in_quarter
    cierre = quarter.months()[-1]
    t12_label = ("Accesos que entran al T1.2 (corte de cierre del trimestre)" if mes == 3 else
                 f"Accesos T1.2 a este corte (referencia: el T1.2 usa el corte de {cierre.sub_label.lower()})")
    r = _summary_block(resumen, r, "Relación con el reporte trimestral", [
        ("Trimestre", f"{quarter.label} ({quarter.id})"),
        ("Mes dentro del trimestre", f"{mes} de 3 · columna MES = {mes} del F6"),
        (f"Suscriptores de TV que entran al F6 (MES {mes})", suscriptores_f6),
        (t12_label, accesos_t12),
    ])
    r = _summary_block(resumen, r, "Suscriptores F6 por estado al corte", [
        (f"{STATUS_ES.get(s, s)} ({s})", f6_by_status.get(s, 0)) for s in settings.F6_STATUSES
    ] + [("Total F6", suscriptores_f6)])
    r = _summary_block(resumen, r, "Suscripciones por estado al corte", sorted(by_status.items(), key=lambda x: -x[1]))
    r = _summary_block(resumen, r, "Accesos conectados por municipio (incluye suspendidas)",
                       sorted(by_mpio.items(), key=lambda x: -x[1]))
    r = _summary_block(resumen, r, "Accesos conectados por servicio", sorted(by_service.items(), key=lambda x: -x[1]))
    seg_labels = {101: "Estrato 1", 102: "Estrato 2", 103: "Estrato 3", 104: "Estrato 4", 105: "Estrato 5",
                  106: "Estrato 6", 107: "Corporativo", 108: "Sin estratificar", 109: "Uso propio"}
    r = _summary_block(resumen, r, "Accesos conectados por segmento",
                       [(seg_labels.get(k, str(k)), v) for k, v in sorted(by_segment.items())])
    gs = geo_stats(rows)
    _summary_block(resumen, r, "Origen de la ubicación DANE", [
        ("Por coordenadas (MGN 2025 / veredas 2024)", gs["por_coordenadas"]),
        ("Por ciudad (sin coordenadas válidas)", gs["por_ciudad"]),
        ("Municipio por defecto", gs["por_defecto"]),
    ])
    resumen.sheet_view.showGridLines = False

    stats = {"suscripciones": len(rows), "estados": dict(by_status),
             "conectadas": sum(by_service.values()), "trimestre": quarter.id, "mes_trimestre": mes,
             "suscriptores_f6": suscriptores_f6, "f6_por_estado": dict(f6_by_status),
             "accesos_t12": accesos_t12, **gs}
    return to_bytes(wb), stats
