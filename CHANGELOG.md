# Changelog

## 1.0.57 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.3.
- Nuevo comportamiento por defecto para duplicados en Fase 1: se conserva la primera ocurrencia y se ignoran duplicados posteriores (sin bloquear la migración).
- Nuevo modo estricto opcional (`strict_duplicate_errors=True`) para mantener el comportamiento anterior de error duro en duplicados.
- Se agregan métricas al `run_summary.json`: `total_duplicados_ignorados` y `strict_duplicate_errors`.


## 1.0.58 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.4.
- Se agrega script de simulación `backend/simulate_raw_log_analysis.py` para procesar `raw.log` y resumir errores/recomendaciones usando los CSV generados.

## 1.0.59 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.5.
- Duplicados en Fase 1 vuelven a modo estricto por defecto (`strict_duplicate_errors=True`) para no ocultar problemas de calidad de datos.
- Nuevo fallback para Fase 2: variantes sin atributos válidos pueden exportarse como simples (`fallback_orphan_variants_to_simple=True`) en lugar de perderse.
- Se añade `fallback_orphan_variants_to_simple` al `run_summary.json`.

## 1.0.60 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.6.
- Se agrega guardarraíl en Fase 2 para detectar y deduplicar por (`product_tmpl_id/id`, `Variant Values`) antes de exportar `odoo_product_variant_internal_references.csv`.
- Se reportan nuevas validaciones de riesgo para prevenir el error de unicidad de Odoo `product_product_combination_unique`.
- Se genera en `docs/odoo_import_templates/Last` un CSV saneado de variantes (`odoo_product_variant_internal_references_clean.csv`) listo para importación segura.

## 1.0.61 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.7.
- Se elimina el artefacto pesado `odoo_product_variant_internal_references_clean.csv` del repo (debe generarse por corrida, no versionarse).
- Nuevo script `backend/build_safe_variant_update_csv.py` para construir un CSV de actualización segura por `id` + `Internal Reference` + `Barcode` sin tocar `Variant Values` (evita que Odoo recalcule `combination_indices=''`).

## 1.0.62 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.8.
- Se elimina el flujo apoyado en `docs/odoo_import_templates/Last` para artefactos auxiliares; la operación queda centrada en archivos del `run_id` generado desde frontend.
- Descarga de archivos de run mejorada: se reemplaza whitelist rígida por validación segura de ruta/extensión (`.csv`, `.log`, `.md`, `.json`) para evitar que archivos generados en nuevas fases aparezcan pero no se puedan descargar.
- Se agregan a la respuesta estándar de archivos los outputs `odoo_phase2_simples_minimal.csv` y `odoo_phase2_simples_unmatched.csv` cuando existan.

## 1.0.63 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.9.
- Se agrega salida alias en cada `run_id`: `odoo_product_variant_update_by_id_safe.csv` (mismo contenido que `odoo_phase2_with_odoo_ids_minimal.csv`) para facilitar operación.
- Se expone este archivo en los links del frontend/API (`_build_files` y respuesta de `/runs/{run_id}/phase2/merge`).

## 1.0.64 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.10.
- Se genera `odoo_product_variant_update_by_id_safe.csv` desde el momento de creación del run (placeholder con header), para que siempre exista en descargas aun antes de ejecutar `/phase2/merge`.
- Al ejecutar `/phase2/merge`, ese archivo se rellena con las filas matched por `id` para importación segura.

## 1.0.65 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.11.
- Mejora crítica en `/phase2/merge`: si no hay match por `(template_id + variant_values)` ni por `(template_name + variant_values)`, ahora se aplica fallback por SKU (`Internal Reference` ↔ `default_code` del export de Odoo).
- Esto evita casos de `odoo_product_variant_update_by_id_safe.csv` vacío cuando Odoo exporta variantes con `product_template_variant_value_ids` distintos o vacíos.

## 1.0.66 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.12.
- Normalización defensiva de barcode en `product_internal_reference_update.csv`: corrige el patrón `.../O{talla}` cuando el SKU es `.../{talla}` para evitar códigos como `512961-025/O36`.
- El ajuste se aplica tanto para productos simples como variantes antes de detección de conflictos de barcode.

## 1.0.67 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.13.
- Corrección de regla de normalización de barcode: `.../O{talla}` ahora se corrige a `.../{talla}` (sin insertar `0`), p.ej. `512961-025/O36 -> 512961-025/36`.
- Se evita modificar códigos válidos fuera de ese patrón exacto.
