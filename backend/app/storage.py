"""Almacenamiento de los Excel generados.

- LocalStorage (por defecto): backend/storage/<reporte>/<año>/<archivo>.xlsx
- ERPNextStorage: sube el archivo como File privado en ERPNext (/api/method/upload_file, is_private=1)
  y lo descarga con las credenciales del servicio. Pensado para el paso a producción.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from .config import settings
from .erpnext import ERPNextError


class LocalStorage:
    name = "local"

    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.STORAGE_DIR)

    def save(self, report: str, year: int, filename: str, data: bytes) -> str:
        key = f"{report}/{year}/{filename}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return key

    def read(self, key: str) -> bytes:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise FileNotFoundError(key)
        return path.read_bytes()


class ERPNextStorage:
    name = "erpnext"

    def _client(self) -> httpx.Client:
        if not settings.ERPNEXT_API_KEY or not settings.ERPNEXT_API_SECRET:
            raise ERPNextError("Faltan las credenciales de ERPNext para guardar el archivo.")
        return httpx.Client(
            base_url=settings.ERPNEXT_URL,
            headers={"Authorization": f"token {settings.ERPNEXT_API_KEY}:{settings.ERPNEXT_API_SECRET}"},
            timeout=120,
        )

    def save(self, report: str, year: int, filename: str, data: bytes) -> str:
        with self._client() as http:
            resp = http.post(
                "/api/method/upload_file",
                data={"is_private": "1", "folder": settings.ERPNEXT_FILE_FOLDER, "file_name": filename},
                files={"file": (filename, data,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        if resp.status_code >= 400:
            raise ERPNextError("No se pudo guardar el archivo en ERPNext.", f"{resp.status_code}: {resp.text[:300]}")
        file_url = (resp.json().get("message") or {}).get("file_url")
        if not file_url:
            raise ERPNextError("ERPNext no devolvió la ubicación del archivo guardado.")
        return file_url

    def read(self, key: str) -> bytes:
        with self._client() as http:
            resp = http.get(key)
        if resp.status_code >= 400:
            raise FileNotFoundError(key)
        return resp.content


def get_storage() -> LocalStorage | ERPNextStorage:
    return ERPNextStorage() if settings.STORAGE_BACKEND == "erpnext" else LocalStorage()
