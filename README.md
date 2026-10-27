# Portal de reportes regulatorios · CRC y MinTIC

Portal interno de Gigafibra para consultar, generar y descargar en Excel:

| Reporte | Formato | Periodicidad | Generación automática |
|---|---|---|---|
| **Reporte F6** | Res. 00175 – F6. Suscriptores y asociados de televisión cerrada | Trimestral (detalle por mes) | Último día del trimestre, 23:50 |
| **Reporte T1.2** | Res. 7811 – T.1.2 Formato unificado ISP (pestaña de accesos) | Trimestral | Último día del trimestre, 23:50 |
| **Cortes de suscripciones** | Estado de todas las suscripciones al cierre del mes, ligado a su trimestre | Mensual | Último día del mes, 23:50 |

Diseño: Figma *Gigafibra-web → 🗂 Portal reportes regulatorios · CRC y MinTIC*. Datos de configuración: [CONFIGURACION.md](CONFIGURACION.md).

```
backend/      API FastAPI + generación de Excel (Python)
  app/          código del portal
  config/       clientes ISP (clientes_isp.json)
  templates/    plantillas CRC originales (F6 y T1.2)
  scripts/      arranque y herramientas de línea de comandos
  data/         base de versiones (portal.db) y caché de geografía   ← no borrar
  storage/      archivos Excel generados                             ← no borrar
frontend/     React + Vite + TypeScript
dane/         capas DANE (MGN 2025 y veredas 2024) para ubicar centros poblados y veredas
```

## 1. Instalación (Windows)

Requisitos: Python 3.11+ y Node 20+.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env      # solo la primera vez; luego completar (ver 2 y 3)

cd ..\frontend
npm install
```

## 2. Configuración (`backend/.env`)

`backend/.env.example` es la plantilla; [CONFIGURACION.md](CONFIGURACION.md) tiene todas las variables y sus valores. Las principales:

| Variable | Valor actual | Para qué |
|---|---|---|
| `ERPNEXT_URL` | `https://next.gigafibra.co` | ERPNext de Gigafibra |
| `ERPNEXT_API_KEY` / `ERPNEXT_API_SECRET` | usuario de API (ver 9) | Consultar datos y roles en ERPNext |
| `AUTH_MODE` | `erpnext` | Inicio de sesión con ERPNext + Office 365 |
| `OAUTH_CLIENT_ID` / `OAUTH_CLIENT_SECRET` | del OAuth Client (ver 3) | Inicio de sesión |
| `OAUTH_REDIRECT_URI` | `http://localhost:8000/api/auth/callback` | Regreso desde ERPNext |
| `ALLOWED_EMAIL_DOMAINS` | `gigafibra.co` | Quién puede entrar |
| `GENERATE_ROLES` | `System Manager` | Quién puede generar reportes |
| `ENABLED_REPORTS` | `f6,t12,cortes` | Reportes del portal |
| `SCHEDULE_HOUR` / `SCHEDULE_MINUTE` | `23` / `50` | Hora de la generación automática |
| `STORAGE_BACKEND` | `local` | Archivos en `backend/storage/` |

Después de cambiar `backend/.env` hay que reiniciar el servidor.

## 3. Inicio de sesión con Office 365 (ERPNext)

El portal usa ERPNext como proveedor OAuth2 y ERPNext inicia sesión con Office 365 (mismo esquema de *Mapa Despacho · Gestión*).

**OAuth Client en ERPNext** (*Integrations → OAuth Client → New*, una sola vez):

| Campo | Valor |
|---|---|
| App Name | `Portal reportes regulatorios` |
| Skip Authorization | ✔ (entra directo si ya hay sesión en ERPNext) |
| Grant Type | `Authorization Code` |
| Response Type | `Code` |
| Scopes | `openid all` |
| Redirect URIs | `http://localhost:8000/api/auth/callback` (al publicar el portal, agregar `https://<host-del-portal>/api/auth/callback`, separadas por espacio) |
| Default Redirect URI | la del entorno donde corre el portal |

Luego copiar *Client ID* y *App Client Secret* a `OAUTH_CLIENT_ID` y `OAUTH_CLIENT_SECRET`. `OAUTH_REDIRECT_URI` debe ser exactamente una de las *Redirect URIs*. Al publicar con HTTPS, usar también `APP_ENV=production` (cookies seguras).

**Cómo entra un usuario**
1. Al abrir el portal sin sesión, se le redirige a ERPNext.
2. Si ya tiene sesión en ERPNext, vuelve al portal sin hacer nada. Si no, inicia sesión en ERPNext con *Office 365* y vuelve.
3. Llega a la página que había pedido (p. ej. `/reportes/f6`). La sesión del portal dura 12 horas (`SESSION_HOURS`).
4. "Cerrar sesión" cierra solo el portal; para volver a entrar se usa el botón "Continuar con ERPNext · Office 365".

Pueden entrar los usuarios de ERPNext con correo `@gigafibra.co` (`ALLOWED_ROLES` permite limitarlo a ciertos roles).

## 4. Compilar y arrancar

```powershell
cd frontend
npm run build                 # genera frontend/dist, que sirve el backend

cd ..
backend\.venv\Scripts\python backend\scripts\serve.py --host 0.0.0.0 --port 8000
```

Un solo proceso sirve la API y el portal en http://localhost:8000. Hay que volver a compilar el frontend cada vez que cambie `frontend/src`. Con `--env-file ruta\otro.env` se arranca con otra configuración sin tocar `backend/.env`.

**El servidor debe quedar encendido**: la generación automática corre dentro de este proceso.

## 5. Generación de reportes

- **Automática** (zona America/Bogota):
  - Último día de cada mes, 23:50 → corte de suscripciones del mes.
  - Último día de marzo, junio, septiembre y diciembre, 23:50 → F6 y T1.2 del trimestre, y los cortes del trimestre que falten.
  - Al arrancar el servidor: genera el último periodo cerrado de cada reporte si no tiene archivo, y los cortes que falten del trimestre anterior y del actual (por si el servidor estaba apagado al cierre).
- **Desde el portal** (solo System Manager): "Descargar Excel" en un periodo cerrado sin archivo lo genera y lo descarga; el ícono ⟳ junto a la versión genera una nueva versión con los datos actuales de ERPNext; "Reintentar" en un periodo con error.
- **Versiones**: cada generación crea una versión (v1, v2…). La más reciente es *Vigente*; las anteriores quedan *Reemplazadas* y siguen descargables en **Historial**.
- **Quién generó**: las automáticas se muestran como **"Generado por el sistema"**; las demás, con el nombre del usuario.
- **Archivos**: `backend/storage/<reporte>/<año>/` y su registro en `backend/data/portal.db`.

## 6. Permisos

| Acción | Quién |
|---|---|
| Consultar y descargar | Cualquier usuario con sesión |
| Generar (periodos sin archivo, nuevas versiones, reintentos) | Solo usuarios con el rol **System Manager** en ERPNext |

El rol se consulta en ERPNext con la API key del portal y se recuerda 5 minutos (`ROLE_CACHE_SECONDS`): dar o quitar el rol en ERPNext se refleja en ese plazo. Si ERPNext no responde, no se permite generar. Quien no tiene el rol ve "Requiere System Manager" en lugar de los botones de generar, y su menú de usuario dice "Consulta y descarga".

## 7. Contenido de los reportes

**Fuente de datos**: `GET /api/method/monthly_subscription_snapshot?desde=AAAA-MM-DD&corte=AAAA-MM-DD` (Server Script *API Monthly Subscription Snapshot*), tal cual lo entrega la API para cada corte, más el catálogo de *Subscription Plan*.
- F6 y cortes: una consulta por mes (`desde` = día 1, `corte` = último día del mes).
- T1.2: `desde` = inicio del trimestre, `corte` = último día del trimestre.

**Plantillas**: las plantillas CRC originales (`backend/templates/`) se conservan intactas (hojas, notas de cada columna y hoja `INFO`); solo se escriben las filas de datos.

**Ubicación DANE**: con las coordenadas de la suscripción se busca la zona urbana MGN 2025 (cabecera = clase 1, centro poblado = clase 2 con su código de 8 dígitos). Fuera de zona urbana es rural disperso (clase 3) con su vereda DANE 2024. Sin coordenadas válidas, o a más de 15 km del municipio declarado, se usa la ciudad de la suscripción como cabecera municipal.

### F6 – Suscriptores de TV cerrada

| Columna | Regla |
|---|---|
| ANNO / TRIMESTRE / MES_DEL_TRIMESTRE | Del periodo; un grupo de filas por cada mes del trimestre |
| CODIGO_DANE_MUNICIPIO | DIVIPOLA según la ubicación |
| CODIGO_DANE_CENTRO_POBLADO | Código del centro poblado; `0` en cabecera o rural |
| NOMBRE_CENTRO_POBLADO | Nombre DANE del centro poblado; en rural, la vereda; `0` en cabecera |
| MODALIDAD_SERVICIO_TELEVISION | `1` Televisión por suscripción |
| SEGMENTO | Estrato 1–6, `7` corporativo, `8` sin estratificar, `9` sin ánimo de lucro (cliente corporativo con nombre de fundación, asociación, corporación, JAC, iglesia…) |
| TIPO_TECNOLOGIA | `5` IPTV por fibra |
| NUMERO_TOTAL_CONEXIONES | Suscripciones con **TV paga** (plan de TV con costo > 0; no cuenta "Giga Fibra TV - Free") en estado *Active*, *Past Due Date* o *Unpaid* al último día del mes. Incluye las cuentas de uso propio |

### T1.2 – Formato unificado ISP

El archivo lleva la pestaña `T1_2_ISP_ACCESOS` y la hoja de control `INFO`. Accesos al último día del trimestre en estado *Active*, *Past Due Date*, *Unpaid*, *Temporarily Suspended* o *Trialling*; no incluye a los clientes ISP de `config/clientes_isp.json` (venta mayorista).

| Columna | Regla |
|---|---|
| ID_MUNICIPIO / ID_CLASE | Según la ubicación DANE |
| ID_CENTRO_POBLADO | Código de 8 dígitos si es centro poblado; `99` en cabecera o rural |
| ID_VEREDA | Código de vereda si es rural; `98` si no tiene código; `99` si no aplica |
| ID_SEGMENTO | `101`–`106` estratos, `107` corporativo, `108` sin estratificar, `109` uso propio (cliente GIGA FIBRA) |
| ID_SERVICIO_PAQUETE | `1` Internet, `3` TV, `5` Duo Play 2 (Internet + TV). La TV incluida sin costo cuenta como TV |
| VELOCIDAD_EFECTIVA_DOWN/UPSTREAM | Velocidad **contratada** del nombre del plan ("250 Mbps" → 250, "1Gbps" → 1000); la subida conserva la proporción configurada en ERPNext. Si el nombre no trae velocidad, se usa la configurada en ERPNext. `0` si no incluye Internet |
| ID_TECNOLOGIA_ACCESO | `108` FTTH si incluye Internet; `999` si no aplica |
| CANTIDAD_LINEAS_ACCESOS | Suscripciones con la misma combinación |
| VALOR_TOTAL_PLAN_TARIFARIO | Costo sin IVA de los planes recurrentes de la suscripción (sin reconexión, traslado ni visitas) |

### Cortes de suscripciones (mensual)

Libro interno con dos hojas:
- **Resumen**: parámetros de la consulta; relación con el trimestre (trimestre, mes 1-3 = `MES_DEL_TRIMESTRE` del F6, suscriptores que entran al F6 y accesos que entran al T1.2); suscriptores F6 por estado; totales por estado, municipio, servicio y segmento; origen de la ubicación.
- **Suscripciones**: todas las suscripciones del corte con ubicación DANE y clasificación, más las columnas **Cuenta en F6** y **Cuenta en T1.2** (encabezado naranja), calculadas con las mismas reglas de esos reportes: al filtrar "Sí" se obtiene exactamente lo que suma cada uno.

**Relación con el trimestre**: los meses 1, 2 y 3 del trimestre son el `MES_DEL_TRIMESTRE` 1, 2 y 3 del F6, y el corte del mes 3 es la base de los accesos del T1.2. En el portal, cada trimestre del F6 y del T1.2 muestra sus 3 cortes, y cada corte muestra el F6 y el T1.2 de su trimestre. Una marca verde indica que los totales cuadran; una alerta indica que difieren (por ejemplo, si se regeneró uno de los dos con datos más nuevos).

## 8. Herramientas (desde `backend/`)

```powershell
# Probar la conexión con ERPNext: credenciales, endpoint, planes y roles (no genera nada)
.venv\Scripts\python -m scripts.check_erpnext

# Generar un periodo a mano (queda como "Generado por el sistema")
.venv\Scripts\python -m scripts.generate f6 2026-T3
.venv\Scripts\python -m scripts.generate t12 2026-T3
.venv\Scripts\python -m scripts.generate cortes 2026-09

# Eliminar versiones (registro + archivo). Sin --yes solo muestra lo que borraría.
.venv\Scripts\python -m scripts.purge_versions --report f6 --period 2026-T3 --yes
```

## 9. Usuario de API en ERPNext

`ERPNEXT_API_KEY` / `ERPNEXT_API_SECRET` de un usuario con permiso para:
- ejecutar el método `monthly_subscription_snapshot`;
- leer *Subscription Plan*;
- leer *User* (para verificar el rol System Manager de quien intenta generar).
