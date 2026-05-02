const $ = (id) => document.getElementById(id);
const baseUrlEl = $('baseUrl');
const tokenEl = $('token');
const endpointSelect = $('endpointSelect');
const methodEl = $('method');
const pathEl = $('path');
const queryEl = $('query');
const headersEl = $('headers');
const bodyEl = $('body');
const statusEl = $('status');
const responseEl = $('response');

let endpoints = [];

function safeJsonParse(text, fallback = {}) {
  try { return JSON.parse(text || ''); } catch { return fallback; }
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function populateEndpoints() {
  endpointSelect.innerHTML = '';
  endpoints.forEach((ep, idx) => {
    const opt = document.createElement('option');
    opt.value = String(idx);
    opt.textContent = `${ep.method.toUpperCase()} ${ep.path}`;
    endpointSelect.appendChild(opt);
  });
  if (endpoints.length) selectEndpoint(0);
}

function selectEndpoint(index) {
  const ep = endpoints[index];
  if (!ep) return;
  methodEl.value = ep.method.toUpperCase();
  pathEl.value = ep.path;
}

async function loadOpenApi() {
  const base = baseUrlEl.value.trim().replace(/\/$/, '');
  const resp = await fetch(`${base}/openapi.json`);
  if (!resp.ok) throw new Error(`No se pudo cargar OpenAPI (${resp.status})`);
  const spec = await resp.json();
  endpoints = [];
  Object.entries(spec.paths || {}).forEach(([path, methods]) => {
    Object.keys(methods).forEach((method) => endpoints.push({ path, method }));
  });
  endpoints.sort((a, b) => `${a.path}${a.method}`.localeCompare(`${b.path}${b.method}`));
  populateEndpoints();
  statusEl.textContent = `OpenAPI cargado: ${endpoints.length} método(s) detectados.`;
}

function buildUrl(base, path, query) {
  const url = new URL(`${base.replace(/\/$/, '')}${path}`);
  Object.entries(query || {}).forEach(([k, v]) => {
    if (v !== null && v !== undefined && `${v}` !== '') url.searchParams.set(k, String(v));
  });
  return url;
}

async function sendRequest() {
  const base = baseUrlEl.value.trim();
  const method = methodEl.value.trim().toUpperCase();
  const path = pathEl.value.trim();
  const query = safeJsonParse(queryEl.value, {});
  const extraHeaders = safeJsonParse(headersEl.value, {});
  const body = safeJsonParse(bodyEl.value, {});

  const headers = { 'Content-Type': 'application/json', ...extraHeaders };
  const token = tokenEl.value.trim();
  if (token) headers.Authorization = `Bearer ${token}`;

  const url = buildUrl(base, path, query);
  const init = { method, headers };
  if (!['GET', 'DELETE'].includes(method)) init.body = JSON.stringify(body);

  const startedAt = performance.now();
  const resp = await fetch(url, init);
  const elapsed = (performance.now() - startedAt).toFixed(0);
  const text = await resp.text();
  let parsed;
  try { parsed = JSON.parse(text); } catch { parsed = text; }

  statusEl.textContent = `${resp.status} ${resp.statusText} · ${elapsed} ms`;
  responseEl.textContent = pretty(parsed);
}

function buildCurl() {
  const base = baseUrlEl.value.trim();
  const method = methodEl.value.trim().toUpperCase();
  const path = pathEl.value.trim();
  const query = safeJsonParse(queryEl.value, {});
  const headers = safeJsonParse(headersEl.value, {});
  const body = safeJsonParse(bodyEl.value, {});
  const token = tokenEl.value.trim();
  if (token) headers.Authorization = `Bearer ${token}`;
  const url = buildUrl(base, path, query).toString();

  const chunks = [`curl -X ${method} '${url}'`];
  Object.entries(headers).forEach(([k, v]) => chunks.push(`-H '${k}: ${String(v)}'`));
  if (!['GET', 'DELETE'].includes(method)) chunks.push(`-H 'Content-Type: application/json' -d '${JSON.stringify(body)}'`);
  return chunks.join(' \\\n  ');
}

$('loadOpenApi').addEventListener('click', async () => {
  try { await loadOpenApi(); } catch (e) { statusEl.textContent = `Error: ${e.message}`; }
});
endpointSelect.addEventListener('change', () => selectEndpoint(Number(endpointSelect.value)));
$('sendBtn').addEventListener('click', async () => {
  try { await sendRequest(); } catch (e) { statusEl.textContent = `Error: ${e.message}`; }
});
$('curlBtn').addEventListener('click', async () => {
  const curl = buildCurl();
  await navigator.clipboard.writeText(curl);
  statusEl.textContent = 'cURL copiado al portapapeles.';
});
