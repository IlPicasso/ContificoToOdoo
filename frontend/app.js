const inputJson = document.getElementById('inputJson');
const transformButton = document.getElementById('transformButton');
const downloadCsvButton = document.getElementById('downloadCsvButton');
const statusElement = document.getElementById('status');
const tableHead = document.querySelector('#previewTable thead');
const tableBody = document.querySelector('#previewTable tbody');

const sleeveMap = { S1: 'S1 - 32/33', S2: 'S2 - 34/35' };
let lastRows = [];

function parseSku(skuRaw) {
  const sku = String(skuRaw || '').trim();
  const suit = /^(\d+)\/(\d+(?:\.\d+)?)$/.exec(sku);
  if (suit) return { producto_madre: `Terno ${suit[1]}`, talla: suit[2], manga: '' };
  const shirt = /^(\d+)-(\d+(?:\.\d+)?)-(S[12])$/.exec(sku);
  if (shirt) return { producto_madre: `Camisa ${shirt[1]}`, talla: shirt[2], manga: sleeveMap[shirt[3]] || '' };
  return { producto_madre: `Producto ${sku}`, talla: '', manga: '' };
}

function mapRow(item) {
  const sku = String(item.sku || '').trim();
  const parsed = parseSku(sku);
  const stocks = item.stock_por_bodega || {};
  return {
    producto_madre: parsed.producto_madre,
    sku,
    codigo_barras: String(item.codigo_barras || ''),
    categoria_odoo: item.categoria_odoo || 'Ropa / Accesorios',
    talla: parsed.talla,
    manga: parsed.manga,
    marca: item.marca || 'BRUNO CASSINI',
    color: item.color || '',
    precio_venta: Number(item.precio_venta || 0),
    costo: Number(item.costo || 0),
    stock_bpu: Number(stocks.BPU || 0),
    stock_tur: Number(stocks.TUR || 0),
    stock_bat: Number(stocks.BAT || 0),
  };
}

function renderTable(rows) {
  tableHead.innerHTML = '';
  tableBody.innerHTML = '';
  if (!rows.length) return;
  const columns = Object.keys(rows[0]);
  const tr = document.createElement('tr');
  columns.forEach((col) => {
    const th = document.createElement('th'); th.textContent = col; tr.appendChild(th);
  });
  tableHead.appendChild(tr);
  rows.forEach((row) => {
    const r = document.createElement('tr');
    columns.forEach((col) => {
      const td = document.createElement('td'); td.textContent = String(row[col]); r.appendChild(td);
    });
    tableBody.appendChild(r);
  });
}

function toCsv(rows) {
  if (!rows.length) return '';
  const cols = Object.keys(rows[0]);
  const head = cols.join(',');
  const body = rows.map((r) => cols.map((c) => `"${String(r[c]).replaceAll('"', '""')}"`).join(',')).join('\n');
  return `${head}\n${body}`;
}

transformButton.addEventListener('click', () => {
  try {
    const payload = JSON.parse(inputJson.value);
    if (!Array.isArray(payload)) throw new Error('Debe ser un arreglo JSON.');
    lastRows = payload.map(mapRow);
    renderTable(lastRows);
    statusElement.textContent = `OK: ${lastRows.length} fila(s) transformadas.`;
  } catch (error) {
    statusElement.textContent = `Error: ${error.message}`;
  }
});

downloadCsvButton.addEventListener('click', () => {
  if (!lastRows.length) {
    statusElement.textContent = 'Primero transforma datos para poder descargar.';
    return;
  }
  const blob = new Blob([toCsv(lastRows)], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'contifico_odoo_productos.csv';
  a.click();
  URL.revokeObjectURL(url);
});
