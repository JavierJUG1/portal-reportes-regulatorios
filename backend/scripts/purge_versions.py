"""Elimina versiones generadas (registro en el portal + archivo Excel guardado).

Uso (desde backend/):
    .venv/Scripts/python -m scripts.purge_versions --all --yes
    .venv/Scripts/python -m scripts.purge_versions --report f6 --period 2026-T3 --yes

Sin --yes solo muestra lo que se eliminaría. No elimina versiones "en proceso" (espera a que terminen).
Después, la siguiente generación de ese periodo vuelve a empezar en v1.
"""
from __future__ import annotations

import argparse
import sys

from app import db
from app.config import settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Elimina versiones generadas")
    parser.add_argument("--report", help="f6 | t12 | cortes")
    parser.add_argument("--period", help="AAAA-T# o AAAA-MM")
    parser.add_argument("--all", action="store_true", help="todas las versiones de todos los reportes")
    parser.add_argument("--yes", action="store_true", help="confirmar la eliminación")
    args = parser.parse_args()
    if not args.all and not args.report:
        parser.error("indica --all o --report (y opcionalmente --period)")

    sql, params = "SELECT * FROM report_versions", []
    if not args.all:
        sql += " WHERE report=?"
        params.append(args.report)
        if args.period:
            sql += " AND period=?"
            params.append(args.period)
    rows = db.query(sql + " ORDER BY id", tuple(params))
    busy = [r for r in rows if r["status"] == "processing"]
    if busy:
        print("Hay versiones en proceso; espera a que terminen:", [(r["report"], r["period"], r["version"]) for r in busy])
        return 1
    if not rows:
        print("No hay versiones que eliminar.")
        return 0
    for r in rows:
        print(f"  {r['report']:6} {r['period']:8} v{r['version']}  {r['status']:10} {r.get('filename') or '—'}")
    if not args.yes:
        print(f"{len(rows)} versión(es). Agrega --yes para eliminarlas.")
        return 0

    removed_files = 0
    root = settings.STORAGE_DIR.resolve()
    for r in rows:
        key = r.get("storage_key")
        if key and settings.STORAGE_BACKEND == "local":
            path = (root / key).resolve()
            if root in path.parents and path.exists():
                path.unlink()
                removed_files += 1
    with db.tx() as conn:
        conn.executemany("DELETE FROM report_versions WHERE id=?", [(r["id"],) for r in rows])
    print(f"Eliminadas {len(rows)} versión(es) y {removed_files} archivo(s).")
    if settings.STORAGE_BACKEND != "local":
        print("Nota: con STORAGE_BACKEND=erpnext los archivos en ERPNext no se borran desde aquí.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
