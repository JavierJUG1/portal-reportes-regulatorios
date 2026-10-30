"""Une los registros duplicados (según MinTIC) de un F6 ya generado y lo guarda como una nueva versión.

MinTIC identifica cada registro del F6 sin el nombre del centro poblado (año, trimestre, mes, municipio,
código de centro poblado, modalidad, segmento y tecnología). Los F6 generados antes de la corrección del
30/10/2026 podían traer varias filas con código "0" en un mismo municipio (cabecera y veredas rurales), que
MinTIC rechaza como "Registro Duplicado". Este script toma la última versión disponible del periodo, suma esas
filas en una sola (mismos totales, mismos datos) y la guarda como la siguiente versión (p. ej. v2).

No consulta ERPNext: usa exactamente los datos del archivo ya generado.

Uso (desde backend/):
    .venv/Scripts/python -m scripts.unificar_f6 2026-T3 --simular
    .venv/Scripts/python -m scripts.unificar_f6 2026-T3 --by javier.urbina@gigafibra.co --name "Javier Urbina"
"""
from __future__ import annotations

import argparse
import io
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.config import settings  # noqa: E402
from app.generator import ALL_REPORTS, SYSTEM_EMAIL, SYSTEM_NAME  # noqa: E402
from app.periods import parse_period  # noqa: E402
from app.reports.base import load_template, reset_sheet, to_bytes, write_rows  # noqa: E402
from app.reports.f6 import SHEET, _nombre_registro  # noqa: E402
from app.storage import get_storage  # noqa: E402

# Columnas que identifican un registro en MinTIC (todas menos NOMBRE_CENTRO_POBLADO y NUMERO_TOTAL_CONEXIONES)
KEY_COLS = (0, 1, 2, 3, 4, 6, 7, 8)


def unificar(rows: list[tuple]) -> list[list]:
    totals: dict[tuple, int] = defaultdict(int)
    names: dict[tuple, set[str]] = defaultdict(set)
    for r in rows:
        key = tuple(r[i] for i in KEY_COLS)
        totals[key] += int(r[9])
        names[key].add(str(r[5]))
    out = []
    for key, total in sorted(totals.items()):
        anno, trim, mes, mpio, cp, modalidad, seg, tec = key
        out.append([anno, trim, mes, mpio, cp, _nombre_registro(int(cp), names[key]), modalidad, seg, tec, total])
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Une los registros duplicados de un F6 en una nueva versión")
    parser.add_argument("period", help="trimestre, p. ej. 2026-T3")
    parser.add_argument("--by", default=SYSTEM_EMAIL, help="correo de quien genera (por defecto: system)")
    parser.add_argument("--name", help="nombre visible de quien genera")
    parser.add_argument("--simular", action="store_true", help="muestra el resultado sin guardar la versión")
    args = parser.parse_args()

    report = ALL_REPORTS["f6"]
    period = parse_period("quarter", args.period)
    db.connect()
    source = next((v for v in db.versions_for("f6", period.id) if v["status"] == "available"), None)
    if not source:
        print(f"✗ No hay un F6 disponible para {period.label}.")
        return 1
    storage = get_storage()
    wb_src = openpyxl.load_workbook(io.BytesIO(storage.read(source["storage_key"])))
    rows = [r for r in wb_src[SHEET].iter_rows(min_row=2, values_only=True) if r[0] is not None]
    merged = unificar(rows)

    def por_mes(filas) -> dict[int, int]:
        acc: dict[int, int] = defaultdict(int)
        for r in filas:
            acc[int(r[2])] += int(r[9])
        return dict(sorted(acc.items()))

    print(f"Origen: {source['filename']} (v{source['version']}) · {len(rows)} filas · por mes {por_mes(rows)}")
    print(f"Unificado: {len(merged)} filas · por mes {por_mes(merged)}")
    if por_mes(rows) != por_mes(merged):
        print("✗ Los totales no coinciden; no se guarda nada.")
        return 1
    if len(merged) == len(rows):
        print("No había registros duplicados; no se crea una versión nueva.")
        return 0
    if args.simular:
        print("Simulación: no se guardó nada.")
        return 0

    wb = load_template(settings.TEMPLATE_F6)
    ws = wb[SHEET]
    reset_sheet(ws)
    write_rows(ws, merged, {4: "00000", 5: "[<100]0;00000000"})
    data = to_bytes(wb)

    name = args.name or (SYSTEM_NAME if args.by == SYSTEM_EMAIL else args.by)
    version = db.create_version("f6", period.id, args.by, name, "manual")
    filename = report.filename(period, version["version"])
    key = storage.save("f6", period.year, filename, data)
    stats = dict(source.get("stats") or {})
    stats.update({"filas": len(merged), "unificado_desde": f"v{source['version']}",
                  "nota": "Registros con la misma llave de MinTIC unidos en uno (sin consultar ERPNext)."})
    db.finish_version(version["id"], filename=filename, storage_key=key, size_bytes=len(data), stats=stats)
    print(f"✓ Guardado como {filename} (v{version['version']}), generado por {name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
