"""Arma el paquete del portal para subirlo a un servidor.

Uso (desde la carpeta del proyecto, después de `npm run build` en frontend/):
    backend/.venv/Scripts/python deploy/empaquetar.py

Crea release/portal-reportes-regulatorios_<fecha>_<commit>.zip con lo que necesita el servidor:
backend (código, scripts, config, plantillas, requirements, .env.example), frontend/dist (compilado),
dane/ (capas DANE), deploy/ y la documentación.

No incluye backend/.env (claves), backend/data (base de versiones) ni backend/storage (Excel con datos de
clientes): se configuran o copian aparte en el servidor (ver README → Despliegue en un servidor).
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "portal-reportes-regulatorios"

INCLUDE = [
    "README.md",
    "CONFIGURACION.md",
    "backend/app",
    "backend/scripts",
    "backend/config",
    "backend/templates",
    "backend/requirements.txt",
    "backend/.env.example",
    "frontend/dist",
    "dane",
    "deploy/portal-reportes.service",
    "deploy/nginx-portal-reportes.conf",
]
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc"}


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _files(rel: str):
    path = ROOT / rel
    if path.is_file():
        yield path
        return
    for f in sorted(path.rglob("*")):
        if f.is_file() and not SKIP_DIRS & set(f.relative_to(ROOT).parts) and f.suffix not in SKIP_SUFFIXES:
            yield f


def main() -> int:
    dist = ROOT / "frontend" / "dist" / "index.html"
    if not dist.exists():
        print("Falta frontend/dist: ejecuta `npm run build` en frontend/ antes de empaquetar.")
        return 1
    missing = [rel for rel in INCLUDE if not (ROOT / rel).exists()]
    if missing:
        print("Faltan archivos del proyecto: " + ", ".join(missing))
        return 1

    commit = _git("rev-parse", "--short", "HEAD") or "sin-git"
    dirty = bool(_git("status", "--porcelain"))
    built = datetime.now().astimezone()
    out_dir = ROOT / "release"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / f"{NAME}_{built:%Y-%m-%d}_{commit}.zip"

    version = (
        f"Portal de reportes regulatorios · CRC y MinTIC\n"
        f"Commit: {commit}{' (con cambios sin commit)' if dirty else ''}\n"
        f"Empaquetado: {built:%Y-%m-%d %H:%M %z}\n"
        f"Frontend compilado: {datetime.fromtimestamp(dist.stat().st_mtime).astimezone():%Y-%m-%d %H:%M %z}\n"
    )

    count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for rel in INCLUDE:
            for f in _files(rel):
                zf.write(f, f"{NAME}/{f.relative_to(ROOT).as_posix()}")
                count += 1
        zf.writestr(f"{NAME}/VERSION.txt", version)

    size = zip_path.stat().st_size / 1e6
    print(version.strip())
    print(f"Paquete: {zip_path.relative_to(ROOT)} · {count + 1} archivos · {size:.1f} MB")
    if dirty:
        print("Aviso: hay cambios sin commit en el proyecto; el paquete los incluye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
