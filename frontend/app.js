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


let migrationProgressTimer = null;

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

function startProgressSimulation() {
  let progress = 8;
  setProgress(true, progress);
  setMigrationStatus('Iniciando exportación...');
  migrationProgressTimer = window.setInterval(() => {
    progress = Math.min(progress + 7, 92);
    setProgress(true, progress);
    if (progress < 35) setMigrationStatus('Extrayendo productos de Contífico...');
    else if (progress < 70) setMigrationStatus('Procesando SKU ADAMS y validando plantilla...');
    else setMigrationStatus('Generando archivos CSV revisables...');
  }, 450);
}

function stopProgressSimulation(success = true) {
  if (migrationProgressTimer) {
    window.clearInterval(migrationProgressTimer);
    migrationProgressTimer = null;
  }
  setProgress(true, success ? 100 : 0);
  if (success) setMigrationStatus('Exportación finalizada. Revisa el resumen y descarga los archivos.');
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
  try { show('productDetailOut', await apiGet(`/temp/contifico/products/${encodeURIComponent($('productId').value.trim())}`)); } catch (e) { showErr(e); }
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


function renderMigrationLinks(files) {
  const container = $('migrationLinks');
  container.innerHTML = '';
  Object.entries(files || {}).forEach(([label, path]) => {
    const a = document.createElement('a');
    a.href = `${base()}${path}`;
    a.textContent = `Descargar ${label}`;
    a.target = '_blank';
    a.rel = 'noopener';
    a.className = 'download-link';
    container.appendChild(a);
  });
}

$('generateMigrationCsv').addEventListener('click', async () => {
  try {
    toggleMigrationButtons(true);
    startProgressSimulation();
    const data = await apiPost('/odoo-migration/products-stock/export', {
      page_size: $('exportPageSize').value,
      max_pages: $('exportMaxPages').value,
    });
    stopProgressSimulation(true);
    show('migrationSummaryOut', data);
    renderMigrationLinks(data.files);
  } catch (e) {
    stopProgressSimulation(false);
    setMigrationStatus('La exportación falló. Revisa el detalle de error global.');
    showErr(e);
  } finally {
    toggleMigrationButtons(false);
  }
});

$('loadRuns').addEventListener('click', async () => {
  try {
    setMigrationStatus('Consultando últimas corridas...');
    const data = await apiGet('/odoo-migration/runs', { limit: 20 });
    show('migrationSummaryOut', data);
    setMigrationStatus('Corridas cargadas.');
  } catch (e) { showErr(e); }
});
