# Runbook: Wipe + Reimport limpio (Contifico → Odoo 19)

## Diagnóstico del estado actual de Odoo

A partir del export `Last/Product Variant (product.product).csv` (27,564 variantes):

| Categoría | Plantillas | Variantes |
|---|---|---|
| Plantillas con `default_code` correcto | 1,538 | ~1,548 |
| Plantillas sin `default_code` (sin atributos duplicados) | 1,158 | ~3,140 |
| Plantillas con atributos duplicados (Talla×Talla, Manga×Manga) | **790** | **22,876 (fantasmas)** |
| Total | 3,486 | 27,564 |

**Causa raíz**: Odoo no desduplica `attribute_line_ids` al re-importar el mismo template ID. Si `odoo_product_templates_with_attributes.csv` se importó dos veces, las líneas de atributo se apilan y se genera el cartesiano duplicado (ej: 7×7×2×2 = 196 variantes en lugar de 14).

---

## Paso 1 — Archivar lo importado en Odoo

Tenés 4 CSVs listos en este mismo directorio. Importalos en Odoo (Menú → Settings → Import) en este orden:

### 1.1 (Recomendado) Archivar las 3,475 plantillas que importamos

Archivo: `archive_imported_product_templates.csv`

**Modelo**: `product.template` · **Modo**: Update existing records (matching by id)

```
id,active
__import__.product_template_xxx,False
...
```

Esto archiva los templates `__import__.product_template_*` y, en cascada, sus variantes. No toca las 6 plantillas pre-existentes (`__export__.*`).

### 1.2 (Alternativa más agresiva) Archivar también las 27,564 variantes

Archivo: `archive_all_product_products.csv`

**Modelo**: `product.product` · **Modo**: Update existing records

Útil si querés asegurar que ninguna variante quede activa por separado (ej. si la cascada del template no llega a algún registro huérfano).

### 1.3 (Opcional) Solo archivar las variantes sin SKU

Archivo: `archive_variants_without_default_code.csv` (26,016 filas)

Si querés conservar las 1,548 variantes que ya tienen `default_code` correcto y solo limpiar el resto. Útil si vas a hacer un reimport selectivo.

### 1.4 Diagnóstico (no importar)

Archivo: `diagnostic_templates_with_duplicate_attributes.csv` — listado de las 790 plantillas con atributos duplicados, para inspección manual si querés decidir caso por caso.

---

## Paso 2 — Reimportar Fase 1 limpia

Importá en Odoo (en este orden, **una sola vez cada uno**):

1. `odoo_product_templates_simple.csv` → modelo `product.template` (productos sin variantes)
2. `odoo_product_templates_with_attributes.csv` → modelo `product.template` (templates con atributos)

⚠️ **Crítico**: NO re-importes el mismo CSV dos veces. Cada import APENDÉ líneas de atributo y reaparece el problema. Si necesitás reintentar, archivá primero (Paso 1).

---

## Paso 3 — Exportar `product.product` desde Odoo

Después de la Fase 1 limpia:

1. En Odoo: Inventario → Productos (variantes) → seleccionar todos
2. Export: `id`, `default_code`, `barcode`, `name`, `product_template_variant_value_ids`, `lst_price`, `product_tmpl_id/id`, `product_tmpl_id/name`
3. Subir el CSV al endpoint `POST /odoo-migration/runs/{run_id}/phase2/merge` (campo `file`)

El servicio escribe:
- `odoo_product_variant_update_by_id_safe.csv` — actualización segura por id (asignación de `default_code`/`barcode`)
- `odoo_phase2_simples_for_unmatched.csv` — **NUEVO** (v1.5.12): SKUs que no matchearon como variantes se exportan como simples para preservarlos
- `odoo_phase2_merger_unmatched.csv` — diagnóstico

---

## Paso 4 — Aplicar SKUs y simples residuales

1. Importar `odoo_product_variant_update_by_id_safe.csv` → modelo `product.product` con Update existing (asigna `default_code` + `barcode`)
2. Importar `odoo_phase2_simples_for_unmatched.csv` → modelo `product.template` (crea simples para SKUs sin variante limpia)

Sobre los archivos del `Last/` que dejaste:
- 6,003 variantes recibirían SKU correctamente
- 238 SKUs se importarían como simples (ej: VE-ELA-LI-L, PT-25C29118-10/32)

---

## Paso 5 — Stock (cuando quieras)

Cuando quieras agregar stock, regenerá la corrida con `export_stock=true` y aplicá `odoo_stock_quant.csv` al modelo `stock.quant` (Inventory Adjustments).

---

## Cómo evitar el problema en el futuro

1. **Nunca re-importar Fase 1 sin archivar primero**. El bug es del lado Odoo, no del exportador.
2. Si necesitás corregir un template ya importado, archivá ese template específico antes de reimportarlo.
3. Mantené copias del `run_summary.json` para auditar qué se importó cuándo.
