# Portal de Sastrería

Versión 1.0.12

Repositorio reorientado para migrar de Contífico a Odoo de manera ordenada. Conserva el frontend y una API FastAPI ya integrada con gran parte de la funcionalidad operativa, y ahora prioriza la extracción, normalización y carga de datos críticos hacia Odoo.


## Enfoque actual: Migrador Contífico → Odoo

A partir de la **versión 0.2.0**, este repositorio pasa a enfocarse en la migración de datos de negocio desde Contífico hacia Odoo.

Prioridades iniciales de migración:
- Clientes (contactos y datos fiscales).
- Productos y servicios.
- Facturas y movimientos clave para continuidad operativa.

La estrategia será incremental, con etapas de mapeo de datos, validaciones y sincronización controlada para minimizar riesgos en producción.

## Requisitos

### Backend
- Python 3.10+
- Entorno virtual recomendado

### Frontend
- Cualquier servidor web estático (por ejemplo `python -m http.server`)

## Puesta en marcha

### 1. Preparar el backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

Define la clave secreta JWT en un archivo `.env` dentro de la carpeta `backend` (o como
variable de entorno) antes de iniciar la API. En ese mismo archivo puedes configurar las
credenciales de Contífico (`CONTIFICO_API_KEY` y `CONTIFICO_API_TOKEN`) si deseas usar la
integración:

```bash
cat <<'EOF' > .env
SECRET_KEY="pon-aqui-una-clave-de-al-menos-32-caracteres"
# Credenciales de Contífico
CONTIFICO_API_KEY="tu-api-key"
CONTIFICO_API_TOKEN="tu-api-token"
EOF
# También puedes exportarla directamente:
export SECRET_KEY="pon-aqui-una-clave-de-al-menos-32-caracteres"
# export CONTIFICO_API_KEY="tu-api-key"
# export CONTIFICO_API_TOKEN="tu-api-token"
```

#### Límites para la búsqueda de facturas en Contífico

Para evitar cargar el catálogo completo de facturas en memoria, la descarga se realiza en
bloques y se persiste a disco. Estos parámetros se pueden ajustar con variables de entorno:

- `CONTIFICO_INVOICE_CATALOG_PAGE_SIZE` (predeterminado: `100`): cuántas facturas se
  solicitan por página.
- `CONTIFICO_INVOICE_CATALOG_MAX_PAGES` (predeterminado: `200`): número máximo de páginas
  a recorrer.
- `CONTIFICO_INVOICE_CATALOG_MAX_RECORDS` (predeterminado: `20000`, usa `0` o `None` para
  desactivar): cantidad máxima de facturas a descargar antes de detener la búsqueda.
- `CONTIFICO_INVOICE_CATALOG_STOP_ON_FIRST_MATCH` (predeterminado: `true`): detiene la
  descarga del catálogo en cuanto se encuentra la factura buscada.

Al buscar una factura, el cliente elimina de memoria las páginas que ya fueron persistidas,
manteniendo sólo las coincidencias necesarias para continuar con la consulta.

La aplicación fallará con un mensaje descriptivo si `SECRET_KEY` no está definida o es
demasiado corta.

Para verificar que la integración con Contífico está lista, asegúrate de contar con ambos
valores proporcionados por Contífico (la API Key y el API Token del punto de venta). Si
faltan, los endpoints que dependan de Contífico responderán con un error `503` indicando
que la integración no está configurada.

Crear el primer usuario administrador:

```bash
python create_admin.py --username admin --password cambialo --full-name "Administrador"
```

Si necesitas crear un usuario inicial con otro rol, añade la opción `--role` con uno de
los valores disponibles (`admin`, `sales`, `tailor`). El valor predeterminado es
`admin`.

Poblar la base de datos con información de ejemplo (opcional):

```bash
python seed_database.py --reset --yes --users 6 --customers 20 --orders 25
```

Argumentos útiles del comando:

- `--reset`: vacía las tablas antes de insertar los datos ficticios (pide confirmación a menos que se utilice `--yes`).
- `--users`, `--customers`, `--orders`: controlan cuántos usuarios, clientes y órdenes se generan (valores predeterminados: 5, 15 y 20 respectivamente).
- `--yes`: omite la confirmación interactiva para el borrado de datos.

Al finalizar, se mostrará un resumen con los registros creados y las credenciales generadas para los nuevos usuarios.

Iniciar la API:

```bash
python -m app.main
```

Por defecto el servidor escucha en `127.0.0.1:8000`. Para exponerlo en otro host o
puerto (por ejemplo al desplegar en un servidor), define las variables de entorno
`API_HOST`, `API_PORT` y opcionalmente `API_RELOAD` en tu `.env` o antes de ejecutar
el comando. Ejemplo para escuchar en todas las interfaces:

```bash
export API_HOST=0.0.0.0
export API_PORT=8000
python -m app.main
```

La documentación interactiva estará disponible en `http://<host>:<puerto>/docs`.

### Posibles causas de caída o bloqueo en el VPS

- **Falta de variables críticas**: si `SECRET_KEY` no está definida o tiene menos de 32
  caracteres, la API detendrá el arranque con un error descriptivo. Ajusta la variable en
  `.env` o en el entorno antes de iniciar el servicio.
- **Problemas de disco**: el backend usa SQLite por defecto (`sastreria.db`) y persiste
  cachés de facturas de Contífico en `./data`. Ambos requieren permisos de escritura y
  espacio libre suficiente; un disco lleno o de solo lectura impedirá escribir y puede
  forzar la caída del proceso de aplicación o del servidor de la base de datos.
- **Recursos saturados**: aunque las descargas del catálogo de Contífico ahora se podan y
  persisten por página, tamaños de página y límites de registros demasiado altos, o
  tiempos de espera muy amplios, pueden consumir CPU/ RAM o hilos hasta provocar que el
  proceso sea terminado por el sistema operativo. Ajusta los límites mediante las
  variables de entorno documentadas arriba para mantener el consumo controlado.

### 2. Preparar el frontend

El frontend es una SPA ligera sin dependencias externas. Desde la carpeta `frontend` ejecuta:

```bash
python -m http.server 5173
```

Luego visita `http://localhost:5173` en tu navegador. Asegúrate de que el backend esté funcionando en `http://localhost:8000`.


### Ejecutar Fase 2 (stock por bodega) después de la Fase 1

1. Ejecuta la exportación inicial (Fase 1) y guarda el `run_id` de la respuesta:

```bash
curl -X POST "http://127.0.0.1:8000/odoo-migration/products-stock/export?export_stock=false"
```

2. Inicia el worker de stock (Fase 2) usando ese `run_id`:

```bash
curl -X POST "http://127.0.0.1:8000/odoo-migration/runs/<RUN_ID>/stock/start"
```

3. Monitorea progreso detallado (pendientes, completados, fallidos, porcentaje, ETA):

```bash
curl "http://127.0.0.1:8000/odoo-migration/runs/<RUN_ID>/stock/status"
```

4. Si necesitas pausar/reanudar:

```bash
curl -X POST "http://127.0.0.1:8000/odoo-migration/runs/<RUN_ID>/stock/pause"
curl -X POST "http://127.0.0.1:8000/odoo-migration/runs/<RUN_ID>/stock/resume"
```

5. Si hubo fallidos, reintenta solo los errores:

```bash
curl -X POST "http://127.0.0.1:8000/odoo-migration/runs/<RUN_ID>/stock/retry-failed"
```

6. Descarga resultados parciales/finales:

```bash
curl -O "http://127.0.0.1:8000/odoo-migration/runs/<RUN_ID>/files/initial_stock.csv"
curl -O "http://127.0.0.1:8000/odoo-migration/runs/<RUN_ID>/files/stock_errors.csv"
```

## Roles disponibles

- **Administrador**: crear usuarios, gestionar clientes y órdenes, consultar la bitácora y eliminar registros.
- **Vendedor**: crear clientes, registrar nuevas órdenes y actualizar sus datos.
- **Sastre**: consultar clientes y órdenes, actualizar los arreglos y estados (sin crear órdenes).

## Funcionalidades principales

- Consulta pública del estado de una orden por número de orden **o** cédula del cliente.
- Catálogo reutilizable de clientes con teléfono y conjuntos de medidas guardadas.
- Gestión interna de órdenes: creación (según rol), actualización de estado, notas y asignación de sastre.
- Aplicación rápida de las medidas guardadas del cliente al generar una orden.
- Bitácora de auditoría inmutable accesible para administradores.
- Gestión de usuarios con control de permisos (Administrador, Vendedor, Sastre).

## Estructura del proyecto

```
backend/       # API FastAPI + SQLAlchemy + SQLite
frontend/      # Portal HTML/JS/CSS
```

## Variables útiles

Si necesitas cambiar la URL del backend para el frontend, define `API_BASE_URL` antes de cargar `app.js`:

```html
<script>
  window.API_BASE_URL = 'http://tu-servidor:8000';
</script>
<script src="app.js"></script>
```

## Comandos recomendados

| Acción | Comando |
|--------|---------|
| Ejecutar pruebas manuales | `uvicorn app.main:app --reload` |
| Servir frontend | `python -m http.server 5173` |

¡Listo! Ya puedes gestionar las órdenes de tu sastrería y ofrecer a tus clientes un portal de consulta.


## Historial de cambios

- **1.0.12 (2026-05-03)**: Se rediseñó el frontend para operar por pestañas (Fase 1 / Fase 2 / Preview), incorporando controles directos para iniciar/monitorear/pausar/reanudar/reintentar la Fase 2 desde UI.
- **1.0.11 (2026-05-03)**: Se documentó el procedimiento operativo para disparar la Fase 2 de stock tras la Fase 1, incluyendo endpoints `start/status/pause/resume/retry-failed` y descarga de `initial_stock.csv`/`stock_errors.csv`.
- **1.0.10 (2026-05-03)**: Se añadió worker de stock por corrida (`stock_worker.py`) con procesamiento por lotes/concurrencia configurable (`STOCK_BATCH_SIZE`, `STOCK_MAX_CONCURRENCY`, `STOCK_RPS_LIMIT`), retries con backoff+jitter para errores 429/5xx, checkpoints por batch (`stock_state.json`, `initial_stock.csv`) y endpoints de control/estado (`start`, `status`, `retry-failed`, `pause`, `resume`) más `stock_errors.csv`.
- **1.0.9 (2026-05-03)**: Se separó la exportación en 2 fases en `OdooMigrationService`: (1) snapshot de productos y cierre de `product_product.csv` sin bloquearse por stock por bodega, (2) enriquecimiento progresivo de stock por `id` de producto con estado persistente por item (`stock_state.json`) y snapshot intermedio (`products_snapshot.jsonl`).
- **1.0.8 (2026-05-03)**: Se amplió `config/warehouse_catalog.json` con el cruce de códigos/nombres de bodegas Contífico hacia ubicaciones Odoo (incluyendo BSR/OFA/BMT/B2/BW/BM/BTL), y la exportación de stock ahora soporta estas ubicaciones en `initial_stock.csv`.
- **1.0.7 (2026-05-03)**: Se añadió catálogo de bodegas por ID de Contífico (`config/warehouse_catalog.json`) y mapeo de stock por `bodega_id`/nombre/código con fallback a endpoint `/producto/<ID>/stock/` para mayor precisión.
- **1.0.6 (2026-05-03)**: Se añadió regla de agrupación BIG SIZE (`BG`) para variantes del mismo código madre, alias de marca `ANTONY MORATO/MORATO`, endpoint de stock por ID (`/temp/contifico/products/{id}/stock`) y mapping configurable de bodegas Contífico→Odoo (`config/warehouse_mapping.json`).
- **1.0.5 (2026-05-03)**: Se agregó regla prioritaria: si SKU inicia con `ZP-` se clasifica como Zapatos (Hombres/Mujeres según contexto DAMA/MUJER).
- **1.0.4 (2026-05-03)**: Se incorporó plantilla `adams_products_template.csv` con columna de categoría, mejora de detección Hombre/Mujer y ajuste de regla de stock 0 para excluir productos cuando todas las variantes del código madre tienen stock 0.
- **1.0.3 (2026-05-02)**: Se corrigió `router.py` para eliminar argumentos/keys duplicadas en endpoints de export y estabilizar el arranque en producción (fix de SyntaxError).
- **1.0.2 (2026-05-02)**: Se dejó la exportación enfocada en productos con `export_stock=false` por defecto, manteniendo `initial_stock.csv` para fase posterior cuando se complete el mapeo de bodegas Contífico→Odoo.
- **1.0.1 (2026-05-02)**: Se corrigió cálculo de stock usando fallback `cantidad_stock` cuando no hay detalle por bodega y se aplicó regla de grupo: incluir variantes de un código madre si alguna variante tiene stock > 0.
- **1.0.0 (2026-05-02)**: Refactor del parser/exportador con reglas configurables (`config/*.json`), clasificación ampliada por familias, exclusión automática de stock total 0 a `excluded_zero_stock.csv`, y enriquecimiento de `mapping_report.csv` con confidence/parser_rule/estado.
- **0.9.7 (2026-05-02)**: Se agregó `raw.log` por corrida con respuestas en crudo de cada fetch paginado a Contífico, además de `debug.log`.
- **0.9.6 (2026-05-02)**: Se añadió soporte para atributo `Ancho Corbata` y parsing de SKUs de corbatas (código estándar o `codigo/ancho`) en categoría `Ropa / Corbatas`.
- **0.9.5 (2026-05-02)**: Se agregó exportación de trazas por fetch en `debug.log` por corrida (páginas consultadas y conteos de respuesta), descargable desde el flujo de migración.
- **0.9.4 (2026-05-02)**: Se ajustó el límite por defecto de exportación a `max_pages=200` (antes 50) y se agregó metadata de corrida (`pages_fetched`, `hit_max_pages`) para detectar truncamientos de inventario.
- **0.9.3 (2026-05-02)**: Se añadió exportación por jobs con polling de progreso real (páginas e items procesados) y feedback en frontend durante la carga de inventario.
- **0.9.2 (2026-05-02)**: Se mejoró la UX del frontend de migración con feedback de progreso, estados descriptivos durante exportación y controles deshabilitados mientras se procesa.
- **0.9.1 (2026-05-02)**: Se separó el módulo Odoo de este repositorio para mantener arquitectura desacoplada (ETL/CSV aquí, staging Odoo en repo externo).
- **0.9.0 (2026-05-02)**: Se añadió un módulo Odoo `adams_csv_import_staging` para receptar CSV de inventario/stock en staging y se actualizaron validaciones de plantillas a `adams_product_template.csv` y `adams_stock_template.csv`.
- **0.8.0 (2026-05-02)**: Se agregó flujo de migración operable desde frontend con botones para generar CSV de productos+stock, listar corridas y descargar archivos por run (`/odoo-migration/runs/*`).
- **0.7.1 (2026-05-02)**: Se agregó validación estricta de columnas contra la plantilla `docs/odoo_import_templates/product_product_template.csv` antes de exportar CSV de productos.
- **0.7.0 (2026-05-02)**: Se creó el módulo separado `odoo_migration` con parser SKU ADAMS y exportación de CSV (`product_product`, `initial_stock`, `migration_errors`, `mapping_report`) desde Contífico en modo solo lectura.
- **0.6.5 (2026-05-02)**: Se eliminó el requisito de autenticación en endpoints temporales `/temp/contifico/*` para uso operativo del migrador y se estableció `https://api.adams.com.ec` como base URL por defecto del frontend.
- **0.6.4 (2026-05-02)**: Se eliminó el manejo de token Bearer en la vista previa del migrador para operar sin capas de autenticación adicionales, y se ajustó el mensaje de error de conectividad.
- **0.6.3 (2026-05-02)**: Se ajustó la vista previa para usar puerto API por defecto 9000 y se retiró el flujo de login en frontend según operación actual (token manual opcional).
- **0.6.2 (2026-05-02)**: Se añadió login directo en la vista previa de Contífico (`/auth/login`) con guardado de token, para recuperar el flujo funcional sin copiar token manual en cada prueba.
- **0.6.1 (2026-05-02)**: Se corrigió la configuración de conexión del frontend Contífico (vista previa) para usar `window.API_BASE_URL` o detectar `http://<host>:8000`, persistir base URL en navegador y mostrar errores claros de conectividad.
- **0.6.0 (2026-05-02)**: Se restauró el enfoque de “Contífico (vista previa)” en frontend con tarjetas funcionales para productos, categorías, producto puntual, bodegas y facturas, usando endpoints `/temp/contifico/*`.
- **0.5.0 (2026-05-02)**: Se creó un frontend de testing de API que carga automáticamente todos los métodos desde `/openapi.json`, permite ejecutar requests con token Bearer y exportar comando cURL.
- **0.4.0 (2026-05-02)**: Se simplificó el frontend para dejar únicamente funcionalidades relacionadas al migrador Contífico → Odoo (transformación JSON, vista previa tabular y descarga CSV).
- **0.3.0 (2026-05-02)**: Se agregó la base del migrador Contífico → Odoo con parsing de SKU (terno/camisa), mapeo de stocks por bodega (BPU/TUR/BAT) y pruebas unitarias iniciales.
- **0.2.0**: Reorientación documental del repositorio hacia migración Contífico → Odoo.


## Migración Odoo (fase CSV)

Se agregó el endpoint `POST /odoo-migration/products-stock/export` para generar archivos CSV revisables desde datos de Contífico (solo lectura):

- `product_product.csv`
- `initial_stock.csv`
- `migration_errors.csv`
- `mapping_report.csv`

Los archivos se guardan en `backend/data/odoo_migration/<timestamp>/`.


## Repositorio del módulo Odoo (separado)

El módulo Odoo de staging/importación se mantiene en un repositorio independiente:

- https://github.com/IlPicasso/Modulo-Odoo-A-Contifico

Este repositorio (`ContificoToOdoo`) queda dedicado al pipeline de extracción y generación de CSV revisables.
