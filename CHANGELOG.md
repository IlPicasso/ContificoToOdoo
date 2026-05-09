# Changelog

## 1.0.57 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.3.
- Nuevo comportamiento por defecto para duplicados en Fase 1: se conserva la primera ocurrencia y se ignoran duplicados posteriores (sin bloquear la migración).
- Nuevo modo estricto opcional (`strict_duplicate_errors=True`) para mantener el comportamiento anterior de error duro en duplicados.
- Se agregan métricas al `run_summary.json`: `total_duplicados_ignorados` y `strict_duplicate_errors`.


## 1.0.58 - 2026-05-09
- Exportador Odoo actualizado a versión 1.5.4.
- Se agrega script de simulación `backend/simulate_raw_log_analysis.py` para procesar `raw.log` y resumir errores/recomendaciones usando los CSV generados.
