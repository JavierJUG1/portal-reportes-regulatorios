"""Utilidades comunes de los generadores de reportes."""
from __future__ import annotations

import io
import json
import logging
from collections import Counter
from datetime import date
from typing import Any

import openpyxl
from openpyxl.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from .. import al_corte, fotos, geo
from ..classify import PlanCatalog, classify, load_isp_customers, normalize_customer
from ..config import settings
from ..erpnext import ERPNextClient, FixtureClient
from ..periods import Period

log = logging.getLogger("portal.reports")


class BuildContext:
    """Datos de una generación. Cada mes completo sale de su foto mensual (app/fotos.py): la guardada al cierre,
    o la que se toma y guarda en la primera consulta posterior al cierre. Así regenerar un periodo da los mismos
    datos aunque después cambien las suscripciones en ERPNext."""

    def __init__(self, client: ERPNextClient | FixtureClient, origen: str = "generacion"):
        self.client = client
        self.origen = origen  # schedule | catch_up | on_demand | manual: queda registrado en las fotos nuevas
        self._snapshots: dict[tuple[date, date], dict[str, Any]] = {}
        self._enriched: dict[tuple[date, date], list[dict[str, Any]]] = {}
        self._catalog: PlanCatalog | None = None
        self._fotos: dict[str, dict[str, Any]] = {}
        self._catalogs: dict[str, PlanCatalog] = {}
        self.warnings: list[str] = []
        self.queries: list[dict[str, str]] = []
        self.ajustes: dict[str, dict[str, int]] = {}
        self._events_since: str | None = None
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._disabled_now: set[str] | None = None

    def events_after(self, corte: date) -> dict[str, list[dict[str, Any]]]:
        """Cambios de tabVersion posteriores al corte (una sola consulta cubre varios cortes)."""
        since = al_corte.limite(corte)
        if self._events_since is None or since < self._events_since:
            log.info("Consultando tabVersion desde %s", since)
            self._events = al_corte.load_events(self.client, since)
            self._events_since = since
        return self._events

    def disabled_tv_now(self) -> set[str]:
        if self._disabled_now is None:
            self._disabled_now = self.client.disabled_tv_subscriptions()
        return self._disabled_now

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def catalog(self) -> PlanCatalog:
        """Catálogo de planes actual de ERPNext (solo para rangos que no son un mes completo)."""
        if self._catalog is None:
            self._catalog = PlanCatalog(self.client.subscription_plans())
        return self._catalog

    def foto(self, month: Period) -> dict[str, Any]:
        """Foto del mes (guardada, o tomada ahora si el mes ya cerró y no existía)."""
        if month.id not in self._fotos:
            def consultar() -> tuple[dict[str, Any], list[dict[str, Any]]]:
                log.info("Consultando snapshot desde=%s corte=%s (foto del mes)", month.start, month.end)
                return self.client.snapshot(month.start, month.end), self.client.subscription_plans()

            foto, nueva = fotos.obtener(month, consultar, origen=self.origen)
            self._fotos[month.id] = foto
            meta = fotos.info(foto)
            self.queries.append({"desde": month.start.isoformat(), "corte": month.end.isoformat(),
                                 "total": str(meta["suscripciones"]),
                                 "fuente": "api (foto nueva)" if nueva else "foto guardada",
                                 "foto_tomada": meta["tomada_label"], "foto_tardia": str(meta["tardia"])})
            if meta["tardia"]:
                self.warn(f"La foto de {month.label} se tomó el {meta['tomada_label']}, después del cierre: el estado "
                          "es al corte, pero los planes y la ubicación son los de ese día.")
        return self._fotos[month.id]

    def catalog_for(self, desde: date, corte: date) -> PlanCatalog:
        month = fotos.month_of(desde, corte)
        if month is None:
            return self.catalog()
        if month.id not in self._catalogs:
            self._catalogs[month.id] = PlanCatalog(self.foto(month)["planes"])
        return self._catalogs[month.id]

    def snapshot(self, desde: date, corte: date) -> dict[str, Any]:
        month = fotos.month_of(desde, corte)
        if month is not None:
            return self.foto(month)["snapshot"]
        key = (desde, corte)
        if key not in self._snapshots:
            log.info("Consultando snapshot desde=%s corte=%s", desde, corte)
            self._snapshots[key] = self.client.snapshot(desde, corte)
            self.queries.append({"desde": desde.isoformat(), "corte": corte.isoformat(),
                                 "total": str(self._snapshots[key].get("total"))})
        return self._snapshots[key]

    def enriched(self, desde: date, corte: date) -> list[dict[str, Any]]:
        """Filas del snapshot con clasificación (_cls) y ubicación DANE (_geo)."""
        key = (desde, corte)
        if key in self._enriched:
            return self._enriched[key]
        rows = self.snapshot(desde, corte)["data"]
        catalog = self.catalog_for(desde, corte)
        if settings.AJUSTE_AL_CORTE:
            # Planes, estrato, ubicación y TV deshabilitada tal como estaban al corte (desde tabVersion).
            self.ajustes[corte.isoformat()] = al_corte.ajustar(
                rows, corte, self.events_after(corte), self.disabled_tv_now(), catalog, self.client)
        isp = {normalize_customer(c) for c in load_isp_customers()}
        locations = geo.resolve(rows)
        unknown: Counter[str] = Counter()
        for row, loc in zip(rows, locations):
            row["_cls"] = classify(row, catalog, isp)
            row["_geo"] = loc
            unknown.update(row["_cls"]["planes_desconocidos"])
        if unknown:
            self.warn(f"{len(unknown)} plan(es) no encontrados en el catálogo de ERPNext; se clasificaron por nombre.")
        self._enriched[key] = rows
        return rows


def geo_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    c = Counter(r["_geo"]["geo_fuente"] for r in rows)
    return {"por_coordenadas": c.get("coordenadas", 0), "por_ciudad": c.get("ciudad", 0),
            "por_defecto": c.get("por_defecto", 0)}


def load_template(filename: str) -> Workbook:
    return openpyxl.load_workbook(settings.TEMPLATES_DIR / filename)


def reset_sheet(ws: Worksheet) -> None:
    """Deja solo el encabezado (fila 1) con sus notas."""
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)


def write_rows(ws: Worksheet, rows: list[list[Any]], formats: dict[int, str] | None = None) -> None:
    formats = formats or {}
    for r_idx, values in enumerate(rows, start=2):
        for c_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            if c_idx in formats:
                cell.number_format = formats[c_idx]


def to_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def load_json_config(name: str) -> dict[str, Any]:
    with open(settings.CONFIG_DIR / name, encoding="utf-8") as fh:
        return json.load(fh)


def int_code(value: Any) -> int:
    return int(str(value))
