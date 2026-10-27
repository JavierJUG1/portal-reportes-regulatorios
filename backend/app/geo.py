"""Ubicación DANE (DIVIPOLA) de cada suscripción.

Orden de resolución:
1. Coordenadas dentro de una zona urbana del MGN 2025 → cabecera (clase 1) o centro poblado (clase 2).
2. Coordenadas fuera de zona urbana → rural disperso (clase 3) del municipio que las contiene + vereda DANE 2024.
3. Sin coordenadas válidas (o muy lejos del municipio declarado) → municipio según la ciudad, como cabecera.
"""
from __future__ import annotations

import hashlib
import logging
import pickle
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pyogrio
import shapely
from shapely import STRtree

from .config import settings

log = logging.getLogger("portal.geo")

ZU_PATH = settings.MGN_DIR / "MGN2025_URB_ZONA_URBANA" / "MGN_URB_ZONA_URBANA.shp"
CLASE_PATH = settings.MGN_DIR / "MGN2025_CLASE" / "MGN_TEM_CLASE.shp"
VEREDAS_PATH = settings.VEREDAS_DIR / "shp_CRVeredas_2024" / "shp_CRVeredas_2024.shp"

# Colombia (con margen) para descartar coordenadas imposibles.
LAT_RANGE = (-4.5, 13.6)
LON_RANGE = (-82.0, -66.0)
KM_PER_DEGREE = 111.32
CACHE_VERSION = 2


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    text = str(name).split(",")[0]
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text).upper()
    text = re.sub(r"\b(D C|DC|DISTRITO CAPITAL)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class GeoIndex:
    departments: list[str]
    zu_geoms: np.ndarray
    zu_attrs: list[tuple[str, int, int, str]]  # (mpio, clase, cp_codigo, cp_nombre)
    clase_geoms: np.ndarray
    clase_attrs: list[tuple[str, int]]  # (mpio, clase)
    ver_geoms: np.ndarray
    ver_attrs: list[tuple[int, str]]  # (codigo_vereda, nombre)
    mpio_by_name: dict[str, list[str]]
    mpio_label: dict[str, str]
    mpio_geom: dict[str, Any] = field(default_factory=dict)
    zu_tree: STRtree | None = None
    clase_tree: STRtree | None = None
    ver_tree: STRtree | None = None

    def build_trees(self) -> None:
        # Polígonos "preparados": la prueba punto-en-polígono es mucho más rápida.
        for arr in (self.zu_geoms, self.clase_geoms, self.ver_geoms):
            if len(arr):
                shapely.prepare(arr)
        self.zu_tree = STRtree(self.zu_geoms)
        self.clase_tree = STRtree(self.clase_geoms)
        self.ver_tree = STRtree(self.ver_geoms) if len(self.ver_geoms) else None


_index: GeoIndex | None = None
_index_lock = threading.Lock()


def _in_list(field_name: str, values: Iterable[str]) -> str:
    vals = ",".join(f"'{v}'" for v in values)
    return f"{field_name} IN ({vals})"


def _cache_path() -> Any:
    # Cambia si cambian los departamentos o las capas (ruta o fecha de modificación): el índice se reconstruye.
    parts = [str(CACHE_VERSION), ",".join(sorted(settings.GEO_DEPARTMENTS))]
    for path in (ZU_PATH, CLASE_PATH, VEREDAS_PATH):
        parts += [str(path), str(path.stat().st_mtime if path.exists() else 0)]
    key = "|".join(parts)
    digest = hashlib.sha1(key.encode()).hexdigest()[:12]
    return settings.GEO_CACHE_DIR / f"geo_index_{digest}.pkl"


def _build_index() -> GeoIndex:
    deps = settings.GEO_DEPARTMENTS
    log.info("Construyendo índice geográfico DANE para departamentos %s", deps)
    zu = pyogrio.read_dataframe(
        ZU_PATH, columns=["dpto_ccdgo", "mpio_cdpmp", "clas_ccdgo", "zu_cdivi", "zu_cnmbre"],
        where=_in_list("dpto_ccdgo", deps),
    )
    clase = pyogrio.read_dataframe(
        CLASE_PATH, columns=["dpto_ccdgo", "mpio_cdpmp", "clas_ccdgo"], where=_in_list("dpto_ccdgo", deps)
    )
    if VEREDAS_PATH.exists():
        ver = pyogrio.read_dataframe(
            VEREDAS_PATH, columns=["COD_DPTO", "DPTOMPIO", "CODIGO_VER", "NOMBRE_VER"],
            where=_in_list("COD_DPTO", deps),
        )
    else:
        ver = None
    # Nombres de municipio (todos los departamentos) desde las cabeceras.
    names_df = pyogrio.read_dataframe(
        ZU_PATH, columns=["dpto_ccdgo", "mpio_cdpmp", "clas_ccdgo", "zu_cnmbre"], read_geometry=False,
        where="clas_ccdgo = '1'",
    )
    mpio_by_name: dict[str, list[str]] = {}
    mpio_label: dict[str, str] = {}
    order = {d: i for i, d in enumerate(deps)}
    for _, r in names_df.sort_values(by="dpto_ccdgo", key=lambda s: s.map(lambda d: order.get(d, 99))).iterrows():
        code = str(r["mpio_cdpmp"])
        mpio_label.setdefault(code, str(r["zu_cnmbre"]))
        mpio_by_name.setdefault(normalize_name(r["zu_cnmbre"]), [])
        if code not in mpio_by_name[normalize_name(r["zu_cnmbre"])]:
            mpio_by_name[normalize_name(r["zu_cnmbre"])].append(code)

    mpio_geom = {}
    for code, grp in clase.groupby("mpio_cdpmp"):
        mpio_geom[str(code)] = shapely.union_all(grp.geometry.values)

    def _int(v: Any, default: int = 0) -> int:
        try:
            return int(str(v).strip())
        except (TypeError, ValueError):
            return default

    idx = GeoIndex(
        departments=list(deps),
        zu_geoms=np.asarray(zu.geometry.values),
        zu_attrs=[(str(r.mpio_cdpmp), _int(r.clas_ccdgo), _int(r.zu_cdivi), str(r.zu_cnmbre))
                  for r in zu.itertuples()],
        clase_geoms=np.asarray(clase.geometry.values),
        clase_attrs=[(str(r.mpio_cdpmp), _int(r.clas_ccdgo)) for r in clase.itertuples()],
        ver_geoms=np.asarray(ver.geometry.values) if ver is not None else np.asarray([]),
        ver_attrs=[(_int(r.CODIGO_VER, 98), str(r.NOMBRE_VER or "").strip()) for r in ver.itertuples()]
        if ver is not None else [],
        mpio_by_name=mpio_by_name,
        mpio_label=mpio_label,
        mpio_geom=mpio_geom,
    )
    return idx


def get_index() -> GeoIndex:
    global _index
    with _index_lock:
        if _index is not None:
            return _index
        cache = _cache_path()
        idx: GeoIndex | None = None
        if cache.exists():
            try:
                with open(cache, "rb") as fh:
                    idx = pickle.load(fh)
            except Exception:  # noqa: BLE001 - caché corrupta: se reconstruye
                idx = None
        if idx is None:
            idx = _build_index()
            idx.zu_tree = idx.clase_tree = idx.ver_tree = None
            cache.parent.mkdir(parents=True, exist_ok=True)
            with open(cache, "wb") as fh:
                pickle.dump(idx, fh, protocol=pickle.HIGHEST_PROTOCOL)
        idx.build_trees()
        _index = idx
        return idx


def municipio_por_ciudad(ciudad: str | None, idx: GeoIndex | None = None) -> str | None:
    idx = idx or get_index()
    codes = idx.mpio_by_name.get(normalize_name(ciudad))
    return codes[0] if codes else None


def _valid_coords(lat: Any, lon: Any) -> tuple[float, float] | None:
    try:
        lat_f, lon_f = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(lat_f) or not np.isfinite(lon_f) or (lat_f == 0 and lon_f == 0):
        return None
    if LAT_RANGE[0] <= lat_f <= LAT_RANGE[1] and LON_RANGE[0] <= lon_f <= LON_RANGE[1]:
        return lat_f, lon_f
    if LAT_RANGE[0] <= lon_f <= LAT_RANGE[1] and LON_RANGE[0] <= lat_f <= LON_RANGE[1]:
        return lon_f, lat_f  # latitud/longitud invertidas
    return None


def _first_hits(tree: STRtree | None, geoms: np.ndarray, pts: np.ndarray, n: int) -> np.ndarray:
    out = np.full(n, -1, dtype=np.int64)
    if tree is None or len(pts) == 0:
        return out
    pairs = tree.query(pts)  # candidatos por caja envolvente
    if pairs.shape[1] == 0:
        return out
    hit = shapely.intersects(geoms[pairs[1]], pts[pairs[0]])  # geometrías preparadas
    p_idx, g_idx = pairs[0][hit], pairs[1][hit]
    for p_i, g_i in zip(p_idx[::-1], g_idx[::-1]):  # al invertir, queda el primer acierto
        out[p_i] = g_i
    return out


def resolve(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Devuelve, por cada fila (con latitude/longitude/ciudad), su ubicación DANE."""
    idx = get_index()
    n = len(rows)
    coords: list[tuple[float, float] | None] = [_valid_coords(r.get("latitude"), r.get("longitude")) for r in rows]
    has = np.array([c is not None for c in coords])
    pts = np.array([shapely.Point(c[1], c[0]) if c else shapely.Point(0, 0) for c in coords], dtype=object)
    zu_hit = _first_hits(idx.zu_tree, idx.zu_geoms, pts, n)
    cl_hit = _first_hits(idx.clase_tree, idx.clase_geoms, pts, n)
    ver_hit = _first_hits(idx.ver_tree, idx.ver_geoms, pts, n)

    out: list[dict[str, Any]] = []
    default_mpio = settings.GEO_DEFAULT_MUNICIPIO
    for i, row in enumerate(rows):
        ciudad_mpio = municipio_por_ciudad(row.get("ciudad"), idx)
        res: dict[str, Any] | None = None
        if has[i] and (zu_hit[i] >= 0 or cl_hit[i] >= 0):
            if zu_hit[i] >= 0:
                mpio, clase, cp_code, cp_name = idx.zu_attrs[zu_hit[i]]
            else:
                mpio, clase = idx.clase_attrs[cl_hit[i]]
                cp_code, cp_name = 0, ""
                if clase != 3:  # polígono de clase sin zona urbana asociada: se trata como rural
                    clase = 3
            res = {"dane_municipio": mpio, "clase": clase, "cp_codigo": cp_code if clase == 2 else None,
                   "cp_nombre": cp_name if clase == 2 else None, "vereda_codigo": None, "vereda_nombre": None,
                   "geo_fuente": "coordenadas", "geo_nota": None}
            if clase == 3:
                if ver_hit[i] >= 0:
                    res["vereda_codigo"], res["vereda_nombre"] = idx.ver_attrs[ver_hit[i]]
                else:
                    res["vereda_codigo"], res["vereda_nombre"] = 98, None
            # Coordenada lejos del municipio declarado → se desconfía de ella.
            if ciudad_mpio and ciudad_mpio != mpio and ciudad_mpio in idx.mpio_geom:
                dist_km = idx.mpio_geom[ciudad_mpio].distance(pts[i]) * KM_PER_DEGREE
                if dist_km > settings.GEO_MAX_DISTANCE_KM:
                    res = None
                    nota = f"coordenada a {dist_km:.0f} km del municipio declarado"
                else:
                    nota = None
            else:
                nota = None
        else:
            nota = "sin coordenadas válidas" if not has[i] else "coordenada fuera de los departamentos cargados"
        if res is None:
            mpio = ciudad_mpio or default_mpio
            res = {"dane_municipio": mpio, "clase": 1, "cp_codigo": None, "cp_nombre": None,
                   "vereda_codigo": None, "vereda_nombre": None,
                   "geo_fuente": "ciudad" if ciudad_mpio else "por_defecto", "geo_nota": nota}
        res["dane_municipio_nombre"] = idx.mpio_label.get(res["dane_municipio"], "")
        out.append(res)
    return out
