"""Clasificación regulatoria de cada suscripción a partir de sus planes de ERPNext."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from .config import settings

TV_ITEMS = {"Canais de TV"}
# Cargos no recurrentes que no hacen parte del valor del plan tarifario.
PRICE_EXCLUDED_ITEMS = {"Tarifa de reconexión", "TRASLADO", "VISITA TECNICA", "Item0188", "Punto cableado adicional"}
SPEED = re.compile(r"(\d+(?:[.,]\d+)?)\s*(gbps|gb|mbps|mb)\b", re.I)
INTERNET_HINT = re.compile(r"(mbps|gbps|\bgb\b|internet|corporativo|\bisp\b)", re.I)
OWN_USE = re.compile(settings.OWN_USE_CUSTOMER_PATTERN, re.I)
NONPROFIT = re.compile(settings.NONPROFIT_PATTERN, re.I)


def parse_speed_mbps(text: str | None) -> float | None:
    if not text:
        return None
    m = SPEED.search(text)
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    return value * 1000 if m.group(2).lower().startswith("g") else value


def normalize_customer(name: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().upper()
    text = re.sub(r"[.,]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def load_isp_customers() -> list[str]:
    """Clientes ISP (venta mayorista), con el nombre exacto de ERPNext."""
    path = settings.CONFIG_DIR / "clientes_isp.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [c for c in json.load(fh).get("clientes", []) if c]


@dataclass
class PlanInfo:
    name: str
    item: str
    cost: float
    internet: bool
    tv: bool
    download: float | None
    upload: float | None
    known: bool = True

    @property
    def is_tv_service(self) -> bool:
        return self.tv and (self.item in TV_ITEMS or "giga fibra tv" in self.name.lower())


class PlanCatalog:
    def __init__(self, records: list[dict[str, Any]]):
        self.plans: dict[str, PlanInfo] = {}
        for r in records:
            name = r.get("name") or ""
            self.plans[name] = PlanInfo(
                name=name,
                item=r.get("item") or "",
                cost=float(r.get("cost") or 0),
                internet=bool(int(r.get("custom_internet") or 0)),
                tv=bool(int(r.get("custom_television") or 0)),
                download=float(r["custom_download"]) if r.get("custom_download") else None,
                upload=float(r["custom_upload"]) if r.get("custom_upload") else None,
            )

    def get(self, name: str) -> PlanInfo:
        if name in self.plans:
            return self.plans[name]
        # Plan que no está en el catálogo: se infiere por el nombre.
        speed = parse_speed_mbps(name)
        is_tv = "giga fibra tv" in name.lower()
        return PlanInfo(name=name, item="", cost=0.0, internet=bool(INTERNET_HINT.search(name)) and not is_tv,
                        tv=is_tv, download=speed, upload=speed, known=False)


def split_plans(text: str | None) -> list[str]:
    return [p.strip() for p in (text or "").split(" | ") if p.strip()]


def plan_speed(p: PlanInfo) -> tuple[float | None, float | None]:
    """Velocidad (bajada, subida) en Mbps de un plan de Internet.

    SPEED_SOURCE=contratada (por defecto): la del nombre del plan ("250 Mbps", "1Gbps"); la subida
    conserva la proporción subida/bajada configurada en ERPNext (p. ej. 1024/512 → 1000/500).
    SPEED_SOURCE=aprovisionada: custom_download / custom_upload del plan en ERPNext.
    """
    named = parse_speed_mbps(p.name)
    if settings.SPEED_SOURCE == "contratada" and named:
        if p.download and p.upload:
            return named, round(named * p.upload / p.download, 2)
        return named, named
    down = p.download or named
    return down, p.upload or down


def classify(row: dict[str, Any], catalog: PlanCatalog, isp_customers: set[str] | None = None) -> dict[str, Any]:
    plans = [catalog.get(n) for n in split_plans(row.get("planes_todos"))]
    internet_plans = [p for p in plans if p.internet]
    tv_plans = [p for p in plans if p.is_tv_service]
    # La API marca TV por nombre ("Giga Fibra TV"); se respeta aunque el plan no esté en el catálogo.
    # Con custom_disabled_tv = 1 al corte la TV no está funcionando: no cuenta como servicio de TV.
    has_tv = bool(tv_plans) or bool(row.get("planes_tv"))
    if settings.EXCLUDE_DISABLED_TV and row.get("tv_deshabilitada"):
        has_tv = False
    tv_free_only = has_tv and all(p.cost <= 0 for p in tv_plans) if tv_plans else False
    has_internet = bool(internet_plans)
    # TV paga (criterio F6): algún plan marcado como TV en ERPNext (custom_television) con costo > 0.
    # Deja por fuera "Giga Fibra TV - Free" e incluye canales y set-box de TV con costo.
    has_paid_tv = any(p.tv and p.cost > 0 for p in plans)
    if settings.EXCLUDE_DISABLED_TV and row.get("tv_deshabilitada"):
        has_paid_tv = False

    down = up = None
    if has_internet:
        # Si hay varios planes de Internet se reporta el de mayor velocidad de bajada.
        speeds = [s for s in (plan_speed(p) for p in internet_plans) if s[0]]
        if speeds:
            down, up = max(speeds, key=lambda s: s[0] or 0)

    excluded = sum(p.cost for p in plans if p.item in PRICE_EXCLUDED_ITEMS)
    if row.get("precio_planes") is not None:
        price = float(row["precio_planes"]) - excluded
    else:
        price = sum(p.cost for p in plans) - excluded

    cliente = str(row.get("cliente") or "")
    segmento = int(row.get("segmento") or 8)
    own_use = bool(OWN_USE.search(cliente))
    nonprofit = segmento == 7 and bool(NONPROFIT.search(cliente))

    if has_internet and has_tv:
        servicio = 5  # Duo Play 2 (Internet fijo + TV por suscripción)
    elif has_internet:
        servicio = 1
    elif has_tv:
        servicio = 3
    else:
        servicio = None

    return {
        "planes": [p.name for p in plans],
        "planes_desconocidos": [p.name for p in plans if not p.known],
        "tiene_internet": has_internet,
        "tiene_tv": has_tv,
        "tv_solo_gratis": tv_free_only,
        "tiene_tv_pago": has_paid_tv,
        "velocidad_bajada_mbps": down,
        "velocidad_subida_mbps": up,
        "valor_plan": max(price, 0.0),
        "es_isp": bool(isp_customers) and normalize_customer(cliente) in isp_customers,
        "uso_propio": own_use,
        "sin_animo_lucro": nonprofit,
        "segmento_base": segmento,
        "segmento_f6": 9 if nonprofit else segmento,
        "segmento_t12": 109 if own_use else 100 + segmento,
        "servicio_paquete": servicio,
    }


def speed_value(mbps: float | None) -> float | int:
    if not mbps:
        return 0
    return int(mbps) if float(mbps).is_integer() else round(float(mbps), 2)
