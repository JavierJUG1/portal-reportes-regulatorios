"""Fotos mensuales (respuesta de la API guardada al cierre de cada mes; ver app/fotos.py).

Uso (desde backend/; en el servidor: runuser -u portal-reportes -- .venv/bin/python -m scripts.fotos ...):
    .venv/Scripts/python -m scripts.fotos listar
    .venv/Scripts/python -m scripts.fotos tomar 2026-10                 # solo si aún no existe
    .venv/Scripts/python -m scripts.fotos tomar 2026-10 --reemplazar    # volver a tomarla a propósito

Normalmente no hace falta: la generación automática del corte (último día del mes, 23:50) toma la foto.
"--reemplazar" es para corregir un mes después del cierre (p. ej. un error de datos ya arreglado en ERPNext);
la foto anterior se conserva como AAAA-MM.anterior-<fecha>.json.gz. Las versiones ya generadas no cambian:
para que un reporte use la foto nueva hay que generar una nueva versión desde el portal.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import fotos  # noqa: E402
from app.config import settings  # noqa: E402
from app.erpnext import ERPNextError, get_client  # noqa: E402
from app.periods import parse_period  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Fotos mensuales de la API")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listar", help="muestra las fotos guardadas")
    tomar = sub.add_parser("tomar", help="toma la foto de un mes cerrado")
    tomar.add_argument("mes", help="AAAA-MM")
    tomar.add_argument("--reemplazar", action="store_true", help="vuelve a tomarla aunque ya exista")
    args = parser.parse_args()

    if args.cmd == "listar":
        items = fotos.listar()
        print(f"Fotos en {settings.FOTOS_DIR}: {len(items)}")
        for f in items:
            estado = "TARDÍA" if f["tardia"] else "al cierre"
            print(f"  {f['periodo']}  tomada {f['tomada_label']}  ({estado}, {f['origen']})  "
                  f"{f['suscripciones']} suscripciones · {f['planes']} planes · {f['tamano_mb']} MB")
        return 0

    month = parse_period("month", args.mes)
    if not month.is_closed():
        print(f"✗ {month.label} aún no ha cerrado (cierre {month.end:%d/%m/%Y}); la foto se toma desde ese día.")
        return 1
    actual = fotos.load(month)
    if actual and not args.reemplazar:
        meta = fotos.info(actual)
        print(f"Ya existe la foto de {month.label} (tomada {meta['tomada_label']}). Usa --reemplazar para retomarla.")
        return 0
    client = get_client()
    try:
        snapshot = client.snapshot(month.start, month.end)
        planes = client.subscription_plans()
    except ERPNextError as exc:
        print(f"✗ {exc.user_message} ({exc.detail[:200]})")
        return 1
    finally:
        client.close()
    meta = fotos.info(fotos.save(month, snapshot, planes, "manual"))
    print(f"✓ Foto de {month.label} {'reemplazada' if actual else 'guardada'}: tomada {meta['tomada_label']}, "
          f"{meta['suscripciones']} suscripciones, {meta['planes']} planes"
          + (" (tardía: planes y ubicación de hoy)" if meta["tardia"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
