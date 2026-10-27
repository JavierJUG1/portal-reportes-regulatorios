"""Configuración del portal (variables de entorno + backend/.env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
PROJECT_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "si", "sí", "on")


def _list(name: str, default: str = "") -> list[str]:
    raw = _env(name, default) or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def _path(name: str, default: Path) -> Path:
    value = _env(name)
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else (BASE_DIR / p).resolve()


class Settings:
    # Entorno
    APP_ENV = _env("APP_ENV", "development")
    ENV_LABEL = _env("ENV_LABEL", "PRODUCCIÓN" if APP_ENV == "production" else "DESARROLLO")
    TIMEZONE = _env("TIMEZONE", "America/Bogota")
    SECRET_KEY = _env("SECRET_KEY", "dev-only-change-me")
    CORS_ORIGINS = _list("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    FRONTEND_DIST = _path("FRONTEND_DIST", PROJECT_DIR / "frontend" / "dist")

    # ERPNext
    ERPNEXT_URL = (_env("ERPNEXT_URL", "https://next.gigafibra.co") or "").rstrip("/")
    ERPNEXT_API_KEY = _env("ERPNEXT_API_KEY")
    ERPNEXT_API_SECRET = _env("ERPNEXT_API_SECRET")
    ERPNEXT_COMPANY = _env("ERPNEXT_COMPANY", "GIGA FIBRA SAS")
    ERPNEXT_TIMEOUT = float(_env("ERPNEXT_TIMEOUT", "300"))
    SNAPSHOT_METHOD = _env("SNAPSHOT_METHOD", "monthly_subscription_snapshot")

    # Fuente de datos: "erpnext" (API real) o "fixture" (archivos JSON para pruebas locales)
    DATA_SOURCE = _env("DATA_SOURCE", "erpnext")
    FIXTURE_DIR = _path("FIXTURE_DIR", BASE_DIR / "fixtures")

    # Autenticación: "debug" (login local) o "erpnext" (SSO OAuth2 de ERPNext → Office 365)
    AUTH_MODE = _env("AUTH_MODE", "debug")
    SESSION_HOURS = int(_env("SESSION_HOURS", "12"))
    OAUTH_CLIENT_ID = _env("OAUTH_CLIENT_ID")
    OAUTH_CLIENT_SECRET = _env("OAUTH_CLIENT_SECRET")
    OAUTH_REDIRECT_URI = _env("OAUTH_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
    OAUTH_SCOPES = _env("OAUTH_SCOPES", "openid all")
    ALLOWED_EMAIL_DOMAINS = _list("ALLOWED_EMAIL_DOMAINS", "gigafibra.co")
    ALLOWED_ROLES = _list("ALLOWED_ROLES", "")  # vacío = cualquier usuario del dominio
    POST_LOGIN_REDIRECT = _env("POST_LOGIN_REDIRECT", "/")
    # Roles de ERPNext que pueden generar reportes desde el portal (los demás solo consultan y descargan).
    # Se verifican contra ERPNext con la API key del portal y se recuerdan ROLE_CACHE_SECONDS.
    GENERATE_ROLES = _list("GENERATE_ROLES", "System Manager")
    ROLE_CACHE_SECONDS = int(_env("ROLE_CACHE_SECONDS", "300"))
    FIXTURE_USER_ROLES = _list("FIXTURE_USER_ROLES", "System Manager")  # solo con DATA_SOURCE=fixture

    # Almacenamiento de archivos: "local" (carpeta del proyecto) o "erpnext" (File privado en ERPNext)
    STORAGE_BACKEND = _env("STORAGE_BACKEND", "local")
    STORAGE_DIR = _path("STORAGE_DIR", BASE_DIR / "storage")
    ERPNEXT_FILE_FOLDER = _env("ERPNEXT_FILE_FOLDER", "Home")
    DB_PATH = _path("DB_PATH", BASE_DIR / "data" / "portal.db")

    # Plantillas CRC
    TEMPLATES_DIR = _path("TEMPLATES_DIR", BASE_DIR / "templates")
    TEMPLATE_F6 = "F6_suscriptores_tv_cerrada.xlsx"
    TEMPLATE_T12 = "T1_2_formato_unificado_ISP.xlsx"
    CONFIG_DIR = _path("CONFIG_DIR", BASE_DIR / "config")

    # Geografía DANE
    # Capas DANE del repositorio (dane/): zona urbana MGN 2025 completa, y clase MGN 2025 y veredas 2024 recortadas a
    # GEO_DEPARTMENTS (11 y 25). Para otros departamentos, apuntar MGN_DIR / VEREDAS_DIR a las capas completas.
    MGN_DIR = _path("MGN_DIR", PROJECT_DIR / "dane" / "MGN2025_DANE")
    VEREDAS_DIR = _path("VEREDAS_DIR", PROJECT_DIR / "dane" / "VEREDAS_DANE_2024")
    GEO_CACHE_DIR = _path("GEO_CACHE_DIR", BASE_DIR / "data" / "geo_cache")
    GEO_DEPARTMENTS = _list("GEO_DEPARTMENTS", "11,25")
    GEO_MAX_DISTANCE_KM = float(_env("GEO_MAX_DISTANCE_KM", "15"))
    GEO_DEFAULT_MUNICIPIO = _env("GEO_DEFAULT_MUNICIPIO", "11001")  # si no hay coordenadas ni ciudad reconocida

    # Reportes habilitados en el portal: f6 y t12 (trimestrales) y cortes (mensual, ligado a su trimestre)
    ENABLED_REPORTS = _list("ENABLED_REPORTS", "f6,t12,cortes")

    # Programación automática (último día del mes / trimestre)
    SCHEDULER_ENABLED = _bool("SCHEDULER_ENABLED", True)
    SCHEDULE_HOUR = int(_env("SCHEDULE_HOUR", "23"))
    SCHEDULE_MINUTE = int(_env("SCHEDULE_MINUTE", "50"))
    CATCH_UP_ON_START = _bool("CATCH_UP_ON_START", True)
    HISTORY_START = _env("HISTORY_START", "2025-01")  # primer periodo listado (AAAA-MM)

    # Reglas regulatorias
    INCLUDE_FREE_TV = _bool("INCLUDE_FREE_TV", True)  # TV incluida sin costo cuenta como servicio de TV
    # Con "Disabled TV" (custom_disabled_tv = 1) al corte, la TV no se cuenta como TV (solo aplica si AJUSTE_AL_CORTE)
    EXCLUDE_DISABLED_TV = _bool("EXCLUDE_DISABLED_TV", False)
    # Reconstruir planes, estrato, ubicación y TV deshabilitada al día de corte desde tabVersion.
    # Desactivado: se usa tal cual lo que entrega la API para el corte (criterio de Regulatorio, 26/10/2026).
    AJUSTE_AL_CORTE = _bool("AJUSTE_AL_CORTE", False)
    # Velocidad reportada en T1.2: "contratada" (nombre del plan) o "aprovisionada" (configuración ERPNext)
    SPEED_SOURCE = (_env("SPEED_SOURCE", "contratada") or "contratada").lower()
    F6_TECNOLOGIA = int(_env("F6_TECNOLOGIA", "5"))  # 5 = IPTV por fibra
    T12_TECNOLOGIA_INTERNET = int(_env("T12_TECNOLOGIA_INTERNET", "108"))  # 108 = FTTH
    F6_STATUSES = _list("F6_STATUSES", "Active,Past Due Date,Unpaid")
    # Excluir del F6 las cuentas de uso propio (cliente "GIGA FIBRA ..."); por defecto se cuentan, como la API
    F6_EXCLUDE_OWN_USE = _bool("F6_EXCLUDE_OWN_USE", False)
    # Pestañas del T1.2 que se llenan: ingresos, accesos, quejas. Las demás se quitan del archivo
    # (la hoja INFO de control de la CRC siempre se conserva). Criterio de Regulatorio: solo accesos.
    T12_SHEETS = _list("T12_SHEETS", "accesos")
    T12_STATUSES = _list("T12_STATUSES", "Active,Past Due Date,Unpaid,Temporarily Suspended,Trialling")
    OWN_USE_CUSTOMER_PATTERN = _env("OWN_USE_CUSTOMER_PATTERN", r"GIGA\s*FIBRA")
    NONPROFIT_PATTERN = _env(
        "NONPROFIT_PATTERN",
        r"\b(FUNDACI[OÓ]N|ASOCIACI[OÓ]N|CORPORACI[OÓ]N|JUNTA DE ACCI[OÓ]N|IGLESIA|PARROQUIA|COOPERATIVA)\b",
    )


settings = Settings()
