"""Arranca el portal (API + frontend compilado) con uvicorn.

Uso (desde la carpeta del proyecto o desde backend/):
    backend/.venv/Scripts/python backend/scripts/serve.py
    backend/.venv/Scripts/python backend/scripts/serve.py --env-file ruta/a/otro.env --port 8001

--env-file permite usar otra configuración (p. ej. pruebas o staging) sin tocar backend/.env.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor del portal de reportes")
    parser.add_argument("--env-file", help="archivo .env alterno (tiene prioridad sobre backend/.env)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file, override=True)
    sys.path.insert(0, str(BACKEND_DIR))
    import uvicorn

    uvicorn.run("app.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
