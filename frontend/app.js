const $ = (id) => document.getElementById(id);
const statusEl = $('status');
const BASE_URL_STORAGE_KEY = 'contifico.preview.apiBaseUrl';

const DEFAULT_API_BASE_URL = (window.API_BASE_URL || 'https://api.adams.com.ec').trim();

function base() {
  const value = $('baseUrl').value.trim() || DEFAULT_API_BASE_URL;
  return value.replace(/\/$/, '');
}
async function apiGet(path, params = {}) {
  const url = new URL(`${base()}${path}`);
  Object.entries(params).forEach(([k, v]) => { if (v !== '' && v != null) url.searchParams.set(k, String(v)); });
  let resp;
  try {
    resp = await fetch(url);
  } catch (error) {
    throw new Error(`No se pudo conectar con ${base()}. Verifica URL, puerto, CORS/SSL y que la API esté arriba.`);
  }
  const text = await resp.text();
  let data;
  try { data = JSON.parse(text); } catch { data = text; }
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}: ${typeof data === 'string' ? data : JSON.stringify(data)}`);
  statusEl.textContent = `${resp.status} ${resp.statusText}`;
  return data;
}
function show(outId, data) { $(outId).textContent = JSON.stringify(data, null, 2); }
function showErr(err) { statusEl.textContent = `Error: ${err.message}`; }

function setMigrationStatus(message) {
  const el = $('migrationStatus');
  if (el) el.textContent = message || '';
}

function setProgress(visible, value = 0) {
  const wrap = $('migrationProgress');
  const bar = $('migrationProgressBar');
  if (!wrap || !bar) return;
  wrap.classList.toggle('hidden', !visible);
  bar.style.width = `${Math.max(0, Math.min(100, value))}%`;
}

function toggleMigrationButtons(disabled) {
  $('generateMigrationCsv').disabled = disabled;
  $('loadRuns').disabled = disabled;
}


async function apiPost(path, params = {}) {
  const url = new URL(`${base()}${path}`);
  Object.entries(params).forEach(([k, v]) => { if (v !== "" && v != null) url.searchParams.set(k, String(v)); });
  let resp;
  try { resp = await fetch(url, { method: "POST" }); } catch (error) {
    throw new Error(`No se pudo conectar con ${base()}. Verifica URL, puerto, CORS/SSL y que la API esté arriba.`);
  }
  const text = await resp.text();
  let data; try { data = JSON.parse(text); } catch { data = text; }
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}: ${typeof data === "string" ? data : JSON.stringify(data)}`);
  statusEl.textContent = `${resp.status} ${resp.statusText}`;
  return data;
}

async function apiUpload(path, fileInputId, params = {}) {
  const input = $(fileInputId);
  const file = input?.files?.[0];
  if (!file) throw new Error('Debes seleccionar un archivo CSV.');
  const url = new URL(`${base()}${path}`);
  Object.entries(params).forEach(([k, v]) => { if (v !== '' && v != null) url.searchParams.set(k, String(v)); });
  const form = new FormData();
  form.append('file', file);
  const resp = await fetch(url, { method: 'POST', body: form });
  const text = await resp.text();
  let data; try { data = JSON.parse(text); } catch { data = text; }
  if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}: ${typeof data === 'string' ? data : JSON.stringify(data)}`);
  return data;
}


$('loadProducts').addEventListener('click', async () => {
  try {
    const data = await apiGet('/temp/contifico/products', { page: $('productsPage').value, page_size: $('productsPageSize').value, category_id: $('productsCategory').value });
    show('productsOut', data);
  } catch (e) { showErr(e); }
});
$('loadCategories').addEventListener('click', async () => {
  try { show('categoriesOut', await apiGet('/temp/contifico/product-categories')); } catch (e) { showErr(e); }
});
$('loadProductDetail').addEventListener('click', async () => {
  try {
    const id = $('productId').value.trim();
    const detail = await apiGet(`/temp/contifico/products/${encodeURIComponent(id)}`);
    let stock = [];
    try { stock = await apiGet(`/temp/contifico/products/${encodeURIComponent(id)}/stock`); } catch (_) {}
    show('productDetailOut', { detail, stock }); } catch (e) { showErr(e); }
});
$('loadWarehouses').addEventListener('click', async () => {
  try { show('warehousesOut', await apiGet('/temp/contifico/warehouses')); } catch (e) { showErr(e); }
});
$('loadInvoicesByCustomer').addEventListener('click', async () => {
  try {
    show('invoicesByCustomerOut', await apiGet('/temp/contifico/invoices/by-customer', { document_id: $('invDoc').value, page: $('invPage').value, page_size: $('invPageSize').value }));
  } catch (e) { showErr(e); }
});
$('loadInvoiceByNumber').addEventListener('click', async () => {
  try {
    show('invoiceByNumberOut', await apiGet('/temp/contifico/invoices/by-number', { customer_document: $('invoiceCustomer').value, document_number: $('invoiceNumber').value }));
  } catch (e) { showErr(e); }
});


(function initBaseUrl(){
  const saved = window.localStorage.getItem(BASE_URL_STORAGE_KEY);
  $('baseUrl').value = saved || DEFAULT_API_BASE_URL;
  $('baseUrl').addEventListener('change', () => {
    window.localStorage.setItem(BASE_URL_STORAGE_KEY, $('baseUrl').value.trim());
  });
})();


const FILE_PHASES = {
  fase1_1_simple_products_csv:              { phase: 'Fase 1 · Importar en Odoo', label: '① Productos simples (odoo_product_templates_simple.csv)', import: true },
  fase1_2_templates_with_attributes_csv:    { phase: 'Fase 1 · Importar en Odoo', label: '② Templates con atributos (odoo_product_templates_with_attributes.csv)', import: true },
  fase2_1_variant_internal_references_csv:  { phase: 'Fase 2 · Actualizar SKU en variantes', label: '③ Internal References variantes (odoo_product_variant_internal_references.csv)', import: true },
  fase2_2_internal_reference_update_csv:    { phase: 'Fase 2 · Actualizar SKU en variantes', label: '④ Update SKU simples+variantes (product_internal_reference_update.csv)', import: true },
  fase3_stock_quant_csv:                    { phase: 'Fase 3 · Stock', label: '⑤ Ajuste de inventario (odoo_stock_quant.csv)', import: true },
  reporte_errores_csv:                      { phase: 'Reportes · Solo lectura', label: 'Errores de migración', import: false },
  reporte_mapping_csv:                      { phase: 'Reportes · Solo lectura', label: 'Mapping report', import: false },
  reporte_atributos_rechazados_csv:         { phase: 'Reportes · Solo lectura', label: 'Atributos rechazados', import: false },
  reporte_barcode_conflicts_csv:            { phase: 'Reportes · Solo lectura', label: 'Conflictos de barcode', import: false },
  reporte_barcode_conflicts_fase2_csv:      { phase: 'Reportes · Solo lectura', label: 'Conflictos barcode Fase 2', import: false },
  reporte_duplicados_variantes_csv:         { phase: 'Reportes · Solo lectura', label: 'Combinaciones variantes duplicadas', import: false },
  reporte_missing_stock_csv:                { phase: 'Reportes · Solo lectura', label: 'Productos sin stock asignado', import: false },
  reporte_validacion_fase2_csv:             { phase: 'Reportes · Solo lectura', label: 'Validación Fase 2', import: false },
  reporte_excluded_zero_csv:                { phase: 'Reportes · Solo lectura', label: 'Excluidos por stock 0', import: false },
  reporte_unmapped_categories_csv:          { phase: 'Reportes · Solo lectura', label: 'Categorías sin mapear', import: false },
  debug_log:                                { phase: 'Logs', label: 'debug.log', import: false },
  raw_log:                                  { phase: 'Logs', label: 'raw.log', import: false },
  run_summary_json:                         { phase: 'Logs', label: 'run_summary.json', import: false },
};

function makeLink(href, label, isImport) {
  const a = document.createElement('a');
  a.href = href;
  a.textContent = `↓ ${label}`;
  a.target = '_blank';
  a.rel = 'noopener';
  a.className = isImport ? 'download-link download-link--import' : 'download-link download-link--report';
  return a;
}

function renderMigrationLinks(files, summary) {
  const container = $('migrationLinks');
  container.innerHTML = '';
  const byPhase = {};
  Object.entries(files || {}).forEach(([key, path]) => {
    const meta = FILE_PHASES[key] || { phase: 'Otros', label: key, import: false };
    if (!byPhase[meta.phase]) byPhase[meta.phase] = [];
    byPhase[meta.phase].push({ label: meta.label, path, import: meta.import });
  });

  // Extract run_id from any path (e.g. /odoo-migration/runs/20260506_123456/files/foo.csv)
  const anyPath = Object.values(files || {})[0] || '';
  const runIdMatch = anyPath.match(/\/runs\/([^/]+)\//);
  const runId = runIdMatch ? runIdMatch[1] : null;

  Object.entries(byPhase).forEach(([phase, items]) => {
    const section = document.createElement('div');
    section.className = 'phase-section';
    const title = document.createElement('div');
    title.className = 'phase-title';
    title.textContent = phase;
    section.appendChild(title);
    items.forEach(({ label, path, import: isImport }) => {
      section.appendChild(makeLink(`${base()}${path}`, label, isImport));
    });
    container.appendChild(section);
  });
}

function renderWarnings(summary) {
  const panel = $('warningsPanel');
  if (!panel) return;
  const warnings = [];
  if ((summary.total_errores_reales || 0) > 0)
    warnings.push({ level: 'error', msg: `${summary.total_errores_reales} errores de migración (SKU vacío o barcode duplicado en Contifico)` });
  if ((summary.total_attribute_rejections || 0) > 0)
    warnings.push({ level: 'warn', msg: `${summary.total_attribute_rejections} SKUs rechazados por atributos fuera del catálogo Odoo → quedan como simples` });
  if ((summary.total_barcode_conflicts || 0) > 0)
    warnings.push({ level: 'warn', msg: `${summary.total_barcode_conflicts} conflictos de barcode detectados → barcode limpiado en esos productos` });
  if ((summary.total_duplicate_variant_combinations || 0) > 0)
    warnings.push({ level: 'warn', msg: `${summary.total_duplicate_variant_combinations} combinaciones de variante duplicadas → ver odoo_duplicate_variant_combinations.csv` });
  if ((summary.total_phase2_orphan_variant_skus || 0) > 0)
    warnings.push({ level: 'warn', msg: `${summary.total_phase2_orphan_variant_skus} variantes sin template en Fase 1 → no se podrá actualizar su SKU en Odoo` });
  if ((summary.total_missing_from_stock || 0) > 0)
    warnings.push({ level: 'info', msg: `${summary.total_missing_from_stock} SKUs con stock en Contifico sin mapping en Odoo` });
  if ((summary.total_categorias_no_mapeadas || 0) > 0)
    warnings.push({ level: 'info', msg: `${summary.total_categorias_no_mapeadas} categorías de Contifico sin mapeo a Odoo` });
  panel.innerHTML = '';
  if (!warnings.length) {
    panel.innerHTML = '<div class="warning-item warning-item--ok">✓ Sin advertencias críticas. Puedes importar los archivos en Odoo.</div>';
    panel.classList.remove('hidden');
    return;
  }
  warnings.forEach(({ level, msg }) => {
    const div = document.createElement('div');
    div.className = `warning-item warning-item--${level}`;
    div.textContent = (level === 'error' ? '✗ ' : level === 'warn' ? '⚠ ' : 'ℹ ') + msg;
    panel.appendChild(div);
  });
  panel.classList.remove('hidden');
}

$('generateMigrationCsv').addEventListener('click', async () => {
  try {
    toggleMigrationButtons(true);
    setProgress(true, 3);
    setMigrationStatus('Creando job de exportación...');
    const started = await apiPost('/odoo-migration/products-stock/export-jobs', {
      page_size: $('exportPageSize').value,
      max_pages: $('exportMaxPages').value,
      export_stock: false,
      include_additional_attributes: $('includeAdditionalAttributes').checked,
    });
    const jobId = started.job_id;
    let done = false;
    while (!done) {
      await new Promise((r) => setTimeout(r, 800));
      const job = await apiGet(`/odoo-migration/products-stock/export-jobs/${jobId}`);
      if (job.status === 'failed') {
        setMigrationStatus(`Error en exportación: ${job.error || 'desconocido'}`);
        throw new Error(job.error || 'Export job failed');
      }
      const stage = job.stage || 'running';
      const found = Number(job.found_items || 0);
      const processed = Number(job.processed_items || 0);
      const total = Number(job.total_items || 0);
      const expectedMin = Number(job.expected_min_items_from_api || 0);
      const expectedLabel = expectedMin > 0 ? ` · esperado API v2: ${expectedMin} · cobertura: ${Math.min(100, ((found / expectedMin) * 100)).toFixed(2)}%` : '';
      let progress = 12;
      if (stage === 'fetching' || stage === 'fetched_page') progress = Math.min(45, 10 + found / 3);
      if (stage === 'processing') progress = total > 0 ? Math.min(92, 45 + (processed / total) * 47) : 55;
      if (job.status === 'completed') progress = 100;
      setProgress(true, progress);
      setMigrationStatus(`Etapa: ${stage} · items encontrados: ${found} · procesados: ${processed}${total ? `/${total}` : ''}${expectedLabel}`);
      if (job.status === 'completed') {
        done = true;
        show('migrationSummaryOut', job);
        renderWarnings(job.summary || {});
        renderMigrationLinks(job.files, job.summary);
        // Pre-fill run_id en Merger y Stock para el siguiente paso
        if (job.run_id) {
          if (!$('mergerRunId').value.trim()) $('mergerRunId').value = job.run_id;
          if (!$('stockRunId').value.trim()) $('stockRunId').value = job.run_id;
          if (!$('compareRunId').value.trim()) $('compareRunId').value = job.run_id;
        }
        const summaryExpected = Number((job.summary || {}).expected_min_items_from_api || 0);
        const summaryFound = Number(job.found_items || (job.summary || {}).total_products || 0);
        const summaryCoverage = summaryExpected > 0 ? ` Cobertura vs count API: ${summaryFound}/${summaryExpected} (${Math.min(100, ((summaryFound / summaryExpected) * 100)).toFixed(2)}%).` : '';
        setMigrationStatus((job.hit_max_pages ? 'Exportación completada pero alcanzó el límite de páginas. Sube Max pages para traer más.' : 'Exportación completada. Descarga los archivos generados.') + summaryCoverage);
      }
    }
  } catch (e) {
    setMigrationStatus('La exportación falló. Revisa el detalle de error global.');
    showErr(e);
  } finally {
    toggleMigrationButtons(false);
  }
});

$('uploadSnapshotAttributes').addEventListener('click', async () => {
  try {
    const data = await apiUpload('/odoo-migration/odoo-attributes/snapshot/upload', 'snapshotAttributesCsv', { kind: 'attributes' });
    show('migrationSummaryOut', data);
    setMigrationStatus(`Snapshot de atributos actualizado (${data.count} registros).`);
  } catch (e) { showErr(e); }
});

$('uploadSnapshotCategories').addEventListener('click', async () => {
  try {
    const data = await apiUpload('/odoo-migration/odoo-attributes/snapshot/upload', 'snapshotCategoriesCsv', { kind: 'categories' });
    show('migrationSummaryOut', data);
    setMigrationStatus(`Snapshot de categorías actualizado (${data.count} registros).`);
  } catch (e) { showErr(e); }
});

$('precheckOdooOffline').addEventListener('click', async () => {
  try {
    setMigrationStatus('Ejecutando precheck offline (sin API Odoo)...');
    const data = await apiGet('/odoo-migration/odoo-attributes/precheck-offline');
    show('migrationSummaryOut', data);
    $('includeAdditionalAttributes').checked = !!data.can_enable_brand_color_export;
    const missingAttrs = (data.attributes_missing || []).length;
    const missingCats = (data.categories_missing || []).length;
    setMigrationStatus(`Precheck offline: faltan ${missingAttrs} atributos y ${missingCats} categorías.`);
  } catch (e) {
    showErr(e);
  }
});

$('processRawJson').addEventListener('click', async () => {
  try {
    const data = await apiUpload('/odoo-migration/products-stock/process-raw-upload', 'rawJsonFile', {
      include_additional_attributes: $('includeAdditionalAttributes').checked,
      export_stock: false,
    });
    show('migrationSummaryOut', data);
    renderWarnings(data.summary || {});
    renderMigrationLinks(data.files, data.summary);
    if (data.run_id) {
      if (!$('mergerRunId').value.trim()) $('mergerRunId').value = data.run_id;
      if (!$('stockRunId').value.trim()) $('stockRunId').value = data.run_id;
      if (!$('compareRunId').value.trim()) $('compareRunId').value = data.run_id;
    }
    setMigrationStatus(`Archivo procesado. Productos detectados: ${data.detected_products}.`);
  } catch (e) { showErr(e); }
});

$('loadRuns').addEventListener('click', async () => {
  try {
    setMigrationStatus('Consultando últimas corridas...');
    const data = await apiGet('/odoo-migration/runs', { limit: 20 });
    show('migrationSummaryOut', data);
    setMigrationStatus('Corridas cargadas.');
  } catch (e) { showErr(e); }
});


function activateTab(name) {
  document.querySelectorAll('.tab-btn').forEach((b)=>b.classList.toggle('active', b.dataset.tab===name));
  document.querySelectorAll('.tab-panel').forEach((p)=>p.classList.toggle('active', p.id===`tab-${name}`));
}
document.querySelectorAll('.tab-btn').forEach((btn)=>btn.addEventListener('click',()=>activateTab(btn.dataset.tab)));

// ── Comparador de inventario ────────────────────────────────────────────────

function setCompareStatus(msg) { const el=$('compareStatus'); if(el) el.textContent=msg||''; }

function renderCompareStats(data) {
  const el = $('compareStats');
  if (!el) return;
  el.innerHTML = `
    <div class="stat-card stat-card--total"><div class="stat-num">${data.contifico_total}</div><div class="stat-lbl">Contífico</div></div>
    <div class="stat-card stat-card--total"><div class="stat-num">${data.odoo_total}</div><div class="stat-lbl">Odoo</div></div>
    <div class="stat-card stat-card--both"><div class="stat-num">${data.in_both}</div><div class="stat-lbl">Coinciden</div></div>
    <div class="stat-card stat-card--contifico"><div class="stat-num">${data.only_in_contifico}</div><div class="stat-lbl">Solo Contífico</div></div>
    <div class="stat-card stat-card--odoo"><div class="stat-num">${data.only_in_odoo}</div><div class="stat-lbl">Solo Odoo</div></div>
  `;
  el.classList.remove('hidden');
}

function renderComparePreviews(data) {
  const el = $('comparePreviews');
  if (!el) return;
  el.innerHTML = '';
  const sections = [
    { key: 'preview_only_contifico', label: `Solo en Contífico — ${data.only_in_contifico} SKUs (en extracción pero no en Odoo)`, cls: 'stat-card--contifico' },
    { key: 'preview_only_odoo',      label: `Solo en Odoo — ${data.only_in_odoo} SKUs (en Odoo pero no en extracción)`,   cls: 'stat-card--odoo' },
    { key: 'preview_in_both',        label: `Coinciden — ${data.in_both} SKUs`,                                             cls: 'stat-card--both' },
  ];
  sections.forEach(({ key, label, cls }) => {
    const items = data[key] || [];
    if (!items.length) return;
    const details = document.createElement('details');
    details.className = 'compare-preview';
    const summary = document.createElement('summary');
    summary.textContent = label + (items.length === 30 ? ' (mostrando primeros 30)' : '');
    details.appendChild(summary);
    const ul = document.createElement('ul');
    items.forEach(sku => { const li = document.createElement('li'); li.textContent = sku; ul.appendChild(li); });
    details.appendChild(ul);
    el.appendChild(details);
  });
}

function renderCompareLinks(files) {
  const el = $('compareLinks');
  if (!el || !files) return;
  el.innerHTML = '';
  const title = document.createElement('div');
  title.className = 'phase-title';
  title.textContent = 'Descargar resultados';
  el.appendChild(title);
  const COMPARE_FILES = [
    { key: 'only_in_contifico', label: 'Solo en Contífico (faltan importar en Odoo)', isImport: false },
    { key: 'only_in_odoo',      label: 'Solo en Odoo (no vienen de esta extracción)',  isImport: false },
    { key: 'in_both',           label: 'Coinciden en ambos sistemas',                  isImport: false },
  ];
  COMPARE_FILES.forEach(({ key, label, isImport }) => {
    const path = files[key];
    if (!path) return;
    el.appendChild(makeLink(`${base()}${path}`, label, isImport));
  });
}

$('executeCompare').addEventListener('click', async () => {
  try {
    const runId = $('compareRunId').value.trim();
    if (!runId) throw new Error('Debes ingresar el Run ID de la extracción.');
    const input = $('compareOdooFile');
    if (!input?.files?.[0]) throw new Error('Debes seleccionar el CSV exportado de Odoo.');
    $('executeCompare').disabled = true;
    $('compareStats').classList.add('hidden');
    $('comparePreviews').innerHTML = '';
    $('compareLinks').innerHTML = '';
    setCompareStatus('Comparando inventarios...');
    const url = new URL(`${base()}/odoo-migration/runs/${encodeURIComponent(runId)}/compare-inventory`);
    const form = new FormData();
    form.append('file', input.files[0]);
    const resp = await fetch(url, { method: 'POST', body: form });
    const text = await resp.text();
    let data; try { data = JSON.parse(text); } catch { data = text; }
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}: ${typeof data === 'string' ? data : JSON.stringify(data)}`);
    renderCompareStats(data);
    renderComparePreviews(data);
    renderCompareLinks(data.files);
    setCompareStatus(`Comparación completada. Coinciden: ${data.in_both} · Solo Contífico: ${data.only_in_contifico} · Solo Odoo: ${data.only_in_odoo}`);
    if (data.only_in_contifico > 0) $('generateMissingSection').classList.remove('hidden');
  } catch(e) {
    setCompareStatus(`Error: ${e.message}`);
    showErr(e);
  } finally {
    $('executeCompare').disabled = false;
  }
});

$('generateMissingImport').addEventListener('click', async () => {
  try {
    const runId = $('compareRunId').value.trim();
    if (!runId) throw new Error('Debes ingresar el Run ID.');
    $('generateMissingImport').disabled = true;
    $('generateMissingStatus').textContent = 'Generando CSVs...';
    $('generateMissingLinks').innerHTML = '';
    const data = await apiGet(`/odoo-migration/runs/${encodeURIComponent(runId)}/compare-inventory/generate-missing`);
    const el = $('generateMissingLinks');
    el.innerHTML = '';
    const title = document.createElement('div');
    title.className = 'phase-title';
    title.textContent = 'Archivos generados (importar en este orden)';
    el.appendChild(title);
    const MISSING_FILES = [
      { key: 'missing_simple',           label: `① Simples faltantes — ${data.simple_rows_exported} productos (odoo_missing_simple_for_import.csv)`,           isImport: true },
      { key: 'missing_templates',        label: `② Templates con atributos — ${data.template_rows_exported} filas / ${data.needed_templates} templates (odoo_missing_templates_with_attributes.csv)`, isImport: true },
      { key: 'missing_variants_phase2',  label: `③ Variantes Phase 2 — ${data.variant_rows_exported} SKUs (odoo_missing_variants_phase2.csv)`,                isImport: true },
    ];
    MISSING_FILES.forEach(({ key, label, isImport }) => {
      const path = (data.files || {})[key];
      if (!path) return;
      el.appendChild(makeLink(`${base()}${path}`, label, isImport));
    });
    $('generateMissingStatus').textContent = `CSVs generados. Simples: ${data.missing_simple_total} · Variantes: ${data.missing_variants_total} · Templates necesarios: ${data.needed_templates}`;
  } catch(e) {
    $('generateMissingStatus').textContent = `Error: ${e.message}`;
    showErr(e);
  } finally {
    $('generateMissingImport').disabled = false;
  }
});

// ── Merger Variantes ────────────────────────────────────────────────────────

function setMergerStatus(msg) { const el=$('mergerStatus'); if(el) el.textContent=msg||''; }

function renderMergerLinks(runId, files) {
  const container = $('mergerLinks');
  if (!container || !files) return;
  container.innerHTML = '';
  const section = document.createElement('div');
  section.className = 'phase-section';
  const title = document.createElement('div');
  title.className = 'phase-title';
  title.textContent = 'Archivos generados por el merger';
  section.appendChild(title);
  const MERGER_FILES = [
    { key: 'phase2_with_odoo_ids_minimal', label: '⭐ IMPORTAR (variantes) — odoo_phase2_with_odoo_ids_minimal.csv (id + SKU + Barcode + Precio)', isImport: true },
    { key: 'simples_minimal',              label: '⭐ IMPORTAR (simples) — odoo_phase2_simples_minimal.csv (id + SKU + Barcode)', isImport: true },
    { key: 'phase2_with_odoo_ids',         label: 'Variantes versión completa con Name/Variant Values (solo referencia)', isImport: false },
    { key: 'unmatched',                    label: 'Variantes sin par en Odoo (merger_unmatched)', isImport: false },
    { key: 'simples_unmatched',            label: 'Simples sin par en Odoo (simples_unmatched)', isImport: false },
    { key: 'unused_odoo',                  label: 'Registros Odoo sin par en Fase 2 (merger_unused_odoo)', isImport: false },
  ];
  MERGER_FILES.forEach(({ key, label, isImport }) => {
    const path = files[key];
    if (!path) return;
    section.appendChild(makeLink(`${base()}${path}`, label, isImport));
  });
  container.appendChild(section);
}

$('executeMerger').addEventListener('click', async () => {
  try {
    const runId = $('mergerRunId').value.trim();
    if (!runId) throw new Error('Debes ingresar el Run ID de la corrida.');
    const input = $('mergerOdooExportFile');
    if (!input?.files?.[0]) throw new Error('Debes seleccionar el CSV exportado de Odoo.');
    $('executeMerger').disabled = true;
    setMergerStatus('Ejecutando merger...');
    const url = new URL(`${base()}/odoo-migration/runs/${encodeURIComponent(runId)}/phase2/merge`);
    const form = new FormData();
    form.append('file', input.files[0]);
    const resp = await fetch(url, { method: 'POST', body: form });
    const text = await resp.text();
    let data; try { data = JSON.parse(text); } catch { data = text; }
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}: ${typeof data === 'string' ? data : JSON.stringify(data)}`);
    show('mergerSummaryOut', data);
    renderMergerLinks(runId, data.files);
    const byId = data.matched_by_tmpl_id ?? 0;
    const byName = data.matched_by_name ?? 0;
    const simples = data.simple_matched ?? 0;
    setMergerStatus(`Merger completado. Variantes: ${data.matched} (${byId} por ID, ${byName} por nombre) · Simples: ${simples} · Sin par: ${data.unmatched} · Odoo sin usar: ${data.unused_odoo_rows}`);
    // Pre-fill run_id en Stock si está vacío
    if (!$('stockRunId').value.trim()) $('stockRunId').value = runId;
  } catch(e) {
    setMergerStatus(`Error: ${e.message}`);
    showErr(e);
  } finally {
    $('executeMerger').disabled = false;
  }
});

// ── Stock por bodega ────────────────────────────────────────────────────────

function getRunId(){ return $('stockRunId').value.trim(); }
function setStockStatus(msg){ const el=$('stockStatusText'); if(el) el.textContent=msg||''; }

$('startStockPhase').addEventListener('click', async ()=>{
  try{
    const runId=getRunId(); if(!runId) throw new Error('Debes ingresar un run_id');
    setStockStatus('Iniciando stock...');
    const data=await apiPost(`/odoo-migration/runs/${encodeURIComponent(runId)}/stock/start`);
    show('stockStatusOut', data); setStockStatus('Stock iniciado.');
  }catch(e){ showErr(e); }
});

$('checkStockStatus').addEventListener('click', async ()=>{
  try{
    const runId=getRunId(); if(!runId) throw new Error('Debes ingresar un run_id');
    const data=await apiGet(`/odoo-migration/runs/${encodeURIComponent(runId)}/stock/status`);
    show('stockStatusOut', data);
    setStockStatus(`Progreso: ${data.done||0}/${data.total||0} · pendientes: ${data.pending||0} · fallidos: ${data.failed||0} · ${data.percent||0}%`);
  }catch(e){ showErr(e); }
});

$('pauseStockPhase').addEventListener('click', async ()=>{
  try{ const runId=getRunId(); if(!runId) throw new Error('Debes ingresar un run_id'); show('stockStatusOut', await apiPost(`/odoo-migration/runs/${encodeURIComponent(runId)}/stock/pause`)); setStockStatus('Stock pausado.'); }catch(e){ showErr(e); }
});
$('resumeStockPhase').addEventListener('click', async ()=>{
  try{ const runId=getRunId(); if(!runId) throw new Error('Debes ingresar un run_id'); show('stockStatusOut', await apiPost(`/odoo-migration/runs/${encodeURIComponent(runId)}/stock/resume`)); setStockStatus('Stock reanudado.'); }catch(e){ showErr(e); }
});
$('retryStockFailed').addEventListener('click', async ()=>{
  try{ const runId=getRunId(); if(!runId) throw new Error('Debes ingresar un run_id'); show('stockStatusOut', await apiPost(`/odoo-migration/runs/${encodeURIComponent(runId)}/stock/retry-failed`)); setStockStatus('Reintento de fallidos iniciado.'); }catch(e){ showErr(e); }
});
