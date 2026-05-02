const $ = (id) => document.getElementById(id);
const statusEl = $('status');
const BASE_URL_STORAGE_KEY = 'contifico.preview.apiBaseUrl';
const TOKEN_STORAGE_KEY = 'contifico.preview.token';

const DEFAULT_API_BASE_URL = (window.API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`).trim();

function base() {
  const value = $('baseUrl').value.trim() || DEFAULT_API_BASE_URL;
  return value.replace(/\/$/, '');
}
function authHeaders() {
  const token = $('token').value.trim();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
async function apiGet(path, params = {}) {
  const url = new URL(`${base()}${path}`);
  Object.entries(params).forEach(([k, v]) => { if (v !== '' && v != null) url.searchParams.set(k, String(v)); });
  let resp;
  try {
    resp = await fetch(url, { headers: authHeaders() });
  } catch (error) {
    throw new Error(`No se pudo conectar con ${base()}. Verifica API_BASE_URL/puerto/CORS y que la API esté arriba.`);
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
  const savedToken = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (savedToken) $('token').value = savedToken;
  $('baseUrl').addEventListener('change', () => {
    window.localStorage.setItem(BASE_URL_STORAGE_KEY, $('baseUrl').value.trim());
  });
  $('token').addEventListener('change', () => {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, $('token').value.trim());
  });
})();

async function loginAndStoreToken() {
  const username = $('username').value.trim();
  const password = $('password').value;
  if (!username || !password) throw new Error('Debes ingresar usuario y contraseña.');
  const resp = await fetch(`${base()}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const payload = await resp.json();
  if (!resp.ok) throw new Error(payload?.detail || `Login falló (${resp.status})`);
  const token = payload?.access_token || '';
  if (!token) throw new Error('No se recibió token en /auth/login');
  $('token').value = token;
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  statusEl.textContent = 'Login correcto. Token guardado.';
}

$('loginBtn').addEventListener('click', async () => {
  try { await loginAndStoreToken(); } catch (e) { showErr(e); }
});
