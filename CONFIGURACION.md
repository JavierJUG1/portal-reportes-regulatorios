# Configuración del portal

Datos de configuración del *Portal de reportes regulatorios · CRC y MinTIC*. Las instrucciones de instalación y uso están en el [README](README.md).

> **Secretos**: las claves (`ERPNEXT_API_SECRET`, `ERPNEXT_API_KEY`, `OAUTH_CLIENT_SECRET`, `SECRET_KEY`) **no** están en este repositorio. Viven solo en `backend/.env` del equipo donde corre el portal. Si una clave se expone, hay que regenerarla en ERPNext (o cambiar `SECRET_KEY`) y actualizar `backend/.env`.

## Resumen

| Dato | Valor |
|---|---|
| Portal (local) | http://localhost:8000 (un proceso sirve API y frontend) |
| Backend | Python · FastAPI · APScheduler · openpyxl |
| Frontend | React 18 · Vite · TypeScript (compilado en `frontend/dist`) |
| ERPNext | https://next.gigafibra.co (Frappe v14) · empresa `GIGA FIBRA SAS` |
| Fuente de datos | `GET /api/method/monthly_subscription_snapshot?desde=AAAA-MM-DD&corte=AAAA-MM-DD&company=GIGA FIBRA SAS` (Server Script *API Monthly Subscription Snapshot*) |
| Inicio de sesión | ERPNext como proveedor OAuth2 → Office 365 (Social Login Key `office_365`) |
| Zona horaria | America/Bogota |
| Reportes | F6 y T1.2 (trimestrales), cortes de suscripciones (mensual) |
| Archivos generados | `backend/storage/<reporte>/<año>/` · registro en `backend/data/portal.db` |

## ERPNext

### OAuth Client del portal (inicio de sesión)

*Integrations → OAuth Client*:

| Campo | Valor |
|---|---|
| App Name | `Portal reportes regulatorios` |
| Skip Authorization | ✔ |
| Grant Type | `Authorization Code` |
| Response Type | `Code` |
| Scopes | `openid all` |
| Redirect URIs | `http://localhost:8000/api/auth/callback` (y `https://<host-del-portal>/api/auth/callback` al publicarlo, separadas por espacio) |
| Default Redirect URI | la del entorno donde corre el portal |

*Client ID* → `OAUTH_CLIENT_ID`; *App Client Secret* → `OAUTH_CLIENT_SECRET`.

### Usuario de API

Usuario de ERPNext cuya API key / secret van en `ERPNEXT_API_KEY` / `ERPNEXT_API_SECRET`. Necesita:

| Permiso | Para qué |
|---|---|
| Ejecutar `monthly_subscription_snapshot` | Suscripciones de cada corte |
| Leer *Subscription Plan* | Clasificar planes (Internet, TV, velocidad, costo) |
| Leer *User* | Verificar el rol System Manager de quien intenta generar |

Prueba: `backend\.venv\Scripts\python -m scripts.check_erpnext` (desde `backend/`).

## Variables de entorno (`backend/.env`)

`backend/.env.example` es la plantilla. Valores actuales:

### General

| Variable | Valor | Descripción |
|---|---|---|
| `APP_ENV` | `development` | `production` al publicar con HTTPS (cookies seguras y etiqueta PRODUCCIÓN) |
| `SECRET_KEY` | *(secreto)* | Firma la sesión del portal; cadena larga y aleatoria |
| `TIMEZONE` | `America/Bogota` | Zona horaria de cortes y programación |

### ERPNext

| Variable | Valor | Descripción |
|---|---|---|
| `ERPNEXT_URL` | `https://next.gigafibra.co` | Instancia de ERPNext |
| `ERPNEXT_API_KEY` | *(secreto)* | API key del usuario de API |
| `ERPNEXT_API_SECRET` | *(secreto)* | API secret del usuario de API |
| `ERPNEXT_COMPANY` | `GIGA FIBRA SAS` | Empresa enviada al snapshot |
| `SNAPSHOT_METHOD` | `monthly_subscription_snapshot` | Método del Server Script |
| `ERPNEXT_TIMEOUT` | `300` | Segundos máximos por consulta |
| `DATA_SOURCE` | `erpnext` | Fuente de datos |

### Inicio de sesión y permisos

| Variable | Valor | Descripción |
|---|---|---|
| `AUTH_MODE` | `erpnext` | Inicio de sesión con ERPNext + Office 365 |
| `OAUTH_CLIENT_ID` | *(del OAuth Client)* | Client ID del OAuth Client del portal |
| `OAUTH_CLIENT_SECRET` | *(secreto)* | App Client Secret del OAuth Client |
| `OAUTH_REDIRECT_URI` | `http://localhost:8000/api/auth/callback` | Debe ser exactamente una de las Redirect URIs |
| `OAUTH_SCOPES` | `openid all` | Alcances solicitados |
| `SESSION_HOURS` | `12` | Duración de la sesión del portal |
| `ALLOWED_EMAIL_DOMAINS` | `gigafibra.co` | Dominios que pueden entrar |
| `ALLOWED_ROLES` | *(vacío)* | Vacío = cualquier usuario del dominio; o lista de roles de ERPNext |
| `GENERATE_ROLES` | `System Manager` | Roles que pueden generar reportes |
| `ROLE_CACHE_SECONDS` | `300` | Cada cuánto se vuelve a consultar el rol en ERPNext |

### Reportes y programación

| Variable | Valor | Descripción |
|---|---|---|
| `ENABLED_REPORTS` | `f6,t12,cortes` | Reportes del portal |
| `SCHEDULER_ENABLED` | `true` | Generación automática |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` | `23` / `50` | Hora de cierre (último día del mes y del trimestre) |
| `CATCH_UP_ON_START` | `true` | Al arrancar, genera lo que quedó pendiente |
| `HISTORY_START` | `2025-01` | Primer periodo listado en el portal |
| `STORAGE_BACKEND` | `local` | Archivos en `backend/storage/` |

### Reglas de los reportes

| Variable | Valor | Descripción |
|---|---|---|
| `F6_STATUSES` | `Active,Past Due Date,Unpaid` | Estados al corte que cuentan en el F6 |
| `F6_EXCLUDE_OWN_USE` | `false` | El F6 incluye las cuentas de uso propio |
| `F6_TECNOLOGIA` | `5` | TIPO_TECNOLOGIA del F6 (IPTV por fibra) |
| `T12_SHEETS` | `accesos` | Pestañas del T1.2 que se llenan (más `INFO`) |
| `T12_STATUSES` | `Active,Past Due Date,Unpaid,Temporarily Suspended,Trialling` | Estados que cuentan como acceso en el T1.2 |
| `T12_TECNOLOGIA_INTERNET` | `108` | ID_TECNOLOGIA_ACCESO del T1.2 (FTTH) |
| `INCLUDE_FREE_TV` | `true` | TV incluida sin costo cuenta como TV en el T1.2 (el F6 cuenta solo TV paga) |
| `SPEED_SOURCE` | `contratada` | Velocidad del nombre del plan (`aprovisionada` = la configurada en ERPNext) |
| `OWN_USE_CUSTOMER_PATTERN` | `GIGA\s*FIBRA` | Clientes de uso propio (segmento 109 del T1.2) |

### Geografía DANE

| Variable | Valor | Descripción |
|---|---|---|
| `GEO_DEPARTMENTS` | `11,25` | Departamentos: Bogotá y Cundinamarca |
| `GEO_MAX_DISTANCE_KM` | `15` | Si la coordenada está más lejos del municipio declarado, se usa la ciudad |
| `GEO_DEFAULT_MUNICIPIO` | `11001` | Municipio si no hay coordenadas ni ciudad reconocida |
| `MGN_DIR` / `VEREDAS_DIR` | `dane/MGN2025_DANE` / `dane/VEREDAS_DANE_2024` | Capas DANE |

## Capas DANE (`dane/`)

| Capa | Contenido en el repositorio |
|---|---|
| MGN 2025 · Zona urbana | Completa (todo el país; también da los nombres de municipio) |
| MGN 2025 · Clase | Solo departamentos 11 y 25 |
| Veredas DANE 2024 | Solo departamentos 11 y 25 |

Las capas completas de clase y veredas superan el límite de 100 MB por archivo de GitHub, por eso se recortaron a los departamentos de `GEO_DEPARTMENTS`; el resultado de los reportes es idéntico. Para agregar otros departamentos: descargar las capas completas del DANE (MGN 2025 y Capa de referencia de veredas 2024), apuntar `MGN_DIR` / `VEREDAS_DIR` a ellas y ampliar `GEO_DEPARTMENTS`.

## Archivos de configuración (`backend/config/`)

| Archivo | Uso |
|---|---|
| `clientes_isp.json` | Clientes ISP (venta mayorista): no se reportan como accesos en el T1.2 |

## Qué no está en el repositorio

| Ruta | Motivo |
|---|---|
| `backend/.env` | Claves y configuración del equipo |
| `backend/data/` | Base de versiones y caché geográfica (se recrean) |
| `backend/storage/` | Excel generados: los cortes tienen datos de clientes |
| `frontend/node_modules/`, `frontend/dist/` | Dependencias y compilado (`npm install`, `npm run build`) |
| `MGN2025_DANE/`, `VEREDAS_DANE_2024/` | Capas DANE completas (solo locales) |

## Puesta en marcha en otro equipo

1. Clonar el repositorio e instalar (README, sección 1).
2. Crear `backend/.env` desde `backend/.env.example` con las claves de ERPNext, el OAuth Client y una `SECRET_KEY` nueva.
3. Registrar la Redirect URI del nuevo equipo en el OAuth Client de ERPNext.
4. `npm run build` en `frontend/` y arrancar con `backend/scripts/serve.py`.
5. Los Excel generados no viajan con el repositorio: copiar `backend/storage/` y `backend/data/portal.db` del equipo anterior, o generarlos de nuevo desde el portal.
