const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000';
const TOKEN_STORAGE_KEY = 'sastreria.authToken';
const ORDER_TASK_STATUS_PENDING = 'pendiente';
const ORDER_TASK_STATUS_COMPLETED = 'completado';

const headingNumberElement = document.getElementById('orderHeadingNumber');
const headingCreatedElement = document.getElementById('orderHeadingCreated');
const headingUpdatedElement = document.getElementById('orderHeadingUpdated');
const headingStatusElement = document.getElementById('orderHeadingStatus');
const statusMessageElement = document.getElementById('orderDetailStatusMessage');
const contentElement = document.getElementById('orderDetailContent');
const summaryCustomerElement = document.getElementById('orderSummaryCustomer');
const summaryInvoiceElement = document.getElementById('orderSummaryInvoice');
const summaryOriginElement = document.getElementById('orderSummaryOrigin');
const summaryDeliveryElement = document.getElementById('orderSummaryDelivery');
const summaryTailorElement = document.getElementById('orderSummaryTailor');
const summaryVendorElement = document.getElementById('orderSummaryVendor');
const notesElement = document.getElementById('orderDetailNotes');
const measurementsElement = document.getElementById('orderDetailMeasurements');
const tasksContainerElement = document.getElementById('orderDetailTasks');
const currentYearElement = document.getElementById('currentYear');

const customerDetailModalElement = document.getElementById('customerDetailModal');
const customerDetailDialogElement = document.getElementById('customerDetailDialog');
const customerDetailNameElement = document.getElementById('customerDetailName');
const customerDetailDocumentElement = document.getElementById('customerDetailDocument');
const customerDetailContactElement = document.getElementById('customerDetailContact');
const customerDetailDescriptionElement = document.getElementById('customerDetailDescription');
const customerDetailCloseElements = document.querySelectorAll('[data-close-customer-modal]');

const RETRYABLE_STATUS_CODES = new Set([408, 429, 500, 502, 503, 504]);
const ORDER_FETCH_MAX_ATTEMPTS = 5;
const ORDER_FETCH_BASE_DELAY_MS = 2500;
const TASK_FETCH_MAX_ATTEMPTS = 3;
const TASK_FETCH_BASE_DELAY_MS = 2000;

function setCurrentYear() {
  if (currentYearElement) {
    currentYearElement.textContent = String(new Date().getFullYear());
  }
}

function readStoredToken() {
  if (typeof window === 'undefined' || !window.localStorage) {
    return null;
  }
  try {
    const storedToken = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    if (typeof storedToken !== 'string') {
      return null;
    }
    const trimmed = storedToken.trim();
    return trimmed ? trimmed : null;
  } catch (error) {
    return null;
  }
}

function parseOrderId() {
  if (typeof window === 'undefined') {
    return null;
  }
  const params = new URLSearchParams(window.location.search);
  const rawId = params.get('id');
  if (!rawId) {
    return null;
  }
  const numericId = Number(rawId);
  return Number.isFinite(numericId) && numericId > 0 ? numericId : null;
}

function applyInitialOrderNumberFromQuery() {
  if (typeof window === 'undefined' || !headingNumberElement) {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  const orderNumber = params.get('number');
  if (orderNumber) {
    headingNumberElement.textContent = orderNumber;
    document.title = `Orden ${orderNumber} | Portal de Sastrería`;
  }
}

function setStatusMessage(message, type = 'info') {
  if (!statusMessageElement) {
    return;
  }
  const normalizedMessage = message ? message.toString().trim() : '';
  statusMessageElement.classList.remove('loading', 'error', 'success');
  if (!normalizedMessage) {
    statusMessageElement.textContent = '';
    statusMessageElement.classList.add('hidden');
    return;
  }
  statusMessageElement.textContent = normalizedMessage;
  statusMessageElement.classList.remove('hidden');
  if (type === 'loading') {
    statusMessageElement.classList.add('loading');
  } else if (type === 'error') {
    statusMessageElement.classList.add('error');
  } else if (type === 'success') {
    statusMessageElement.classList.add('success');
  }
}

function clearStatusMessage() {
  setStatusMessage('');
}

function wait(delayInMs) {
  const timer = typeof window !== 'undefined' ? window : globalThis;
  return new Promise((resolve) => {
    timer.setTimeout(resolve, delayInMs);
  });
}

function isRetryableError(error) {
  if (!error) {
    return false;
  }
  if (error.retryable === true) {
    return true;
  }
  if (typeof error.status === 'number' && RETRYABLE_STATUS_CODES.has(error.status)) {
    return true;
  }
  const message = typeof error.message === 'string' ? error.message.toLowerCase() : '';
  return message.includes('intenta nuevamente');
}

function showContent() {
  if (contentElement) {
    contentElement.classList.remove('hidden');
  }
}

function hideContent() {
  if (contentElement) {
    contentElement.classList.add('hidden');
  }
}

function formatDate(dateString) {
  try {
    return new Date(dateString).toLocaleString('es-EC', {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch (error) {
    return dateString || '';
  }
}

function formatDateOnly(dateString) {
  try {
    return new Date(dateString).toLocaleDateString('es-EC', {
      dateStyle: 'medium',
    });
  } catch (error) {
    return dateString || '';
  }
}

function hasExplicitTimeComponent(value) {
  if (!value) {
    return false;
  }
  if (value instanceof Date) {
    return true;
  }
  if (typeof value === 'string') {
    return /T\d{2}:\d{2}| \d{2}:\d{2}/.test(value);
  }
  return false;
}

function formatDateTimeLocalString(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    return '';
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
}

function normalizeDateTimeString(value) {
  if (!value) {
    return '';
  }
  if (value instanceof Date) {
    return formatDateTimeLocalString(value);
  }
  if (typeof value === 'number') {
    return formatDateTimeLocalString(new Date(value));
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return '';
    }
    const isoMatch = trimmed.match(
      /^(\d{4}-\d{2}-\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?)?(?:\.\d+)?(?:Z)?$/,
    );
    if (isoMatch) {
      const datePart = isoMatch[1];
      const hourPart = isoMatch[2] ?? '00';
      const minutePart = isoMatch[3] ?? '00';
      const secondPart = isoMatch[4] ?? '00';
      return `${datePart}T${hourPart}:${minutePart}:${secondPart}`;
    }
    const parsed = new Date(trimmed);
    if (!Number.isNaN(parsed.getTime())) {
      return formatDateTimeLocalString(parsed);
    }
  }
  return '';
}

function isOrderDelivered(status) {
  return typeof status === 'string' && status.trim().toLowerCase() === 'entregado';
}

function formatDeliveryDateLabel(order) {
  if (!order?.delivery_date) {
    return '';
  }
  const deliveryValue = order.delivery_date;
  const hasTime = hasExplicitTimeComponent(deliveryValue);
  const normalizedValue = normalizeDateTimeString(deliveryValue) || deliveryValue;
  if (!hasTime && isOrderDelivered(order.status) && order.updated_at) {
    const updated = new Date(order.updated_at);
    if (!Number.isNaN(updated.getTime())) {
      const timeLabel = updated.toLocaleTimeString('es-EC', {
        hour: '2-digit',
        minute: '2-digit',
      });
      const dateLabel = formatDateOnly(normalizedValue);
      return `${dateLabel} · ${timeLabel}`;
    }
  }
  return formatDate(normalizedValue);
}

function getStatusBadgeVariant(status) {
  if (!status) {
    return 'neutral';
  }
  const normalized = status.toString().trim().toLowerCase();
  if (!normalized) {
    return 'neutral';
  }
  if (normalized.includes('entreg')) {
    return 'success';
  }
  if (normalized.includes('cancel') || normalized.includes('anulad')) {
    return 'danger';
  }
  if (normalized.includes('pend') || normalized.includes('espera')) {
    return 'warning';
  }
  if (
    normalized.includes('listo') ||
    normalized.includes('termin') ||
    normalized.includes('produc') ||
    normalized.includes('proceso')
  ) {
    return 'info';
  }
  return 'neutral';
}

function createStatusBadgeElement(status) {
  const badge = document.createElement('span');
  badge.className = 'status-badge';
  const text = status && status.toString().trim() ? status : 'Sin estado';
  badge.textContent = text;
  badge.classList.add(`status-${getStatusBadgeVariant(status)}`);
  return badge;
}

function createTaskStatusBadge(status) {
  const badge = document.createElement('span');
  badge.className = 'status-badge';
  const normalized = typeof status === 'string' ? status.trim().toLowerCase() : '';
  if (normalized === ORDER_TASK_STATUS_COMPLETED) {
    badge.textContent = 'Completado';
    badge.classList.add('status-success');
  } else {
    badge.textContent = 'Pendiente';
    badge.classList.add('status-warning');
  }
  return badge;
}

function setSummaryField(element, value, fallback = '—') {
  if (!element) {
    return;
  }
  const normalized = value === null || value === undefined
    ? ''
    : value.toString().trim();
  if (normalized) {
    element.textContent = normalized;
    element.classList.remove('muted');
  } else {
    element.textContent = fallback;
    element.classList.add('muted');
  }
}

function syncBodyModalState() {
  if (typeof document === 'undefined') {
    return;
  }
  const hasVisibleModal = Boolean(document.querySelector('.modal-overlay:not(.hidden)'));
  document.body.classList.toggle('modal-open', hasVisibleModal);
}

function normalizeTextContent(value) {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'string') {
    return value.trim();
  }
  try {
    return value.toString().trim();
  } catch (error) {
    return '';
  }
}

const customerDetailState = {
  name: '',
  document: '',
  contact: '',
  hasAnyDetail: false,
};

let lastFocusedElementBeforeCustomerModal = null;
let isCustomerModalOpen = false;

function updateCustomerModalContent() {
  if (customerDetailNameElement) {
    setSummaryField(customerDetailNameElement, customerDetailState.name, 'Sin registrar');
  }
  if (customerDetailDocumentElement) {
    setSummaryField(customerDetailDocumentElement, customerDetailState.document, 'Sin registrar');
  }
  if (customerDetailContactElement) {
    setSummaryField(customerDetailContactElement, customerDetailState.contact, 'Sin registrar');
  }
  if (customerDetailDescriptionElement) {
    if (customerDetailState.hasAnyDetail) {
      customerDetailDescriptionElement.textContent =
        'Consulta los datos registrados para el cliente asociado a esta orden.';
      customerDetailDescriptionElement.classList.remove('is-empty');
    } else {
      customerDetailDescriptionElement.textContent =
        'No se registraron datos adicionales del cliente.';
      customerDetailDescriptionElement.classList.add('is-empty');
    }
  }
}

function applyCustomerSummaryAvailability() {
  if (!summaryCustomerElement) {
    return;
  }
  const interactive = customerDetailState.hasAnyDetail;
  summaryCustomerElement.disabled = !interactive;
  summaryCustomerElement.classList.toggle('is-interactive', interactive);
  if (interactive) {
    summaryCustomerElement.setAttribute('aria-label', 'Ver datos del cliente');
    summaryCustomerElement.setAttribute('aria-haspopup', 'dialog');
    summaryCustomerElement.setAttribute('title', 'Ver datos del cliente');
  } else {
    summaryCustomerElement.removeAttribute('aria-label');
    summaryCustomerElement.removeAttribute('aria-haspopup');
    summaryCustomerElement.removeAttribute('title');
  }
}

function resetCustomerDetailState(fallback = 'Sin registrar') {
  customerDetailState.name = '';
  customerDetailState.document = '';
  customerDetailState.contact = '';
  customerDetailState.hasAnyDetail = false;
  if (summaryCustomerElement) {
    setSummaryField(summaryCustomerElement, '', fallback);
  }
  updateCustomerModalContent();
  applyCustomerSummaryAvailability();
}

function updateCustomerDetailState(order) {
  if (!order) {
    resetCustomerDetailState();
    return;
  }

  customerDetailState.name = normalizeTextContent(order.customer_name);
  customerDetailState.document = normalizeTextContent(order.customer_document);
  customerDetailState.contact = normalizeTextContent(order.customer_contact);
  customerDetailState.hasAnyDetail = Boolean(
    customerDetailState.name || customerDetailState.document || customerDetailState.contact
  );

  if (summaryCustomerElement) {
    setSummaryField(summaryCustomerElement, customerDetailState.name, 'Sin registrar');
  }
  updateCustomerModalContent();
  applyCustomerSummaryAvailability();
}

function openCustomerDetailModal() {
  if (!customerDetailModalElement || !customerDetailState.hasAnyDetail) {
    return;
  }
  if (!customerDetailModalElement.classList.contains('hidden')) {
    return;
  }
  lastFocusedElementBeforeCustomerModal =
    document.activeElement && typeof document.activeElement.focus === 'function'
      ? document.activeElement
      : null;
  customerDetailModalElement.classList.remove('hidden');
  customerDetailModalElement.setAttribute('aria-hidden', 'false');
  syncBodyModalState();
  if (customerDetailDialogElement) {
    customerDetailDialogElement.focus();
  }
  isCustomerModalOpen = true;
}

function closeCustomerDetailModal() {
  if (!customerDetailModalElement || customerDetailModalElement.classList.contains('hidden')) {
    return;
  }
  customerDetailModalElement.classList.add('hidden');
  customerDetailModalElement.setAttribute('aria-hidden', 'true');
  syncBodyModalState();
  isCustomerModalOpen = false;
  if (lastFocusedElementBeforeCustomerModal && typeof lastFocusedElementBeforeCustomerModal.focus === 'function') {
    lastFocusedElementBeforeCustomerModal.focus();
  } else if (summaryCustomerElement) {
    summaryCustomerElement.focus();
  }
  lastFocusedElementBeforeCustomerModal = null;
}

function setupCustomerDetailModal() {
  if (summaryCustomerElement) {
    summaryCustomerElement.addEventListener('click', () => {
      if (summaryCustomerElement.disabled) {
        return;
      }
      openCustomerDetailModal();
    });
  }

  customerDetailCloseElements.forEach((element) => {
    element.addEventListener('click', () => {
      closeCustomerDetailModal();
    });
  });

  if (customerDetailModalElement) {
    customerDetailModalElement.addEventListener('click', (event) => {
      if (event?.target?.dataset?.closeCustomerModal === 'true') {
        closeCustomerDetailModal();
      }
    });
  }

  document.addEventListener('keydown', (event) => {
    if (!isCustomerModalOpen) {
      return;
    }
    if (event.key === 'Escape' || event.key === 'Esc') {
      event.preventDefault();
      closeCustomerDetailModal();
    }
  });
}

function renderNotes(notes) {
  if (!notesElement) return;
  const normalized = typeof notes === 'string' ? notes.trim() : '';
  if (normalized) {
    notesElement.textContent = normalized;
    notesElement.classList.remove('muted');
  } else {
    notesElement.textContent = 'Sin notas registradas.';
    notesElement.classList.add('muted');
  }
}

function renderMeasurements(measurements) {
  if (!measurementsElement) return;
  measurementsElement.innerHTML = '';
  measurementsElement.classList.remove('muted');
  if (!Array.isArray(measurements) || !measurements.length) {
    measurementsElement.textContent = 'Sin medidas registradas.';
    measurementsElement.classList.add('muted');
    return;
  }
  measurements.forEach((measurement) => {
    if (!measurement) return;
    const nameValue = measurement.nombre;
    const valueValue = measurement.valor;
    const name =
      typeof nameValue === 'string'
        ? nameValue.trim()
        : nameValue !== null && nameValue !== undefined
          ? nameValue.toString().trim()
          : '';
    const value =
      typeof valueValue === 'string'
        ? valueValue.trim()
        : valueValue !== null && valueValue !== undefined
          ? valueValue.toString().trim()
          : '';
    if (!name && !value) {
      return;
    }
    const tag = document.createElement('span');
    tag.className = 'tag';
    const label = name && value ? `${name}: ${value}` : name || value;
    tag.textContent = label;
    measurementsElement.appendChild(tag);
  });
  if (!measurementsElement.children.length) {
    measurementsElement.textContent = 'Sin medidas registradas.';
    measurementsElement.classList.add('muted');
  }
}

function getTimeValue(value) {
  if (!value) return 0;
  const date = new Date(value);
  const time = date.getTime();
  return Number.isNaN(time) ? 0 : time;
}

function sortTasks(tasks) {
  return [...tasks].sort((a, b) => {
    const priority = (task) =>
      typeof task?.status === 'string' && task.status.trim().toLowerCase() === ORDER_TASK_STATUS_COMPLETED
        ? 1
        : 0;
    const priorityDiff = priority(a) - priority(b);
    if (priorityDiff !== 0) {
      return priorityDiff;
    }
    return getTimeValue(a?.created_at) - getTimeValue(b?.created_at);
  });
}

function renderTasks(tasks, { loading = false, loadingMessage = null, error = null } = {}) {
  if (!tasksContainerElement) return;
  tasksContainerElement.innerHTML = '';
  tasksContainerElement.classList.remove('muted', 'order-detail-error');
  if (loading) {
    tasksContainerElement.textContent =
      loadingMessage || 'Cargando checklist de producción...';
    tasksContainerElement.classList.add('muted');
    return;
  }
  if (error) {
    tasksContainerElement.textContent = error;
    tasksContainerElement.classList.add('order-detail-error');
    return;
  }
  if (!Array.isArray(tasks) || !tasks.length) {
    tasksContainerElement.textContent = 'No hay tareas registradas para esta orden.';
    tasksContainerElement.classList.add('muted');
    return;
  }
  const list = document.createElement('ul');
  list.className = 'order-detail-task-list';
  sortTasks(tasks).forEach((task) => {
    const item = document.createElement('li');
    item.className = 'order-detail-task';
    const normalizedStatus = typeof task?.status === 'string' ? task.status.trim().toLowerCase() : '';
    if (normalizedStatus === ORDER_TASK_STATUS_COMPLETED) {
      item.classList.add('is-completed');
    } else {
      item.classList.add('is-pending');
    }

    const header = document.createElement('div');
    header.className = 'order-detail-task-header';
    header.appendChild(createTaskStatusBadge(task?.status));
    if (task?.updated_at) {
      const updated = document.createElement('span');
      updated.className = 'order-detail-task-meta';
      updated.textContent = `Actualizado: ${formatDate(task.updated_at)}`;
      header.appendChild(updated);
    }
    item.appendChild(header);

    const description = document.createElement('p');
    description.className = 'order-detail-task-description';
    description.textContent = task?.description?.trim()
      ? task.description.trim()
      : 'Sin descripción registrada.';
    item.appendChild(description);

    const metaParts = [];
    if (task?.created_at) {
      metaParts.push(`Creada: ${formatDate(task.created_at)}`);
    }
    if (metaParts.length) {
      const meta = document.createElement('p');
      meta.className = 'order-detail-task-meta';
      meta.textContent = metaParts.join(' • ');
      item.appendChild(meta);
    }

    list.appendChild(item);
  });
  tasksContainerElement.appendChild(list);
}

function updateDocumentTitle(order) {
  if (!order) {
    document.title = 'Detalle de la orden | Portal de Sastrería';
    return;
  }
  const number = order.order_number || (order.id ? `#${order.id}` : '');
  if (number) {
    document.title = `Orden ${number} | Portal de Sastrería`;
  } else {
    document.title = 'Detalle de la orden | Portal de Sastrería';
  }
}

function renderOrder(order) {
  if (!order) {
    return;
  }
  updateDocumentTitle(order);
  const orderNumber = order.order_number || (order.id ? `#${order.id}` : '—');
  if (headingNumberElement) {
    headingNumberElement.textContent = orderNumber;
  }
  if (headingCreatedElement) {
    setSummaryField(headingCreatedElement, order.created_at ? formatDate(order.created_at) : '', '—');
  }
  if (headingUpdatedElement) {
    setSummaryField(headingUpdatedElement, order.updated_at ? formatDate(order.updated_at) : '', '—');
  }
  if (headingStatusElement) {
    headingStatusElement.innerHTML = '';
    headingStatusElement.appendChild(createStatusBadgeElement(order.status));
  }

  updateCustomerDetailState(order);
  setSummaryField(summaryInvoiceElement, order.invoice_number || '', 'Sin número registrado');
  setSummaryField(summaryOriginElement, order.origin_branch || '', 'Sin definir');
  const deliveryLabel = formatDeliveryDateLabel(order);
  setSummaryField(summaryDeliveryElement, deliveryLabel || '', 'Sin fecha de entrega');
  setSummaryField(
    summaryTailorElement,
    order.assigned_tailor?.full_name || '',
    'Sin asignar'
  );
  setSummaryField(
    summaryVendorElement,
    order.assigned_vendor?.full_name || '',
    'Sin asignar'
  );

  renderNotes(order.notes);
  renderMeasurements(order.measurements);
}

function extractErrorMessage(data) {
  if (!data) {
    return '';
  }
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item) => {
        if (item?.msg) return item.msg;
        if (item?.detail) return item.detail;
        if (item?.message) return item.message;
        if (typeof item === 'string') return item;
        try {
          return JSON.stringify(item);
        } catch (error) {
          return '';
        }
      })
      .filter(Boolean)
      .join(' ');
  }
  if (typeof data.detail === 'string') {
    return data.detail;
  }
  if (data.detail?.msg) {
    return data.detail.msg;
  }
  if (data.detail?.message) {
    return data.detail.message;
  }
  if (typeof data.message === 'string') {
    return data.message;
  }
  if (typeof data === 'string') {
    return data;
  }
  return '';
}

async function fetchWithAuth(path, token) {
  const headers = { Accept: 'application/json' };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { headers });
  } catch (networkError) {
    const error = new Error('No se pudo conectar con el servidor. Intenta nuevamente.');
    error.retryable = true;
    throw error;
  }
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get('content-type') || '';
  let data = null;
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (parseError) {
      data = null;
    }
  } else {
    data = await response.text();
  }
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('Tu sesión ha expirado. Inicia sesión nuevamente.');
    }
    if (response.status === 404) {
      throw new Error('No encontramos la orden solicitada.');
    }
    const message = extractErrorMessage(data) || 'Error al cargar la información.';
    const error = new Error(message);
    error.status = response.status;
    if (RETRYABLE_STATUS_CODES.has(response.status)) {
      error.retryable = true;
    }
    throw error;
  }
  return data;
}

async function fetchOrder(orderId, token) {
  return fetchWithAuth(`/orders/${orderId}`, token);
}

async function fetchOrderTasks(orderId, token) {
  const data = await fetchWithAuth(`/orders/${orderId}/tasks`, token);
  return Array.isArray(data) ? data : [];
}

async function loadOrderDetails(orderId, token) {
  setStatusMessage('Cargando información de la orden...', 'loading');
  let order = null;
  let attempt = 0;
  while (attempt < ORDER_FETCH_MAX_ATTEMPTS) {
    attempt += 1;
    try {
      order = await fetchOrder(orderId, token);
      break;
    } catch (error) {
      if (isRetryableError(error) && attempt < ORDER_FETCH_MAX_ATTEMPTS) {
        const delayMs = ORDER_FETCH_BASE_DELAY_MS * attempt;
        setStatusMessage(
          `Sincronizando la información de la orden... Reintentando (${attempt + 1}/${ORDER_FETCH_MAX_ATTEMPTS}).`,
          'loading'
        );
        // eslint-disable-next-line no-await-in-loop
        await wait(delayMs);
        continue;
      }
      hideContent();
      setStatusMessage(error.message || 'No se pudo cargar la información de la orden.', 'error');
      return;
    }
  }

  if (!order) {
    hideContent();
    setStatusMessage('No se pudo cargar la información de la orden.', 'error');
    return;
  }

  renderOrder(order);
  showContent();
  clearStatusMessage();

  let taskAttempt = 0;
  renderTasks([], { loading: true });
  while (taskAttempt < TASK_FETCH_MAX_ATTEMPTS) {
    taskAttempt += 1;
    try {
      const tasks = await fetchOrderTasks(orderId, token);
      renderTasks(tasks);
      return;
    } catch (taskError) {
      if (isRetryableError(taskError) && taskAttempt < TASK_FETCH_MAX_ATTEMPTS) {
        const delayMs = TASK_FETCH_BASE_DELAY_MS * taskAttempt;
        renderTasks([], {
          loading: true,
          loadingMessage: `Sincronizando el checklist... Reintentando (${taskAttempt + 1}/${TASK_FETCH_MAX_ATTEMPTS}).`,
        });
        // eslint-disable-next-line no-await-in-loop
        await wait(delayMs);
        continue;
      }
      renderTasks([], {
        error: taskError.message || 'No se pudo cargar el checklist.',
      });
      return;
    }
  }
}

function initialise() {
  setCurrentYear();
  applyInitialOrderNumberFromQuery();
  const orderId = parseOrderId();
  if (!orderId) {
    setStatusMessage(
      'No se especificó una orden válida. Regresa al panel y selecciona una orden.',
      'error'
    );
    return;
  }
  const token = readStoredToken();
  if (!token) {
    setStatusMessage('Inicia sesión en el panel para ver la información de la orden.', 'error');
    return;
  }
  loadOrderDetails(orderId, token);
}

setupCustomerDetailModal();
resetCustomerDetailState('—');
initialise();
