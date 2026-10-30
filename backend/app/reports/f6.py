"""Res. 00175 - F6. Suscriptores y asociados de televisión cerrada (trimestral, detalle mensual)."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ..config import settings
from ..periods import Period
from .base import BuildContext, geo_stats, int_code, load_template, reset_sheet, to_bytes, write_rows

SHEET = "SUSCRIP_ASOCI_TV_CERRADA"
MODALIDAD_SUSCRIPCION = 1
CABECERA = "0"
ZONA_RURAL = "RURAL DISPERSO"


def _centro_poblado(loc: dict[str, Any]) -> tuple[int, str]:
    """Código y nombre de centro poblado según las notas de las variables 5 y 6."""
    if loc["clase"] == 2 and loc.get("cp_codigo"):
        return int(loc["cp_codigo"]), str(loc.get("cp_nombre") or "")
    if loc["clase"] == 3:
        # No es centro poblado: se indica el nombre de la zona (vereda DANE).
        return 0, (loc.get("vereda_nombre") or ZONA_RURAL)
    return 0, CABECERA  # cabecera municipal


def _nombre_registro(cp_code: int, nombres: set[str]) -> str:
    """Nombre del único registro de un centro poblado.

    MinTIC identifica cada registro del F6 sin el nombre (año, trimestre, mes, municipio, código de centro
    poblado, modalidad, segmento y tecnología): todo lo que comparte el código "0" de un municipio (cabecera y
    veredas rurales) va en un solo registro, o el reporte se rechaza por "Registro Duplicado".
    """
    if cp_code != 0 or len(nombres) == 1:
        return sorted(nombres)[0]
    if CABECERA in nombres:
        return CABECERA  # incluye la cabecera municipal
    return ZONA_RURAL  # varias veredas sin centro poblado


def cuenta_f6(r: dict[str, Any]) -> bool:
    """Si la suscripción (fila enriquecida de un corte) cuenta como suscriptor de TV en el F6.

    Criterio de Regulatorio (26/10/2026): estado al corte Active, Past Due Date o Unpaid,
    con TV paga (sin "Giga Fibra TV - Free"), según los datos que entrega la API para el corte.
    El corte mensual usa esta misma regla, así cuadra con el MES correspondiente del F6.
    """
    cls = r["_cls"]
    if r.get("status_al_corte") not in settings.F6_STATUSES:
        return False
    if not cls["tiene_tv_pago"]:
        return False
    return not (cls["uso_propio"] and settings.F6_EXCLUDE_OWN_USE)


def build(period: Period, ctx: BuildContext) -> tuple[bytes, dict[str, Any]]:
    # Un registro por (mes, municipio, centro poblado, segmento): la llave de MinTIC no incluye el nombre.
    counts: Counter[tuple] = Counter()
    nombres: dict[tuple, set[str]] = defaultdict(set)
    month_stats = []
    for mes_trim, month in enumerate(period.months(), start=1):
        rows = ctx.enriched(month.start, month.end)
        considered = 0
        for r in rows:
            if not cuenta_f6(r):
                continue
            cls = r["_cls"]
            loc = r["_geo"]
            cp_code, cp_name = _centro_poblado(loc)
            key = (mes_trim, int_code(loc["dane_municipio"]), cp_code, cls["segmento_f6"])
            counts[key] += 1
            nombres[key].add(cp_name)
            considered += 1
        month_stats.append({"mes": month.label, "conexiones": considered, **geo_stats(rows)})

    out_rows = []
    for key, total in sorted(counts.items()):
        mes, mpio, cp_code, seg = key
        out_rows.append([period.year, period.number, mes, mpio, cp_code, _nombre_registro(cp_code, nombres[key]),
                         MODALIDAD_SUSCRIPCION, seg, settings.F6_TECNOLOGIA, total])
    wb = load_template(settings.TEMPLATE_F6)
    ws = wb[SHEET]
    reset_sheet(ws)
    write_rows(ws, out_rows, {4: "00000", 5: "[<100]0;00000000"})
    stats = {"filas": len(out_rows), "meses": month_stats,
             "conexiones_ultimo_mes": month_stats[-1]["conexiones"] if month_stats else 0}
    return to_bytes(wb), stats
