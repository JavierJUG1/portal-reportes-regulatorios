"""Genera un reporte desde la línea de comandos (backfill o pruebas).

Uso (desde backend/):
    .venv/Scripts/python -m scripts.generate f6 2026-T3
    .venv/Scripts/python -m scripts.generate t12 2026-T3
    .venv/Scripts/python -m scripts.generate cortes 2026-09
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from app import db
from app.generator import REPORTS, request_generation


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera un reporte regulatorio")
    parser.add_argument("report", choices=sorted(REPORTS))
    parser.add_argument("period", help="AAAA-T# para trimestrales, AAAA-MM para mensuales")
    parser.add_argument("--by", default="system", help="correo de quien genera (por defecto: system)")
    parser.add_argument("--name", help="nombre visible de quien genera (por defecto: Sistema o el correo)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    db.connect()
    name = args.name or ("Sistema" if args.by == "system" else args.by)
    version = request_generation(args.report, args.period, user_email=args.by, user_name=name,
                                 trigger="manual", wait=True)
    print(json.dumps({k: version[k] for k in ("report", "period", "version", "status", "filename", "error")},
                     ensure_ascii=False, indent=2))
    if version.get("stats"):
        print(json.dumps(version["stats"], ensure_ascii=False, indent=2)[:4000])
    return 0 if version["status"] == "available" else 1


if __name__ == "__main__":
    sys.exit(main())
