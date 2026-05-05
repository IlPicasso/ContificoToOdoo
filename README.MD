# Migrador ContificoToOdoo

Versión 1.0.51

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
# Opcional: usar API v2 solo para productos
# CONTIFICO_PRODUCTS_API_BASE_URL="https://api.contifico.com/sistema/api/v2"
EOF
# También puedes exportarla directamente:
export SECRET_KEY="pon-aqui-una-clave-de-al-menos-32-caracteres"
# export CONTIFICO_API_KEY="tu-api-key"
# export CONTIFICO_API_TOKEN="tu-api-token"
# export CONTIFICO_PRODUCTS_API_BASE_URL="https://api.contifico.com/sistema/api/v2"
```

Nota: en API v2 de productos la paginación documentada usa `page` (100 ítems por página),
por lo que el cliente evita enviar `page_size/result_page/result_size` en ese modo.
Además, la respuesta de v2 puede venir envuelta en `{count,next,previous,results}` y el
cliente ya consume `results` automáticamente.

Parámetros recomendados para mitigar throttling/timeouts en descargas largas:
- `CONTIFICO_PRODUCTS_PAGE_DELAY_SECONDS` (default `1.0`)
- `CONTIFICO_PRODUCTS_PAGE_RETRY_ATTEMPTS` (default `5`)
- `CONTIFICO_PRODUCTS_PAGE_RETRY_BACKOFF_BASE_SECONDS` (default `1.5`)
- `CONTIFICO_PRODUCTS_PAGE_RETRY_JITTER_SECONDS` (default `0.4`)

En modo API v2 también se registra en el resumen el `count` reportado por Contífico como
`expected_min_items_from_api`, para comparar rápidamente si la corrida trajo un mínimo
coherente de ítems (`fetched_items_meet_expected_min`).

Para Fase 1 se recomienda trabajar con `page_size=100` y `max_pages=300` (cobertura de hasta
30,000 productos en API v2).

Cada RUN guarda su propio `run_summary.json` dentro de la carpeta del run con, al menos:
- total de productos extraídos
- productos excluidos por stock 0
- duración total de la corrida (segundos)

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



### Precheck Odoo de atributos (desde frontend)

Antes de generar CSV con atributos adicionales, usa el botón **Precheck de atributos Odoo** en la pestaña **Fase 1**.

Campos requeridos:
- `config/odoo_catalog_snapshot.json`: snapshot local de categorías y atributos actuales en Odoo para precheck offline sin API.

Flujo recomendado (sin API Odoo):

1. Exporta desde Odoo dos CSV manuales (una columna con nombre por fila):
   - atributos
   - categorías
2. En frontend (Fase 1), usa:
   - **Actualizar snapshot atributos (CSV)**
   - **Actualizar snapshot categorías (CSV)**
3. El frontend llama:

```bash
POST /odoo-migration/odoo-attributes/snapshot/upload?kind=attributes
POST /odoo-migration/odoo-attributes/snapshot/upload?kind=categories
GET /odoo-migration/odoo-attributes/precheck-offline
```

Si responde `can_enable_brand_color_export=true`, puedes marcar **Incluir atributos adicionales (Marca/Color) en Product Values** y exportar.
Además revisa `categories_missing`: esa lista indica exactamente qué categorías crear en Odoo para migrar productos sin fricción.
Si faltan atributos o categorías, corrige primero en Odoo y vuelve a correr el precheck.

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

- **1.0.54 (2026-05-05)**: Se restauró deduplicación determinística en `odoo_variant_sku_mapping.csv` por combinación de atributos dentro del template para evitar errores de Odoo `product_product_combination_unique`; los SKUs repetidos por combinación ahora se reportan en `odoo_duplicate_variant_combinations.csv` con referencias descartadas para revisión.
- **1.0.53 (2026-05-05)**: Se corrigió el manejo de corbatas con sufijo slash no-ancho (ej. `CORBATA-BC/2013`) para no forzar `Talla`/`Ancho Corbata`; ahora se marcan `UNPARSED` y no contaminan validación template/variantes. También se aplica la misma regla de normalización de corbatas al construir templates para mantener consistencia con variant mapping.
- **1.0.52 (2026-05-05)**: Se saneó la fusión de atributos parseados/raw para evitar contaminar `Talla` y `Ancho Corbata` con SKUs completos o códigos inválidos (ej. `CIN-C-ML`, `MR-10845-1/7`), corrigiendo fallos de validación `template/variantes` en ejecución de API.
- **1.0.51 (2026-05-05)**: Se corrigió el parser de parent_key para SKUs con talla al final separada por guion (ej. `VE-MICAELA-AZ-XL`, `VE-ELA-STP-M`), evitando crear templates por SKU completo y eliminando la inconsistencia `template/variantes` en validación.
- **1.0.50 (2026-05-05)**: Se agregó regla explícita para corbatas (`Ropa / Hombres / Corbatas` o nombre con `CORBATA`): cualquier valor numérico en `Talla` se migra a `Ancho Corbata`, `Talla` se limpia y el ancho se normaliza con unidad (`cm`) como **Ancho Corbata (talla) cm**. Además, en `odoo_variant_sku_mapping.csv` ahora se deduplica por combinación (`Product Template External ID` + `Talla/Color/Manga de Camisa/Ancho Corbata/Marca`), se reportan duplicados detectados y se valida consistencia cruzada contra atributos permitidos en `odoo_product_templates.csv` (falla temprano si una variante llena columnas no declaradas por template).
- **1.0.49 (2026-05-05)**: Se corrigió clasificación por prefijo SKU para evitar que `ZP-`/`PT-`/`CH-` salgan como `Terno` en productos madre/variantes; ahora `ZP` genera nombre `Zapato`, `PT` genera `Pantalon`, `CH` genera `Chaleco`, y además se agrega categoría `Ropa / Hombres / Chaleco`. También se normalizan marcas en formato título (ej. `Bruno Cassini`) en exportaciones.
- **1.0.45 (2026-05-04)**: Se movió el filtrado de stock 0 a Fase 1 (manteniendo la regla de grupo por variantes con stock), y se incorporó mapeo explícito 100% determinístico `categoria_id Contífico -> categoría Odoo` mediante configuración (`config/contifico_category_to_odoo.json`) para evitar heurísticas cuando la categoría viene solo por ID.
- **1.0.44 (2026-05-04)**: Se agregó mapeo explícito de categorías de Contífico por `categoria_id` para detectar categoría Odoo con mayor precisión cuando el listado de productos no trae nombre de categoría, y se añadió salida `unmapped_categories.csv` por run para revisión manual de IDs no mapeados.
- **1.0.34 (2026-05-04)**: Se corrigió el caso real de Contífico donde la respuesta HTTP puede venir con `status=404` pero body `{"code":"400","error":"Pagina fuera del rango"}`; ahora también se interpreta como fin de paginación para no cancelar la exportación.
- **1.0.33 (2026-05-04)**: Se robusteció el manejo de paginación agotada de Contífico también en `ContificoClient.list_products` (no solo en el servicio de migración), interpretando el `400` con `Pagina fuera del rango` como lista vacía para evitar abortos en exportaciones.
- **1.0.32 (2026-05-04)**: El fetch paginado de productos ahora interpreta el 400 de Contífico `{"code":"400","error":"Pagina fuera del rango"}` como fin de paginación (no como error fatal), evitando cancelar corridas cuando se solicita una página inexistente.
- **1.0.32 (2026-05-05)**: Se refactorizó el agrupamiento de variantes con parser central `derive_parent_and_attrs` (reglas BG/DC, tallas con slash y corbatas con ancho en cm), se dejó de deduplicar silenciosamente el mapeo de variantes y se agregaron reportes `odoo_duplicate_variant_combinations.csv` y `odoo_missing_products_for_stock.csv`.
- **1.0.31 (2026-05-04)**: Se corrigió el corte prematuro del fetch paginado cuando entraba fallback de `page_size`; ahora la condición de fin usa el tamaño efectivo de página y evita truncar resultados (ej. alrededor de ~6600 ítems).
- **1.0.30 (2026-05-04)**: Se añadió procesamiento directo de `raw.log`/JSON subido desde frontend para generar la corrida de migración sin fetchear nuevamente Contífico mientras se diagnostican límites/timeouts de paginación.
- **1.0.29 (2026-05-04)**: Se añadió fallback de `page_size` al fetchear productos de Contífico (ej. 200→100→50→25) cuando hay `ContificoTransportError`, para reducir fallas por timeout en páginas pesadas.
- **1.0.28 (2026-05-04)**: Se añadieron reintentos automáticos con backoff para `ReadTimeout` en llamadas HTTP a Contífico, reduciendo fallas transitorias al fetchear catálogos/productos.
- **1.0.27 (2026-05-04)**: Se reforzó el comportamiento por fases: en Fase 1 (`export_stock=false`) no se hace procesamiento de stock por producto ni exclusión por stock 0; la lógica/filas de stock quedan para Fase 2 (`export_stock=true`).
- **1.0.26 (2026-05-04)**: Las salidas de importación de variantes ahora se generan dentro de cada `run` (descargables al final desde la API) en vez de escribirse en `docs/odoo_import_outputs`, evitando confusión y manteniendo todos los artefactos por corrida en un solo lugar.
- **1.0.25 (2026-05-04)**: Se estandarizó el nombre del atributo de corbata a `Ancho Corbata` (sin "de") en precheck y salidas de variantes para que coincida con el nombre real en Odoo.
- **1.0.24 (2026-05-03)**: Se añadió exportación orientada a productos madre+variantes hacia `docs/odoo_import_outputs` con archivos `01_product_templates_with_existing_attributes.csv`, `02_variant_update_map.csv`, `03_stock_quant_by_variant.csv`, `04_missing_attribute_values_report.csv` y reporte `import_products_and_variants_report.md`.
- **1.0.23 (2026-05-03)**: Se generalizó el control de atributos opcionales en frontend/backend con `include_additional_attributes` (manteniendo compatibilidad con `include_brand_color_attributes`) para reflejar que el flujo contempla más atributos y no solo un check aislado de Marca/Color.
- **1.0.22 (2026-05-03)**: Se agregó fallback de categoría a `Sin Categoria` cuando no existe match en reglas/aliases, para permitir importación continua y posterior reclasificación manual en Odoo.
- **1.0.21 (2026-05-03)**: Se reforzó la detección de categorías por género (HOMBRE/MUJER/NIÑO) en el parser para priorizar rutas por género en importación, reduciendo ambigüedad en categorías genéricas.
- **1.0.20 (2026-05-03)**: Se corrigió el precheck offline para interpretar snapshots de atributos exportados con columnas CSV (ej. `Secuencia,Atributo,...`) y para considerar equivalencias de categorías (`Ropa / Camisas|Corbatas|Ternos` vs rutas por género), evitando falsos faltantes.
- **1.0.19 (2026-05-03)**: Se eliminó la dependencia de precheck online por API Odoo; ahora el flujo usa solo precheck offline y actualización manual de `odoo_catalog_snapshot.json` mediante carga de CSV desde frontend.
- **1.0.18 (2026-05-03)**: Se añadió precheck offline (`/odoo-migration/odoo-attributes/precheck-offline`) usando `config/odoo_catalog_snapshot.json` para validar atributos/categorías faltantes sin conectarse a la API de Odoo.
- **1.0.17 (2026-05-03)**: El precheck Odoo ahora reporta atributos faltantes (`attributes_missing`) y categorías faltantes (`categories_missing`) para dar feedback exacto de qué crear antes de migrar productos.
- **1.0.16 (2026-05-03)**: Se añadió precheck por API contra Odoo (`/odoo-migration/odoo-attributes/precheck`) para validar atributos `Marca` y `Color`, con integración en frontend (Fase 1) para activar/desactivar automáticamente el modo de exportación de atributos.
- **1.0.15 (2026-05-03)**: Se agregó parámetro `include_brand_color_attributes` (default `false`) en exportación Odoo para habilitar opcionalmente `Marca` y `Color` dentro de `Product Values` solo cuando esos atributos existan en la base destino; modo seguro por defecto evita `KeyError` en importación.
- **1.0.14 (2026-05-03)**: Se removió la exportación de atributos `Marca` y `Color` dentro de `Product Values` para evitar errores `KeyError` en importación de productos Odoo cuando esos atributos no existen en la base destino; se mantiene SKU como llave operativa para producto/stock.
- **1.0.13 (2026-05-03)**: Se migró la validación de plantillas a los templates oficiales de Odoo (`product_product_template.csv` y `stock_quant.csv`), se añadió salida `stock_quant.csv` para inventario físico y se reforzó el resumen final con métricas de consistencia SKU↔stock por `Internal Reference`.
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


## Exportación Odoo 19 (productos con variantes)

Desde la versión 1.0.46 se generan adicionalmente tres CSV en cada RUN:
1. `attributes_values.csv`
2. `products_with_variants.csv`
3. `stock_quant.csv`

Orden de importación recomendado en Odoo:
1) Attributes/Values, 2) Products with variants, 3) Stock por ajuste físico.

Nota: si necesitas controlar SKU/barcode/precio estrictamente por variante en Odoo, puede requerirse una cuarta importación futura específica de variantes.
