const API_BASE_URL = window.API_BASE_URL || 'http://localhost:8000';
const DEFAULT_PAGE_SIZE = 10;
const PAGE_SIZE_OPTIONS = [10, 15, 20, 25, 30, 35, 40, 45, 50];
const CONTIFICO_DEFAULT_PAGE_SIZE = 25;
const CONTIFICO_MAX_PAGE_SIZE = 200;
const ESTABLISHMENTS = ['Urdesa', 'Batan', 'Indie'];
const ORDER_TASK_STATUS_PENDING = 'pendiente';
const ORDER_TASK_STATUS_COMPLETED = 'completado';
const KANBAN_FETCH_PAGE_SIZE = 100;
const KANBAN_FALLBACK_STATUS = 'Sin estado';
const INVOICE_LOOKUP_LOG_PREFIX = '[Contífico][Factura puntual]';
const CUSTOMER_INVOICE_PAGE_SIZE = 50;


const state = {
  statuses: [],
  token: null,
  user: null,
  tailors: [],
  vendors: [],
  orders: [],
  customers: [],
  customerOptions: [],
  customerOrdersCache: {},
  customerDisplayCache: {},
  customerSearchTerm: '',
  orderSearchTerm: '',
  customerPage: 1,
  customerPageSize: DEFAULT_PAGE_SIZE,
  orderPage: 1,
  orderPageSize: DEFAULT_PAGE_SIZE,
  customerTotal: 0,
  orderTotal: 0,
  kanbanOrders: [],
  kanbanLoading: false,
  kanbanError: null,
  kanbanSearchTerm: '',
  kanbanNeedsRefresh: true,
  kanbanLastUpdated: null,
  activeOrdersView: 'list',
  isCreateCustomerVisible: false,
  isCustomerDetailVisible: false,
  isCreateUserVisible: false,
  auditLogs: [],
  users: [],
  usersLoaded: false,
  usersLoadError: null,
  editingUserId: null,
  selectedCustomerId: null,
  selectedOrderId: null,
  orderTasks: [],
  orderTasksOrderId: null,
  orderTasksLoading: false,
  orderTasksRequestId: 0,
  customerRequestId: 0,
  orderRequestId: 0,
  customerOptionsRequestId: 0,
  customerInvoicesCache: {},
  customerInvoicesRequestId: 0,
  orderInvoiceSuggestions: [],
  orderInvoiceSuggestionsCustomerId: null,
  orderInvoiceSuggestionRequestId: 0,
  orderInvoiceSuggestionsLoading: false,
  orderInvoiceSuggestionsError: null,
  orderInvoiceLookup: null,
  orderInvoiceLookupLoading: false,
  orderInvoiceLookupError: null,
  orderInvoiceLookupCustomerId: null,
  orderInvoiceLookupNumber: '',
  orderInvoiceLookupRequestId: 0,
  pendingOrderCustomerSelection: null,
  contificoPreviewProducts: [],
  contificoPreviewProductsPage: 1,
  contificoPreviewProductsPageSize: CONTIFICO_DEFAULT_PAGE_SIZE,
  contificoPreviewProductsLoading: false,
  contificoPreviewProductsError: null,
  contificoPreviewProductsFetched: false,
  contificoPreviewWarehouses: [],
  contificoPreviewWarehousesLoading: false,
  contificoPreviewWarehousesError: null,
  contificoPreviewWarehousesFetched: false,
  contificoPreviewCustomerInvoices: [],
  contificoPreviewCustomerInvoicesPage: 1,
  contificoPreviewCustomerInvoicesPageSize: CONTIFICO_DEFAULT_PAGE_SIZE,
  contificoPreviewCustomerInvoicesLoading: false,
  contificoPreviewCustomerInvoicesError: null,
  contificoPreviewCustomerInvoicesFetched: false,
  contificoPreviewCustomerInvoicesDocument: '',
  contificoPreviewCustomerInvoiceLookup: null,
  contificoPreviewCustomerInvoiceLookupLoading: false,
  contificoPreviewCustomerInvoiceLookupError: null,
  contificoPreviewCustomerInvoiceLookupFetched: false,
  contificoPreviewCustomerInvoiceLookupDocument: '',
  contificoPreviewCustomerInvoiceLookupNumber: '',
  contificoPreviewInvoiceLookup: null,
  contificoPreviewInvoiceLookupLoading: false,
  contificoPreviewInvoiceLookupError: null,
  contificoPreviewInvoiceLookupFetched: false,
  contificoPreviewInvoiceLookupNumber: '',
  contificoPreviewInvoiceLookupCustomerDocument: '',
  contificoPreviewInvoiceLookupRequestId: 0,
  contificoPreviewInvoiceLookupProgress: 0,
  contificoPreviewInvoiceLookupStage: '',
  contificoPreviewInvoiceLookupMetadata: {},
  contificoPreviewInvoiceLookupJobId: null,
  contificoPreviewInvoiceLookupPollTimer: null,
  contificoCustomerInvoicesModalVisible: false,
  contificoInvoiceLookupModalVisible: false,
};

const TOKEN_STORAGE_KEY = 'sastreria.authToken';

function logInvoiceLookupEvent(level, message, details) {
  if (typeof console === 'undefined') {
    return;
  }
  const logger =
    typeof level === 'string' && typeof console[level] === 'function'
      ? console[level].bind(console)
      : console.log.bind(console);
  const parts = [INVOICE_LOOKUP_LOG_PREFIX, message];
  if (details !== undefined) {
    parts.push(details);
  }
  logger(...parts);
}

function logInvoiceLookupInfo(message, details) {
  logInvoiceLookupEvent('info', message, details);
}

function logInvoiceLookupWarn(message, details) {
  logInvoiceLookupEvent('warn', message, details);
}

function logInvoiceLookupError(message, details) {
  logInvoiceLookupEvent('error', message, details);
}

const INVOICE_LOOKUP_STAGE_MESSAGES = {
  pending: 'Colocando la búsqueda en cola...',
  start: 'Preparando búsqueda en Contífico...',
  starting: 'Preparando búsqueda en Contífico...',
  cache_hit: 'Factura encontrada en la caché local.',
  cache_miss: 'Factura no encontrada en la caché. Consultando Contífico...',
  customer_lookup_start: 'Filtrando facturas por cliente en Contífico...',
  customer_lookup_success: 'Factura encontrada entre las facturas del cliente.',
  customer_lookup_miss:
    'No se halló la factura dentro del historial del cliente. Reintentando con otras estrategias...',
  customer_lookup_error:
    'No se pudo consultar las facturas del cliente. Probando con otra estrategia...',
  direct_lookup_start: 'Consultando la factura directamente en Contífico...',
  direct_lookup_success: 'Factura obtenida exitosamente mediante consulta directa.',
  direct_lookup_fallback: 'Reintentando mediante búsqueda paginada...',
  paged_search_candidate: (metadata = {}) =>
    metadata.candidate
      ? `Buscando coincidencias con la variante “${metadata.candidate}”...`
      : 'Explorando variantes del número de factura...',
  paged_search_page: (metadata = {}) => {
    const page = metadata.page ? Number(metadata.page) : null;
    if (metadata.candidate && page) {
      return `Revisando la página ${page} para la variante “${metadata.candidate}”...`;
    }
    if (page) {
      return `Revisando la página ${page} de resultados...`;
    }
    return 'Analizando páginas de resultados...';
  },
  paged_search_success: 'Factura encontrada durante la búsqueda paginada.',
  paged_search_exhausted: 'No se encontraron coincidencias en la búsqueda paginada inicial.',
  catalog_lookup_start: 'Descargando catálogo de facturas para búsqueda local...',
  catalog_lookup_success: 'Factura encontrada en el catálogo descargado.',
  not_found: 'No se encontró una factura con el número consultado.',
  error: 'Ocurrió un error al consultar Contífico.',
  timeout: 'La consulta superó el tiempo límite y se canceló.',
  completed: 'Búsqueda finalizada.',
};

function describeInvoiceLookupStage(stage, metadata = {}) {
  if (!stage) {
    return '';
  }
  const entry = INVOICE_LOOKUP_STAGE_MESSAGES[stage];
  if (typeof entry === 'function') {
    try {
      return entry(metadata) || '';
    } catch (error) {
      console.warn(`${INVOICE_LOOKUP_LOG_PREFIX} Error interpretando el estado de búsqueda.`, error);
      return '';
    }
  }
  if (typeof entry === 'string') {
    return entry;
  }
  return stage.replace(/_/g, ' ');
}

function getTokenStorage() {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    return window.localStorage || null;
  } catch (error) {
    return null;
  }
}

function persistToken(token) {
  const storage = getTokenStorage();
  if (!storage) return;
  try {
    if (token) {
      storage.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      storage.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch (error) {
    /* ignore storage errors */
  }
}

function readStoredToken() {
  const storage = getTokenStorage();
  if (!storage) return null;
  try {
    const storedToken = storage.getItem(TOKEN_STORAGE_KEY);
    if (typeof storedToken !== 'string') {
      return null;
    }
    const trimmedToken = storedToken.trim();
    return trimmedToken ? trimmedToken : null;
  } catch (error) {
    return null;
  }
}

function clearStoredToken() {
  persistToken(null);
}

const views = document.querySelectorAll('.view');
const navButtons = document.querySelectorAll('.nav-button');
const panelNavButton = document.getElementById('panelNavButton');
const loginNavButton = document.getElementById('loginNavButton');
const categoryBar = document.getElementById('categoryBar');
const DASHBOARD_TAB_IDS = [
  'ordersPanel',
  'orderCreatePanel',
  'customersPanel',
  'usersPanel',
  'auditLogPanel',
  'contificoPreviewPanel',
];
const ADMIN_ONLY_TABS = new Set(['usersPanel', 'auditLogPanel', 'contificoPreviewPanel']);
const dashboardTabButtons = Array.from(document.querySelectorAll('[data-tab]')).filter((btn) =>
  DASHBOARD_TAB_IDS.includes(btn.dataset.tab)
);
const dashboardSubnav = document.querySelector('.dashboard-subnav');
const dashboardPanels = document.querySelectorAll('.dashboard-panel');
const ordersTableSection = document.getElementById('ordersTableSection');
const ordersKanbanSection = document.getElementById('ordersKanbanSection');
const orderCreatePanel = document.getElementById('orderCreatePanel');
const orderCreateBackButton = document.getElementById('orderCreateBackButton');
const ordersCreateButton = document.getElementById('ordersCreateButton');
const ordersViewToggleButtons = document.querySelectorAll('[data-orders-view]');
const roleRestrictedElements = document.querySelectorAll('[data-hide-roles]');
const orderKanbanColumns = document.getElementById('orderKanbanColumns');
const orderKanbanStatus = document.getElementById('orderKanbanStatus');
const orderKanbanSearchInput = document.getElementById('orderKanbanSearchInput');
const orderKanbanRefreshButton = document.getElementById('orderKanbanRefreshButton');
const orderKanbanDetailContainer = document.getElementById('orderKanbanDetail');
const orderKanbanDetailOverlay = document.getElementById('orderKanbanDetailOverlay');
const orderKanbanDetailDialog = document.getElementById('orderKanbanDetailDialog');
const orderKanbanDetailMessage = document.getElementById('orderKanbanDetailMessage');
const kanbanDetailCloseElements = document.querySelectorAll('[data-kanban-detail-close]');
const orderLookupForm = document.getElementById('orderLookupForm');
const orderNumberInput = document.getElementById('orderNumber');
const orderDocumentInput = document.getElementById('customerDocument');
const orderResultContainer = document.getElementById('orderStatusResult');
const staffLoginForm = document.getElementById('staffLoginForm');
const staffDashboard = document.getElementById('staffDashboard');
const staffLoginCard = document.getElementById('staffLogin');
const logoutButton = document.getElementById('logoutButton');
const createOrderForm = document.getElementById('createOrderForm');
const createCustomerForm = document.getElementById('createCustomerForm');
const updateCustomerForm = document.getElementById('updateCustomerForm');
const customerSearchInput = document.getElementById('customerSearchInput');
const showCreateCustomerButton = document.getElementById('showCreateCustomerButton');
const createCustomerSection = document.getElementById('createCustomerSection');
const customerCreateOverlay = document.getElementById('customerCreateOverlay');
const customerCreateDialog = document.getElementById('customerCreateDialog');
const closeCreateCustomerButton = document.getElementById('closeCreateCustomerButton');
const customersTableBody = document.getElementById('customersTableBody');
const customerPageSizeSelect = document.getElementById('customerPageSize');
const customerPrevPageButton = document.getElementById('customerPrevPage');
const customerNextPageButton = document.getElementById('customerNextPage');
const customerPaginationInfo = document.getElementById('customerPaginationInfo');
const customerDetail = document.getElementById('customerDetail');
const customerDetailOverlay = document.getElementById('customerDetailOverlay');
const customerDetailDialog = document.getElementById('customerDetailDialog');
const customerDetailTitle = document.getElementById('customerDetailTitle');
const customerDetailSummaryElement = document.getElementById('customerDetailSummary');
const customerOrderHistoryContainer = document.getElementById('customerOrderHistory');
const customerInvoicesSection = document.getElementById('customerInvoicesSection');
const customerInvoicesStatus = document.getElementById('customerInvoicesStatus');
const customerInvoicesTableBody = document.getElementById('customerInvoicesTableBody');
const customerInvoicesRefreshButton = document.getElementById('customerInvoicesRefreshButton');
const customerMeasurementsContainer = document.getElementById('customerMeasurementsContainer');
const updateCustomerMeasurementsContainer = document.getElementById('updateCustomerMeasurementsContainer');
const updateCustomerNameInput = document.getElementById('updateCustomerName');
const updateCustomerDocumentInput = document.getElementById('updateCustomerDocument');
const updateCustomerPhoneInput = document.getElementById('updateCustomerPhone');
const customerFullNameInput = document.getElementById('customerFullName');
const customerDocumentInput = document.getElementById('customerDocumentInput');
const customerPhoneInput = document.getElementById('customerPhone');
const customerEmailInput = document.getElementById('customerEmail');
const customerAddressInput = document.getElementById('customerAddress');
const fetchContificoCustomerButton = document.getElementById('fetchContificoCustomerButton');
const contificoCustomerLookupStatus = document.getElementById('contificoCustomerLookupStatus');
const updateCustomerEmailInput = document.getElementById('updateCustomerEmail');
const updateCustomerAddressInput = document.getElementById('updateCustomerAddress');
const updateCustomerFetchContificoButton = document.getElementById('updateCustomerFetchContificoButton');
const updateContificoCustomerLookupStatus = document.getElementById('updateContificoCustomerLookupStatus');
const addCustomerMeasurementSetButton = document.getElementById('addCustomerMeasurementSet');
const addUpdateCustomerMeasurementSetButton = document.getElementById('addUpdateCustomerMeasurementSet');
const deleteCustomerButton = document.getElementById('deleteCustomerButton');
const orderCustomerSelect = document.getElementById('orderCustomerSelect');
const orderCreateCustomerButton = document.getElementById('orderCreateCustomerButton');
const customerMeasurementOptions = document.getElementById('customerMeasurementOptions');
const ordersTableBody = document.getElementById('ordersTableBody');
const orderPageSizeSelect = document.getElementById('orderPageSize');
const orderPrevPageButton = document.getElementById('orderPrevPage');
const orderNextPageButton = document.getElementById('orderNextPage');
const orderPaginationInfo = document.getElementById('orderPaginationInfo');
const orderSearchInput = document.getElementById('orderSearchInput');
const measurementsList = document.getElementById('measurementsList');
const addMeasurementButton = document.getElementById('addMeasurementButton');
const newOrderTasksList = document.getElementById('newOrderTasksList');
const addOrderTaskButton = document.getElementById('addOrderTaskButton');
const statusSelect = document.getElementById('newOrderStatus');
const assignTailorSelect = document.getElementById('assignTailor');
const assignVendorSelect = document.getElementById('assignVendor');
const newOrderInvoiceInput = document.getElementById('newOrderInvoice');
const orderInvoiceSuggestionsStatus = document.getElementById('orderInvoiceSuggestionsStatus');
const orderInvoiceSuggestionsList = document.getElementById('orderInvoiceSuggestions');
const orderInvoiceLookupButton = document.getElementById('orderInvoiceLookupButton');
const orderInvoiceLookupDetails = document.getElementById('orderInvoiceLookupDetails');
const newOrderOriginSelect = document.getElementById('newOrderOrigin');
const newOrderDeliveryDateInput = document.getElementById('newOrderDeliveryDate');
const orderDetail = document.getElementById('orderDetail');
const updateOrderForm = document.getElementById('updateOrderForm');
const orderDetailNumberElement = document.getElementById('orderDetailNumber');
const orderDetailCreatedAtElement = document.getElementById('orderDetailCreatedAt');
const orderDetailUpdatedAtElement = document.getElementById('orderDetailUpdatedAt');
const orderDetailCustomerInput = document.getElementById('orderDetailCustomer');
const orderDetailDocumentInput = document.getElementById('orderDetailDocument');
const orderDetailContactInput = document.getElementById('orderDetailContact');
const orderDetailStatusSelect = document.getElementById('orderDetailStatus');
const orderDetailTailorSelect = document.getElementById('orderDetailTailor');
const orderDetailVendorSelect = document.getElementById('orderDetailVendor');
const orderDetailInvoiceInput = document.getElementById('orderDetailInvoice');
const orderDetailOriginSelect = document.getElementById('orderDetailOrigin');
const orderDetailDeliveryDateInput = document.getElementById('orderDetailDeliveryDate');
const orderDetailNotesTextarea = document.getElementById('orderDetailNotes');
const deleteOrderButton = document.getElementById('deleteOrderButton');
const orderDetailMeasurementsContainer = document.getElementById('orderDetailMeasurements');
const orderTasksList = document.getElementById('orderTasksList');
const orderTaskForm = document.getElementById('orderTaskForm');
const orderTaskAddButton = document.getElementById('orderTaskAddButton');
const orderTaskDescriptionInput = document.getElementById('orderTaskDescription');
const orderTaskResponsibleSelect = document.getElementById('orderTaskResponsibleSelect');
const orderTasksPermissionsNotice = document.getElementById('orderTasksPermissionsNotice');
const closeOrderDetailButton = document.getElementById('closeOrderDetailButton');
const toastElement = document.getElementById('toast');
const currentYearElement = document.getElementById('currentYear');
const currentUserNameElement = document.getElementById('currentUserName');
const currentUserRoleElement = document.getElementById('currentUserRole');
const usersTabButton = document.getElementById('usersTabButton');
const auditLogTabButton = document.getElementById('auditLogTabButton');
const auditLogTableBody = document.getElementById('auditLogTableBody');
const contificoPreviewTabButton = document.getElementById('contificoPreviewTabButton');
const contificoPreviewProductsForm = document.getElementById('contificoPreviewProductsForm');
const contificoPreviewPageInput = document.getElementById('contificoPreviewPage');
const contificoPreviewPageSizeInput = document.getElementById('contificoPreviewPageSize');
const contificoPreviewProductsStatus = document.getElementById('contificoPreviewProductsStatus');
const contificoPreviewProductsTableBody = document.getElementById('contificoPreviewProductsTableBody');
const contificoPreviewWarehousesButton = document.getElementById('contificoPreviewWarehousesButton');
const contificoPreviewWarehousesStatus = document.getElementById('contificoPreviewWarehousesStatus');
const contificoPreviewWarehousesTableBody = document.getElementById('contificoPreviewWarehousesTableBody');
const contificoCustomerInvoicesForm = document.getElementById('contificoCustomerInvoicesForm');
const contificoCustomerInvoicesDocumentInput = document.getElementById('contificoCustomerInvoicesDocument');
const contificoCustomerInvoicesPageInput = document.getElementById('contificoCustomerInvoicesPage');
const contificoCustomerInvoicesPageSizeInput = document.getElementById('contificoCustomerInvoicesPageSize');
const contificoCustomerInvoicesStatus = document.getElementById('contificoCustomerInvoicesStatus');
const contificoCustomerInvoiceLookupForm = document.getElementById('contificoCustomerInvoiceLookupForm');
const contificoCustomerInvoiceLookupDocumentInput = document.getElementById(
  'contificoCustomerInvoiceLookupDocument'
);
const contificoCustomerInvoiceLookupNumberInput = document.getElementById(
  'contificoCustomerInvoiceLookupNumber'
);
const contificoCustomerInvoiceLookupStatus = document.getElementById(
  'contificoCustomerInvoiceLookupStatus'
);
const contificoCustomerInvoiceLookupResult = document.getElementById(
  'contificoCustomerInvoiceLookupResult'
);
const contificoInvoiceLookupForm = document.getElementById('contificoInvoiceLookupForm');
const contificoInvoiceLookupDocumentInput = document.getElementById(
  'contificoInvoiceLookupDocument'
);
const contificoInvoiceLookupNumberInput = document.getElementById('contificoInvoiceLookupNumber');
const contificoInvoiceLookupStatus = document.getElementById('contificoInvoiceLookupStatus');
const contificoCustomerInvoicesModalButton = document.getElementById('contificoCustomerInvoicesModalButton');
const contificoCustomerInvoicesOverlay = document.getElementById('contificoCustomerInvoicesOverlay');
const contificoCustomerInvoicesDialog = document.getElementById('contificoCustomerInvoicesDialog');
const contificoCustomerInvoicesModal = document.getElementById('contificoCustomerInvoicesModal');
const contificoCustomerInvoicesModalStatus = document.getElementById('contificoCustomerInvoicesModalStatus');
const contificoCustomerInvoicesModalTableBody = document.getElementById(
  'contificoCustomerInvoicesModalTableBody'
);
const contificoInvoiceLookupModalButton = document.getElementById('contificoInvoiceLookupModalButton');
const contificoInvoiceLookupOverlay = document.getElementById('contificoInvoiceLookupOverlay');
const contificoInvoiceLookupDialog = document.getElementById('contificoInvoiceLookupDialog');
const contificoInvoiceLookupModal = document.getElementById('contificoInvoiceLookupModal');
const contificoInvoiceLookupModalStatus = document.getElementById('contificoInvoiceLookupModalStatus');
const contificoInvoiceLookupModalDetails = document.getElementById('contificoInvoiceLookupModalDetails');
const contificoInvoiceLookupProgress = document.getElementById('contificoInvoiceLookupProgress');
const contificoInvoiceLookupProgressBar = document.getElementById('contificoInvoiceLookupProgressBar');
const contificoInvoiceLookupProgressLabel = document.getElementById('contificoInvoiceLookupProgressLabel');
const usersTableBody = document.getElementById('usersTableBody');
const userCreateContainer = document.getElementById('userCreateContainer');
const toggleCreateUserButton = document.getElementById('toggleCreateUserButton');
const closeCreateUserButton = document.getElementById('closeCreateUserButton');
const createUserForm = document.getElementById('createUserForm');
const newUserUsernameInput = document.getElementById('newUserUsername');
const newUserFullNameInput = document.getElementById('newUserFullName');
const newUserPasswordInput = document.getElementById('newUserPassword');
const newUserRoleSelect = document.getElementById('newUserRole');
const userEditContainer = document.getElementById('userEditContainer');
const editUserForm = document.getElementById('editUserForm');
const editUserUsernameInput = document.getElementById('editUserUsername');
const editUserFullNameInput = document.getElementById('editUserFullName');
const editUserRoleSelect = document.getElementById('editUserRole');
const editUserPasswordInput = document.getElementById('editUserPassword');
const cancelEditUserButton = document.getElementById('cancelEditUserButton');
const editUserTitle = document.getElementById('editUserTitle');
const closeCustomerDetailButton = document.getElementById('closeCustomerDetailButton');

const ROLE_LABELS = {
  administrador: 'Administrador',
  vendedor: 'Vendedor',
  sastre: 'Sastre',
};

const DEFAULT_NEW_USER_ROLE = 'vendedor';

const USER_ROLE_OPTIONS = [
  { value: 'administrador', label: ROLE_LABELS.administrador },
  { value: 'vendedor', label: ROLE_LABELS.vendedor },
  { value: 'sastre', label: ROLE_LABELS.sastre },
];

const DELIVERY_WARNING_DAYS = 2;
const CUSTOMER_DETAIL_DEFAULT_TITLE = 'Detalle del cliente';
const CUSTOMER_DETAIL_DEFAULT_SUMMARY = 'Selecciona un cliente para ver su información.';
const CUSTOMER_ORDER_HISTORY_PROMPT = 'Selecciona un cliente para ver sus órdenes anteriores.';
const CUSTOMER_ORDER_HISTORY_EMPTY_MESSAGE = 'No tiene órdenes registradas.';

let activeDashboardTab = 'ordersPanel';
let lastOrdersViewBeforeCreate = 'list';
const ORDER_TABLE_COLUMN_COUNT = 6;
const CUSTOMER_TABLE_COLUMN_COUNT = 5;
let activeOrderDetailRow = null;
let currentOrderDetailHost = null;
let lastKanbanFocusedElement = null;
let lastKanbanFocusedOrderId = null;
let lastCustomerDetailTrigger = null;
let lastCreateCustomerTrigger = null;
let lastContificoCustomerInvoicesTrigger = null;
let lastContificoInvoiceLookupTrigger = null;


function setActiveView(viewId) {
  views.forEach((view) => {
    if (view.id === viewId) {
      view.classList.add('active');
    } else {
      view.classList.remove('active');
    }
  });
  navButtons.forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.view === viewId);
  });
  if (loginNavButton) {
    const shouldHighlightLogin = viewId === 'staff-view' && !state.token;
    loginNavButton.classList.toggle('active', shouldHighlightLogin);
  }
}

navButtons.forEach((btn) => {
  btn.addEventListener('click', () => setActiveView(btn.dataset.view));
});

const dashboardShortcutButtons = document.querySelectorAll('[data-target-tab]');

function updateDashboardShortcutHighlight() {
  if (!dashboardShortcutButtons.length) {
    return;
  }
  dashboardShortcutButtons.forEach((shortcut) => {
    const shouldHighlight =
      shortcut.dataset.targetTab === activeDashboardTab && !shortcut.classList.contains('hidden');
    shortcut.classList.toggle('is-highlight', shouldHighlight);
  });
}

function updateDashboardShortcutVisibility() {
  const isAuthenticated = Boolean(state.token);
  const userRole = state.user?.role || null;

  if (categoryBar) {
    categoryBar.classList.toggle('hidden', !isAuthenticated);
  }
  if (dashboardSubnav) {
    dashboardSubnav.classList.toggle('hidden', !isAuthenticated);
    dashboardSubnav.setAttribute('aria-hidden', isAuthenticated ? 'false' : 'true');
  }
  if (!dashboardShortcutButtons.length) {
    applyRoleVisibility();
    return;
  }

  let hasVisibleActiveShortcut = false;

  dashboardShortcutButtons.forEach((btn) => {
    const targetTab = btn.dataset.targetTab;
    const requiredRole = btn.dataset.requiredRole || null;
    const hideRoles = (btn.dataset.hideRoles || '')
      .split(',')
      .map((role) => role.trim())
      .filter(Boolean);
    const lacksRequiredRole = Boolean(requiredRole) && userRole !== requiredRole;
    const hiddenForRole = hideRoles.length > 0 && (!userRole || hideRoles.includes(userRole));
    const isAdminTab = ADMIN_ONLY_TABS.has(targetTab);
    const isRecognizedTab = DASHBOARD_TAB_IDS.includes(targetTab);
    const shouldHide =
      !isAuthenticated ||
      !isRecognizedTab ||
      lacksRequiredRole ||
      hiddenForRole ||
      (isAdminTab && userRole !== 'administrador');
    btn.classList.toggle('hidden', shouldHide);
    if (!shouldHide && targetTab === activeDashboardTab) {
      hasVisibleActiveShortcut = true;
    }
  });

  if (isAuthenticated && !hasVisibleActiveShortcut) {
    const fallback = Array.from(dashboardShortcutButtons).find(
      (btn) =>
        !btn.classList.contains('hidden') && DASHBOARD_TAB_IDS.includes(btn.dataset.targetTab)
    );
    if (fallback) {
      setActiveDashboardTab(fallback.dataset.targetTab);
      return;
    }
  }

  updateDashboardShortcutHighlight();
  applyRoleVisibility();
}

dashboardShortcutButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    if (btn.classList.contains('hidden')) {
      return;
    }
    const targetTab = btn.dataset.targetTab;
    setActiveView('staff-view');
    setActiveDashboardTab(targetTab);
    updateDashboardShortcutHighlight();
    const destination = state.token ? document.getElementById('staffDashboard') : document.getElementById('staffLogin');
    if (destination && destination.scrollIntoView) {
      destination.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    if (!state.token) {
      const usernameInput = document.getElementById('username');
      if (usernameInput) {
        usernameInput.focus();
      }
    }
  });
});

if (loginNavButton) {
  loginNavButton.addEventListener('click', () => {
    setActiveView('staff-view');
    const usernameInput = document.getElementById('username');
    if (usernameInput) {
      usernameInput.focus();
    }
  });
}

function focusFirstCreateOrderField() {
  if (!createOrderForm) return;
  const focusable = createOrderForm.querySelector(
    'input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled])'
  );
  if (focusable) {
    focusable.focus();
  }
}

function syncCreateOrderFormDisabled() {
  if (!createOrderForm) return;
  const shouldDisable = !orderCreatePanel || orderCreatePanel.classList.contains('hidden');
  createOrderForm.dataset.disabled = shouldDisable ? 'true' : 'false';
  const submitButton = createOrderForm.querySelector('button[type="submit"]');
  if (submitButton) {
    submitButton.disabled = shouldDisable;
  }
}

function applyRoleVisibility() {
  const userRole = state.user?.role || null;
  roleRestrictedElements.forEach((element) => {
    const roles = (element.dataset.hideRoles || '')
      .split(',')
      .map((role) => role.trim())
      .filter(Boolean);
    const shouldHide = roles.length > 0 && (!userRole || roles.includes(userRole));
    element.classList.toggle('hidden', shouldHide);
    if ('disabled' in element) {
      element.disabled = shouldHide;
    }
    if (element === ordersCreateButton) {
      element.setAttribute('aria-hidden', shouldHide ? 'true' : 'false');
      if (shouldHide && activeDashboardTab === 'orderCreatePanel') {
        setActiveDashboardTab('ordersPanel');
      }
    }
  });
}

function setActiveOrdersView(view) {
  const nextView = view === 'kanban' ? 'kanban' : 'list';
  state.activeOrdersView = nextView;
  ordersViewToggleButtons.forEach((btn) => {
    const isActive = btn.dataset.ordersView === nextView;
    btn.classList.toggle('active', isActive);
    btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
  if (ordersTableSection) {
    ordersTableSection.classList.toggle('hidden', nextView !== 'list');
    ordersTableSection.setAttribute('aria-hidden', nextView === 'list' ? 'false' : 'true');
  }
  if (ordersKanbanSection) {
    const isKanban = nextView === 'kanban';
    ordersKanbanSection.classList.toggle('hidden', !isKanban);
    ordersKanbanSection.setAttribute('aria-hidden', isKanban ? 'false' : 'true');
  }
  if (nextView === 'kanban') {
    ensureKanbanDataLoaded();
  } else {
    renderOrders();
  }
  updateOrderDetailOverlayVisibility();
  renderOrderKanban();
}

function setActiveDashboardTab(tabId = 'ordersPanel') {
  if (!dashboardPanels.length) return;
  const userRole = state.user?.role || null;
  let targetTab = tabId && DASHBOARD_TAB_IDS.includes(tabId) ? tabId : 'ordersPanel';
  if (ADMIN_ONLY_TABS.has(targetTab) && userRole !== 'administrador') {
    targetTab = 'ordersPanel';
  }
  const previousTab = activeDashboardTab;
  activeDashboardTab = targetTab;

  const highlightTabId = targetTab === 'orderCreatePanel' ? 'ordersPanel' : targetTab;

  dashboardTabButtons.forEach((btn) => {
    const tab = btn.dataset.tab;
    if (!tab) return;
    const isAdminTab = ADMIN_ONLY_TABS.has(tab);
    const shouldHide = !state.token || (isAdminTab && userRole !== 'administrador');
    btn.classList.toggle('hidden', shouldHide);
    btn.disabled = shouldHide;
    btn.classList.toggle('active', tab === highlightTabId);
  });

  dashboardPanels.forEach((panel) => {
    const { id } = panel;
    if (!id) return;
    const isAdminPanel = ADMIN_ONLY_TABS.has(id);
    const shouldHide = !state.token || (isAdminPanel && userRole !== 'administrador');
    if (shouldHide) {
      panel.classList.add('hidden');
    } else {
      panel.classList.toggle('hidden', id !== targetTab);
    }
  });

  if (previousTab === 'ordersPanel' && targetTab !== 'ordersPanel') {
    if (currentOrderDetailHost === 'overlay' && state.selectedOrderId !== null) {
      clearOrderDetail({ skipRender: true });
    } else if (document.body) {
      document.body.classList.remove('kanban-detail-open');
    }
  }

  if (targetTab === 'usersPanel' && userRole === 'administrador') {
    loadUsers();
  }

  if (targetTab === 'ordersPanel') {
    if (state.activeOrdersView === 'kanban') {
      ensureKanbanDataLoaded();
    } else {
      renderOrderKanban();
    }
  } else {
    renderOrderKanban();
    if (targetTab === 'orderCreatePanel') {
      focusFirstCreateOrderField();
    }
  }

  syncCreateOrderFormDisabled();
  updateDashboardShortcutHighlight();
}

dashboardTabButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    if (btn.disabled) {
      return;
    }
    setActiveDashboardTab(btn.dataset.tab);
  });
});

ordersViewToggleButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    if (btn.disabled) {
      return;
    }
    setActiveOrdersView(btn.dataset.ordersView);
  });
});

if (ordersCreateButton) {
  ordersCreateButton.addEventListener('click', () => {
    if (ordersCreateButton.disabled) {
      return;
    }
    lastOrdersViewBeforeCreate = state.activeOrdersView || 'list';
    setActiveView('staff-view');
    setActiveDashboardTab('orderCreatePanel');
    if (orderCreatePanel && orderCreatePanel.scrollIntoView) {
      orderCreatePanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
}

if (orderCreateBackButton) {
  orderCreateBackButton.addEventListener('click', () => {
    setActiveDashboardTab('ordersPanel');
    setActiveOrdersView(lastOrdersViewBeforeCreate || 'list');
    if (
      ordersCreateButton &&
      !ordersCreateButton.classList.contains('hidden') &&
      !ordersCreateButton.disabled
    ) {
      ordersCreateButton.focus();
    }
  });
}

setActiveDashboardTab(activeDashboardTab);
updateDashboardShortcutHighlight();
updateDashboardShortcutVisibility();
setActiveOrdersView(state.activeOrdersView || 'list');
applyRoleVisibility();
renderContificoPreview();

if (dashboardShortcutButtons.length) {
  dashboardShortcutButtons.forEach((shortcut) => {
    const shortcutTab = shortcut.dataset.targetTab;
    shortcut.classList.toggle('is-highlight', shortcutTab === activeDashboardTab);
  });
}

if (currentYearElement) {
  currentYearElement.textContent = new Date().getFullYear();
}

function showToast(message, type = 'info') {
  if (!toastElement) return;
  const isError = type === 'error';
  toastElement.setAttribute('role', isError ? 'alert' : 'status');
  toastElement.setAttribute('aria-live', isError ? 'assertive' : 'polite');
  toastElement.textContent = '';
  toastElement.textContent = message;
  toastElement.className = `toast show ${isError ? 'error' : type === 'success' ? 'success' : ''}`;
  setTimeout(() => {
    toastElement.classList.remove('show', 'success', 'error');
  }, 3500);
}

function setContificoLookupStatus(element, message, tone = 'info') {
  if (!element) return;
  element.textContent = message || '';
  element.classList.remove('info', 'success', 'error');
  if (message) {
    element.classList.add(tone);
  }
}

function formatDate(dateString) {
  try {
    return new Date(dateString).toLocaleString('es-EC', {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
  } catch (error) {
    return dateString;
  }
}

function formatDateOnly(dateString) {
  try {
    return new Date(dateString).toLocaleDateString('es-EC', {
      dateStyle: 'medium',
    });
  } catch (error) {
    return dateString;
  }
}

function formatDateTimeForInput(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
    return '';
  }
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function toInputDateTimeValue(value) {
  if (!value) {
    return '';
  }

  if (value instanceof Date) {
    return formatDateTimeForInput(value);
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return '';
    }
    const match = trimmed.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}):(\d{2})/);
    if (match) {
      const [, datePart, hourPart, minutePart] = match;
      return `${datePart}T${hourPart}:${minutePart}`;
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
      return `${trimmed}T00:00`;
    }
    const parsed = new Date(trimmed);
    return formatDateTimeForInput(parsed);
  }

  if (typeof value === 'number') {
    return formatDateTimeForInput(new Date(value));
  }

  return '';
}

function formatCurrencyUSD(value) {
  if (value === null || value === undefined || value === '') {
    return '—';
  }
  const numericValue = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numericValue)) {
    return '—';
  }
  try {
    return new Intl.NumberFormat('es-EC', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numericValue);
  } catch (error) {
    return `$${numericValue.toFixed(2)}`;
  }
}

function normalizeText(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return value
    .toString()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function isOrderDelivered(status) {
  return typeof status === 'string' && status.trim().toLowerCase() === 'entregado';
}

function isDeliveryDateOverdue(deliveryDateString, status) {
  if (!deliveryDateString || isOrderDelivered(status)) {
    return false;
  }
  const deliveryDate = new Date(deliveryDateString);
  if (Number.isNaN(deliveryDate.getTime())) {
    return false;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  deliveryDate.setHours(0, 0, 0, 0);
  return deliveryDate.getTime() < today.getTime();
}

function isDeliveryDateClose(deliveryDateString, status) {
  if (!deliveryDateString || isOrderDelivered(status)) {
    return false;
  }
  const deliveryDate = new Date(deliveryDateString);
  if (Number.isNaN(deliveryDate.getTime())) {
    return false;
  }
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  deliveryDate.setHours(0, 0, 0, 0);
  const diffInDays = (deliveryDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24);
  return diffInDays >= 0 && diffInDays <= DELIVERY_WARNING_DAYS;
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

function normalizeDateTimeString(value) {
  if (!value) {
    return '';
  }
  if (value instanceof Date) {
    return formatDateTimeForApi(value);
  }
  if (typeof value === 'number') {
    return formatDateTimeForApi(new Date(value));
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
      return formatDateTimeForApi(parsed);
    }
  }
  return '';
}

function formatDeliveryDateDisplay(order) {
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

function canModifyOrderTasks() {
  const role = state.user?.role;
  return role === 'administrador' || role === 'sastre';
}

function sortOrderTasks(tasks) {
  return [...tasks].sort((a, b) => {
    const aTime = new Date(a?.created_at ?? 0).getTime();
    const bTime = new Date(b?.created_at ?? 0).getTime();
    const aInvalid = Number.isNaN(aTime);
    const bInvalid = Number.isNaN(bTime);
    if (aInvalid && bInvalid) {
      return (a?.id ?? 0) - (b?.id ?? 0);
    }
    if (aInvalid) return 1;
    if (bInvalid) return -1;
    if (aTime === bTime) {
      return (a?.id ?? 0) - (b?.id ?? 0);
    }
    return aTime - bTime;
  });
}

function resetOrderTasksState() {
  state.orderTasks = [];
  state.orderTasksOrderId = null;
  state.orderTasksLoading = false;
  state.orderTasksRequestId = 0;
  renderOrderTasks();
}

function renderOrderTasks() {
  if (!orderTasksList) return;
  const selectedOrderId = state.selectedOrderId;
  const tasksBelongToSelection =
    selectedOrderId !== null && state.orderTasksOrderId === selectedOrderId;
  const canModify = canModifyOrderTasks();
  const shouldShowForm = tasksBelongToSelection && canModify;

  if (orderTaskForm) {
    orderTaskForm.classList.toggle('hidden', !shouldShowForm);
  }
  if (orderTaskDescriptionInput) {
    orderTaskDescriptionInput.disabled = !canModify;
  }
  if (orderTasksPermissionsNotice) {
    const showNotice = tasksBelongToSelection && !canModify;
    orderTasksPermissionsNotice.classList.toggle('hidden', !showNotice);
  }

  if (!tasksBelongToSelection) {
    orderTasksList.classList.add('muted');
    orderTasksList.textContent =
      selectedOrderId === null
        ? 'Selecciona una orden para ver el checklist.'
        : 'Cargando checklist...';
    return;
  }

  if (state.orderTasksLoading) {
    orderTasksList.classList.add('muted');
    orderTasksList.textContent = 'Cargando checklist...';
    return;
  }

  const tasks = Array.isArray(state.orderTasks) ? state.orderTasks : [];
  orderTasksList.innerHTML = '';
  if (!tasks.length) {
    orderTasksList.classList.add('muted');
    orderTasksList.textContent = 'No hay tareas registradas.';
    return;
  }

  orderTasksList.classList.remove('muted');
  const list = document.createElement('ul');
  list.className = 'order-task-list';

  tasks.forEach((task, index) => {
    const item = document.createElement('li');
    item.className = 'order-task-item';

    const label = document.createElement('label');
    label.className = 'order-task-label';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = task.status === ORDER_TASK_STATUS_COMPLETED;
    checkbox.disabled = !canModify;
    checkbox.addEventListener('change', () => handleOrderTaskToggle(task.id, checkbox));
    label.appendChild(checkbox);

    const description = document.createElement('span');
    description.className = 'order-task-description';
    const rawDescription = typeof task.description === 'string' ? task.description.trim() : '';
    const fallbackLabel = 'Trabajo sin descripción';
    const displayDescription = rawDescription || fallbackLabel;
    description.textContent = displayDescription;
    description.title = displayDescription;
    label.appendChild(description);

    item.appendChild(label);

    const meta = document.createElement('div');
    meta.className = 'order-task-meta';

    if (task.updated_at) {
      const updated = document.createElement('span');
      updated.className = 'order-task-updated';
      updated.textContent = `Actualizado: ${formatDate(task.updated_at)}`;
      meta.appendChild(updated);
    }

    if (meta.children.length > 0) {
      item.appendChild(meta);
    }

    list.appendChild(item);
  });

  orderTasksList.appendChild(list);
}

async function refreshOrderTasks(orderId) {
  if (!state.token) return;
  const requestId = Date.now();
  state.orderTasksRequestId = requestId;
  state.orderTasksOrderId = orderId;
  state.orderTasksLoading = true;
  renderOrderTasks();
  try {
    const tasks = await apiFetch(`/orders/${orderId}/tasks`);
    if (state.orderTasksRequestId !== requestId) {
      return;
    }
    const normalized = Array.isArray(tasks) ? tasks : [];
    state.orderTasks = sortOrderTasks(normalized);
  } catch (error) {
    if (state.orderTasksRequestId === requestId) {
      state.orderTasks = [];
      showToast(error.message, 'error');
    }
  } finally {
    if (state.orderTasksRequestId === requestId) {
      state.orderTasksLoading = false;
      renderOrderTasks();
    }
  }
}

function applyOrderTaskUpdate(updatedTask) {
  if (!updatedTask || typeof updatedTask !== 'object') return;
  if (state.orderTasksOrderId !== updatedTask.order_id) {
    return;
  }
  const tasks = Array.isArray(state.orderTasks) ? [...state.orderTasks] : [];
  const index = tasks.findIndex((task) => task.id === updatedTask.id);
  if (index === -1) {
    tasks.push(updatedTask);
  } else {
    tasks[index] = updatedTask;
  }
  state.orderTasks = sortOrderTasks(tasks);
  renderOrderTasks();
}

async function handleOrderTaskToggle(taskId, checkbox) {
  if (state.selectedOrderId === null || !checkbox) {
    return;
  }
  if (!canModifyOrderTasks()) {
    renderOrderTasks();
    return;
  }
  if (state.orderTasksOrderId !== state.selectedOrderId) {
    checkbox.checked = state.orderTasks.find((task) => task.id === taskId)?.status === ORDER_TASK_STATUS_COMPLETED;
    checkbox.disabled = !canModifyOrderTasks();
    return;
  }
  const currentTask = state.orderTasks.find((task) => task.id === taskId);
  const previousStatus = currentTask?.status || ORDER_TASK_STATUS_PENDING;
  const desiredStatus = checkbox.checked
    ? ORDER_TASK_STATUS_COMPLETED
    : ORDER_TASK_STATUS_PENDING;
  if (desiredStatus === previousStatus) {
    checkbox.disabled = !canModifyOrderTasks();
    return;
  }
  checkbox.disabled = true;
  try {
    const updatedTask = await apiFetch(`/orders/${state.selectedOrderId}/tasks/${taskId}`, {
      method: 'PATCH',
      body: { status: desiredStatus },
    });
    applyOrderTaskUpdate(updatedTask);
    showToast('Checklist actualizado.', 'success');
  } catch (error) {
    checkbox.checked = previousStatus === ORDER_TASK_STATUS_COMPLETED;
    showToast(error.message, 'error');
  } finally {
    checkbox.disabled = !canModifyOrderTasks();
  }
}

async function handleOrderTaskCreate(event) {
  if (event) {
    event.preventDefault();
  }
  if (state.selectedOrderId === null) {
    showToast('Selecciona una orden antes de agregar tareas.', 'error');
    return;
  }
  if (state.orderTasksOrderId !== state.selectedOrderId) {
    showToast('Selecciona una orden antes de agregar tareas.', 'error');
    return;
  }
  if (!canModifyOrderTasks()) {
    showToast('No tienes permisos para modificar el checklist.', 'error');
    return;
  }
  const descriptionValue = orderTaskDescriptionInput?.value.trim() || '';
  if (!descriptionValue) {
    showToast('Ingresa la descripción del trabajo antes de agregarlo.', 'error');
    if (orderTaskDescriptionInput) {
      orderTaskDescriptionInput.focus();
    }
    return;
  }

  const submitButton = orderTaskAddButton;
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.setAttribute('aria-busy', 'true');
  }
  try {
    const body = { description: descriptionValue };
    const newTask = await apiFetch(`/orders/${state.selectedOrderId}/tasks`, {
      method: 'POST',
      body,
    });
    applyOrderTaskUpdate(newTask);
    if (orderTaskDescriptionInput) {
      orderTaskDescriptionInput.value = '';
      orderTaskDescriptionInput.focus();
    }
    showToast('Tarea añadida al checklist.', 'success');
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
      submitButton.removeAttribute('aria-busy');
    }
  }
}

async function apiFetch(path, { method = 'GET', body, headers = {}, auth = true } = {}) {
  const options = { method, headers: { ...headers } };
  if (body !== undefined) {
    options.body = JSON.stringify(body);
    options.headers['Content-Type'] = 'application/json';
  }
  if (auth && state.token) {
    options.headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (response.status === 204) {
    return null;
  }

  let data = null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    if (response.status === 401 && state.token) {
      handleLogout(true);
    }
    let message = 'Error en la solicitud';
    if (data) {
      if (Array.isArray(data.detail)) {
        message = data.detail
          .map((item) => {
            if (item?.msg) return item.msg;
            if (item?.detail) return item.detail;
            if (item?.message) return item.message;
            if (typeof item === 'string') return item;
            try {
              return JSON.stringify(item);
            } catch (error) {
              return 'Error en la solicitud';
            }
          })
          .join(' ');
      } else if (typeof data.detail === 'string') {
        message = data.detail;
      } else if (data.detail?.msg) {
        message = data.detail.msg;
      } else if (data.detail?.message) {
        message = data.detail.message;
      } else if (typeof data.message === 'string') {
        message = data.message;
      } else if (typeof data === 'string') {
        message = data;
      }
    }
    throw new Error(message || 'Error en la solicitud');
  }

  return data;
}

function renderPublicOrderResults(orders) {
  if (!orderResultContainer) return;
  orderResultContainer.classList.remove('hidden');
  if (!orders?.length) {
    orderResultContainer.innerHTML = '<p>No se encontraron órdenes con los datos ingresados.</p>';
    return;
  }

  const listHtml = orders
    .map((order) => {
      const deliveryLabel = order.delivery_date ? formatDeliveryDateDisplay(order) : '';
      const deliveryInfo = deliveryLabel
        ? `<p><strong>Fecha tentativa de entrega:</strong> ${deliveryLabel}</p>`
        : `<p><strong>Fecha tentativa de entrega:</strong> <span class="muted">Sin definir</span></p>`;
      const invoiceInfo = order.invoice_number
        ? `<p class="muted">Factura: ${order.invoice_number}</p>`
        : '<p class="muted">Factura: Sin registrar</p>';
      return `
        <article class="public-order-card">
          <header>
            <h3>Orden ${order.order_number}</h3>
            ${invoiceInfo}
          </header>
          <p><strong>Cliente:</strong> ${order.customer_name || '—'}</p>
          <p><strong>Estado:</strong> ${order.status || 'Sin estado'}</p>
          ${deliveryInfo}
        </article>
      `;
    })
    .join('');

  orderResultContainer.innerHTML = `
    <h3>Resultados (${orders.length})</h3>
    <div class="public-order-list">${listHtml}</div>
  `;
}

function clearOrderResult() {
  if (!orderResultContainer) return;
  orderResultContainer.classList.add('hidden');
  orderResultContainer.innerHTML = '';
}

if (orderLookupForm) {
  orderLookupForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const orderNumber = orderNumberInput?.value.trim();
    const customerDocument = orderDocumentInput?.value.trim();
    if (!orderNumber && !customerDocument) {
      showToast('Ingresa el número de orden o la cédula para continuar.', 'error');
      return;
    }
    const params = new URLSearchParams();
    if (orderNumber) params.append('order_number', orderNumber);
    if (customerDocument) params.append('customer_document', customerDocument);
    try {
      const orders = await apiFetch(`/public/orders?${params.toString()}`, { auth: false });
      renderPublicOrderResults(orders);
    } catch (error) {
      orderResultContainer.classList.remove('hidden');
      orderResultContainer.innerHTML = `<p>${error.message}</p>`;
      showToast(error.message, 'error');
    }
  });
}

function populateStatusSelect(selectElement, selectedValue = '') {
  if (!selectElement) return;
  selectElement.innerHTML = '';
  state.statuses.forEach((statusValue) => {
    const option = document.createElement('option');
    option.value = statusValue;
    option.textContent = statusValue;
    if (selectedValue && selectedValue === statusValue) {
      option.selected = true;
    }
    selectElement.appendChild(option);
  });
}

function populateTailorSelect(selectElement, selectedId = '') {
  if (!selectElement) return;
  selectElement.innerHTML = '';
  const emptyOption = document.createElement('option');
  emptyOption.value = '';
  emptyOption.textContent = 'Sin asignar';
  selectElement.appendChild(emptyOption);
  state.tailors.forEach((tailor) => {
    const option = document.createElement('option');
    option.value = String(tailor.id);
    option.textContent = tailor.full_name;
    if (selectedId && String(selectedId) === String(tailor.id)) {
      option.selected = true;
    }
    selectElement.appendChild(option);
  });
}

function populateVendorSelect(selectElement, selectedId = '', selectedLabel = '') {
  if (!selectElement) return;
  selectElement.innerHTML = '';
  const emptyOption = document.createElement('option');
  emptyOption.value = '';
  emptyOption.textContent = 'Sin asignar';
  selectElement.appendChild(emptyOption);
  let hasSelected = false;
  state.vendors.forEach((vendor) => {
    const option = document.createElement('option');
    option.value = String(vendor.id);
    option.textContent = vendor.full_name;
    if (selectedId && String(selectedId) === String(vendor.id)) {
      option.selected = true;
      hasSelected = true;
    }
    selectElement.appendChild(option);
  });
  if (selectedId && !hasSelected) {
    const fallbackOption = document.createElement('option');
    fallbackOption.value = String(selectedId);
    fallbackOption.textContent = selectedLabel || 'Vendedor seleccionado';
    fallbackOption.selected = true;
    selectElement.appendChild(fallbackOption);
  }
}

function populateNewOrderTaskResponsibles() {
  if (!newOrderTasksList) return;

  const responsibleSelects = newOrderTasksList.querySelectorAll(
    'select[data-role="task-responsible"], select[data-field="responsible"]'
  );

  if (!responsibleSelects.length) return;

  responsibleSelects.forEach((selectElement) => {
    const selectedValue = selectElement.value || '';
    populateTailorSelect(selectElement, selectedValue);
  });
}

function populateEstablishmentSelect(selectElement, selectedValue = '') {
  if (!selectElement) return;
  const normalizedSelected = selectedValue || '';
  selectElement.innerHTML = '';

  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Selecciona un establecimiento';
  placeholder.disabled = true;
  placeholder.hidden = true;
  if (!normalizedSelected) {
    placeholder.selected = true;
  }
  selectElement.appendChild(placeholder);

  ESTABLISHMENTS.forEach((branch) => {
    const option = document.createElement('option');
    option.value = branch;
    option.textContent = branch;
    if (branch === normalizedSelected) {
      option.selected = true;
    }
    selectElement.appendChild(option);
  });
}

function populateCustomerSelect(selectElement, selectedId) {
  if (!selectElement) return;
  const selectedValue =
    selectedId !== undefined && selectedId !== null && selectedId !== ''
      ? String(selectedId)
      : selectElement.value || '';
  selectElement.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = 'Selecciona un cliente';
  if (!selectedValue) {
    placeholder.selected = true;
  }
  selectElement.appendChild(placeholder);
  (state.customerOptions || []).forEach((customer) => {
    const option = document.createElement('option');
    option.value = String(customer.id);
    option.textContent = `${customer.full_name} (${customer.document_id})`;
    if (selectedValue && String(selectedValue) === String(customer.id)) {
      option.selected = true;
    }
    selectElement.appendChild(option);
  });
}

let measurementRowIdCounter = 0;
let newOrderTaskRowIdCounter = 0;

function createMeasurementRowElement(data = { nombre: '', valor: '' }, onRemove) {
  const row = document.createElement('div');
  row.className = 'measurement-row';

  measurementRowIdCounter += 1;
  const rowId = `measurement-${measurementRowIdCounter}`;
  const nameId = `${rowId}-name`;
  const valueId = `${rowId}-value`;

  const nameField = document.createElement('div');
  nameField.className = 'measurement-field';

  const nameLabel = document.createElement('label');
  nameLabel.className = 'sr-only';
  nameLabel.setAttribute('for', nameId);
  nameLabel.textContent = 'Nombre de la medida';

  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.id = nameId;
  nameInput.placeholder = 'Ej. Pecho';
  nameInput.value = data.nombre || '';
  nameInput.dataset.field = 'nombre';

  nameField.appendChild(nameLabel);
  nameField.appendChild(nameInput);

  const valueField = document.createElement('div');
  valueField.className = 'measurement-field';

  const valueLabel = document.createElement('label');
  valueLabel.className = 'sr-only';
  valueLabel.setAttribute('for', valueId);
  valueLabel.textContent = 'Valor de la medida';

  const valueInput = document.createElement('input');
  valueInput.type = 'text';
  valueInput.id = valueId;
  valueInput.placeholder = 'Ej. 98 cm';
  valueInput.value = data.valor || '';
  valueInput.dataset.field = 'valor';

  valueField.appendChild(valueLabel);
  valueField.appendChild(valueInput);

  const removeButton = document.createElement('button');
  removeButton.type = 'button';
  removeButton.className = 'danger ghost';
  removeButton.textContent = 'Eliminar';
  removeButton.addEventListener('click', () => {
    row.remove();
    if (typeof onRemove === 'function') {
      onRemove();
    }
  });

  row.appendChild(nameField);
  row.appendChild(valueField);
  row.appendChild(removeButton);

  return row;
}

function addMeasurementRow(data = { nombre: '', valor: '' }) {
  if (!measurementsList) return;
  const row = createMeasurementRowElement(data, () => ensureMeasurementRow());
  measurementsList.appendChild(row);
}

function highlightMeasurementRow(row) {
  if (!row) return;
  row.classList.add('is-highlighted');
  setTimeout(() => {
    row.classList.remove('is-highlighted');
  }, 1500);
}

function ensureAvailableMeasurementSlot() {
  if (!measurementsList) return;
  const rows = Array.from(measurementsList.querySelectorAll('.measurement-row'));
  const hasEmptyRow = rows.some((row) => {
    const nameInput = row.querySelector('input[data-field="nombre"]');
    const valueInput = row.querySelector('input[data-field="valor"]');
    return (
      nameInput &&
      valueInput &&
      !nameInput.value.trim() &&
      !valueInput.value.trim()
    );
  });
  if (!hasEmptyRow) {
    addMeasurementRow();
  }
}

function applyMeasurementToOrder(measurement) {
  if (!measurementsList) {
    return false;
  }
  if (!measurement) {
    return false;
  }
  const nombreSource = measurement.nombre;
  const valorSource = measurement.valor;
  const nombre =
    typeof nombreSource === 'string'
      ? nombreSource.trim()
      : nombreSource !== null && nombreSource !== undefined
        ? nombreSource.toString().trim()
        : '';
  const valor =
    typeof valorSource === 'string'
      ? valorSource.trim()
      : valorSource !== null && valorSource !== undefined
        ? valorSource.toString().trim()
        : '';
  if (!nombre || !valor) {
    return false;
  }

  const rows = Array.from(measurementsList.querySelectorAll('.measurement-row'));
  let targetRow = rows.find((row) => {
    const nameInput = row.querySelector('input[data-field="nombre"]');
    const valueInput = row.querySelector('input[data-field="valor"]');
    return (
      nameInput &&
      valueInput &&
      !nameInput.value.trim() &&
      !valueInput.value.trim()
    );
  });

  if (!targetRow) {
    addMeasurementRow({ nombre, valor });
    targetRow = measurementsList.lastElementChild;
  }

  if (!targetRow) {
    return false;
  }

  const nameInput = targetRow.querySelector('input[data-field="nombre"]');
  const valueInput = targetRow.querySelector('input[data-field="valor"]');
  if (!nameInput || !valueInput) {
    return false;
  }

  nameInput.value = nombre;
  valueInput.value = valor;

  nameInput.dispatchEvent(new Event('input', { bubbles: true }));
  valueInput.dispatchEvent(new Event('input', { bubbles: true }));

  ensureAvailableMeasurementSlot();
  highlightMeasurementRow(targetRow);
  if (typeof targetRow.scrollIntoView === 'function') {
    targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
  return true;
}

function ensureMeasurementRow() {
  if (measurementsList && measurementsList.children.length === 0) {
    addMeasurementRow();
  }
}

if (addMeasurementButton) {
  addMeasurementButton.addEventListener('click', () => addMeasurementRow());
}

function createOrderTaskRowElement(data = { description: '' }) {

  const row = document.createElement('div');
  row.className = 'measurement-row order-task-input-row';
  row.dataset.role = 'order-task-row';

  newOrderTaskRowIdCounter += 1;
  const rowId = `new-order-task-${newOrderTaskRowIdCounter}`;
  const descriptionId = `${rowId}-description`;

  const descriptionField = document.createElement('div');
  descriptionField.className = 'measurement-field order-task-description-field';

  const labelElement = document.createElement('label');
  labelElement.className = 'order-task-input-label';
  labelElement.dataset.role = 'task-label';
  labelElement.setAttribute('for', descriptionId);
  labelElement.textContent = 'Trabajo #1';

  const descriptionInput = document.createElement('input');
  descriptionInput.type = 'text';
  descriptionInput.id = descriptionId;
  descriptionInput.dataset.field = 'description';
  descriptionInput.placeholder = 'Describe el trabajo a realizar';
  descriptionInput.maxLength = 255;
  descriptionInput.value =
    typeof data.description === 'string' && data.description ? data.description : '';

  descriptionField.appendChild(labelElement);
  descriptionField.appendChild(descriptionInput);


  const removeButton = document.createElement('button');
  removeButton.type = 'button';
  removeButton.className = 'danger ghost';
  removeButton.textContent = 'Eliminar';
  removeButton.addEventListener('click', () => {
    row.remove();
    updateNewOrderTaskLabels();
    ensureNewOrderTaskRow();
  });

  row.appendChild(descriptionField);

  row.appendChild(removeButton);

  return row;
}

function addNewOrderTaskRow(data = { description: '' }) {

  if (!newOrderTasksList) return;
  const row = createOrderTaskRowElement(data);
  newOrderTasksList.appendChild(row);
  updateNewOrderTaskLabels();

}

function ensureNewOrderTaskRow() {
  if (newOrderTasksList && newOrderTasksList.children.length === 0) {
    addNewOrderTaskRow();
  }
  updateNewOrderTaskLabels();
}

function collectNewOrderTasks() {
  if (!newOrderTasksList) {
    return { tasks: [], firstInput: null };
  }
  const rows = Array.from(newOrderTasksList.children);
  const tasks = [];
  let firstInput = null;

  rows.forEach((row) => {
    const input = row.querySelector('input[data-field="description"]');
    if (!input) {
      return;
    }
    if (!firstInput) {
      firstInput = input;
    }
    const value = input.value.trim();
    if (value) {
      tasks.push({ description: value });
    }
  });

  return { tasks, firstInput };
}

function updateNewOrderTaskLabels() {
  if (!newOrderTasksList) return;
  const rows = Array.from(newOrderTasksList.children);
  rows.forEach((row, index) => {
    const label = row.querySelector('[data-role="task-label"]');
    if (label) {
      label.textContent = `Trabajo #${index + 1}`;
    }
  });

}

if (addOrderTaskButton) {
  addOrderTaskButton.addEventListener('click', () => addNewOrderTaskRow());
}

function addMeasurementRowToList(listElement, data = { nombre: '', valor: '' }) {
  if (!listElement) return;
  const row = createMeasurementRowElement(data, () => {
    if (listElement.children.length === 0) {
      addMeasurementRowToList(listElement);
    }
  });
  listElement.appendChild(row);
}

function createMeasurementSetBlock(container, data = { name: '', measurements: [] }) {
  const wrapper = document.createElement('div');
  wrapper.className = 'measurement-set';

  const header = document.createElement('div');
  header.className = 'measurement-set-header';

  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.placeholder = 'Nombre del conjunto (ej. Traje azul)';
  nameInput.value = data.name || '';
  nameInput.dataset.field = 'name';

  const removeButton = document.createElement('button');
  removeButton.type = 'button';
  removeButton.className = 'danger ghost';
  removeButton.textContent = 'Eliminar conjunto';
  removeButton.addEventListener('click', () => {
    wrapper.remove();
  });

  header.appendChild(nameInput);
  header.appendChild(removeButton);

  const measurementList = document.createElement('div');
  measurementList.className = 'measurement-list';

  const addButton = document.createElement('button');
  addButton.type = 'button';
  addButton.className = 'secondary small';
  addButton.textContent = 'Agregar medida';
  addButton.addEventListener('click', () => addMeasurementRowToList(measurementList));

  wrapper.appendChild(header);
  wrapper.appendChild(measurementList);
  wrapper.appendChild(addButton);
  container.appendChild(wrapper);

  if (data.measurements?.length) {
    data.measurements.forEach((item) => addMeasurementRowToList(measurementList, item));
  } else {
    addMeasurementRowToList(measurementList);
  }
}

function collectMeasurementSets(container) {
  if (!container) return [];
  return Array.from(container.querySelectorAll('.measurement-set'))
    .map((setElement) => {
      const nameInput = setElement.querySelector('input[data-field="name"]');
      const name = nameInput?.value.trim();
      const measurements = Array.from(setElement.querySelectorAll('.measurement-row'))
        .map((row) => {
          const nombre = row.querySelector('input[data-field="nombre"]').value.trim();
          const valor = row.querySelector('input[data-field="valor"]').value.trim();
          return nombre && valor ? { nombre, valor } : null;
        })
        .filter(Boolean);
      if (!name) {
        return null;
      }
      return { name, measurements };
    })
    .filter(Boolean);
}

function collectMeasurements() {
  if (!measurementsList) return [];
  return Array.from(measurementsList.querySelectorAll('.measurement-row'))
    .map((row) => {
      const nombre = row.querySelector('input[data-field="nombre"]').value.trim();
      const valor = row.querySelector('input[data-field="valor"]').value.trim();
      return nombre && valor ? { nombre, valor } : null;
    })
    .filter(Boolean);
}

function resetCreateOrderForm() {
  if (!createOrderForm) return;
  createOrderForm.reset();
  populateStatusSelect(statusSelect);
  populateTailorSelect(assignTailorSelect);
  const defaultVendorId =
    state.user?.role === 'vendedor' && state.user?.id ? String(state.user.id) : '';
  const defaultVendorLabel = defaultVendorId ? state.user?.full_name || '' : '';
  populateVendorSelect(assignVendorSelect, defaultVendorId, defaultVendorLabel);
  populateEstablishmentSelect(newOrderOriginSelect);
  populateCustomerSelect(orderCustomerSelect);
  const documentInput = document.getElementById('newCustomerDocument');
  const nameInput = document.getElementById('newCustomerName');
  const contactInput = document.getElementById('newCustomerContact');
  if (newOrderInvoiceInput) newOrderInvoiceInput.value = '';
  if (documentInput) documentInput.value = '';
  if (nameInput) nameInput.value = '';
  if (contactInput) contactInput.value = '';
  measurementsList.innerHTML = '';
  addMeasurementRow();
  if (newOrderTasksList) {
    newOrderTasksList.innerHTML = '';
    addNewOrderTaskRow();
  }
  renderCustomerMeasurementOptions(null);
  clearOrderInvoiceSuggestions();
}

function resetCreateCustomerForm() {
  if (!createCustomerForm) return;
  createCustomerForm.reset();
  if (customerMeasurementsContainer) {
    customerMeasurementsContainer.innerHTML = '';
    createMeasurementSetBlock(customerMeasurementsContainer);
  }
  setContificoLookupStatus(contificoCustomerLookupStatus, '');
  if (fetchContificoCustomerButton) {
    fetchContificoCustomerButton.disabled = false;
  }
}

function applyContificoCustomerData(target, data = {}) {
  if (!data || typeof data !== 'object') return;
  const name = typeof data.full_name === 'string' ? data.full_name.trim() : '';
  const documentId = typeof data.document_id === 'string' ? data.document_id.trim() : '';
  const phone = typeof data.phone === 'string' ? data.phone.trim() : '';
  const email = typeof data.email === 'string' ? data.email.trim() : '';
  const address = typeof data.address === 'string' ? data.address.trim() : '';

  if (target === 'create') {
    if (customerFullNameInput && name) customerFullNameInput.value = name;
    if (customerDocumentInput && documentId) customerDocumentInput.value = documentId;
    if (customerPhoneInput && phone) customerPhoneInput.value = phone;
    if (customerEmailInput && email) customerEmailInput.value = email;
    if (customerAddressInput && address) customerAddressInput.value = address;
    return;
  }

  const nameInput = updateCustomerNameInput || customerDetail?.querySelector('#updateCustomerName');
  const documentInput =
    updateCustomerDocumentInput || customerDetail?.querySelector('#updateCustomerDocument');
  const phoneInput = updateCustomerPhoneInput || customerDetail?.querySelector('#updateCustomerPhone');
  const emailInput = updateCustomerEmailInput || customerDetail?.querySelector('#updateCustomerEmail');
  const addressInput =
    updateCustomerAddressInput || customerDetail?.querySelector('#updateCustomerAddress');

  if (nameInput && name) nameInput.value = name;
  if (documentInput && documentId) documentInput.value = documentId;
  if (phoneInput && phone) phoneInput.value = phone;
  if (emailInput && email) emailInput.value = email;
  if (addressInput && address) addressInput.value = address;
}

async function handleContificoCustomerLookup(source) {
  const isCreate = source === 'create';
  const documentInput = isCreate
    ? customerDocumentInput
    : updateCustomerDocumentInput || customerDetail?.querySelector('#updateCustomerDocument');
  const statusElement = isCreate
    ? contificoCustomerLookupStatus
    : updateContificoCustomerLookupStatus;
  const triggerButton = isCreate ? fetchContificoCustomerButton : updateCustomerFetchContificoButton;

  if (!documentInput) return;

  const rawDocument = documentInput.value || '';
  const normalizedDocument = rawDocument.trim();
  if (!normalizedDocument) {
    setContificoLookupStatus(statusElement, 'Ingresa una cédula o RUC para consultar.', 'error');
    documentInput.focus();
    return;
  }

  setContificoLookupStatus(statusElement, 'Buscando datos en Contífico...', 'info');
  if (triggerButton) {
    triggerButton.disabled = true;
  }
  try {
    const data = await apiFetch(
      `/integrations/contifico/customers/${encodeURIComponent(normalizedDocument)}`
    );
    applyContificoCustomerData(source, data || {});
    if (documentInput && normalizedDocument) {
      const returnedDocument =
        typeof data?.document_id === 'string' ? data.document_id.trim() : '';
      documentInput.value = returnedDocument || normalizedDocument;
    }
    setContificoLookupStatus(
      statusElement,
      'Datos importados desde Contífico. Puedes ajustarlos antes de guardar.',
      'success'
    );
  } catch (error) {
    setContificoLookupStatus(statusElement, error.message || 'No se pudo obtener la información.', 'error');
  } finally {
    if (triggerButton) {
      triggerButton.disabled = false;
    }
  }
}

function updateModalBodyState() {
  if (typeof document === 'undefined' || !document.body) return;
  const hasOpenModal = Boolean(document.querySelector('.modal-overlay:not(.hidden)'));
  document.body.classList.toggle('modal-open', hasOpenModal);
}

function setCreateCustomerVisible(visible) {
  if (!createCustomerSection || !customerCreateOverlay) return;
  state.isCreateCustomerVisible = visible;
  createCustomerSection.classList.toggle('hidden', !visible);
  createCustomerSection.setAttribute('aria-hidden', visible ? 'false' : 'true');
  customerCreateOverlay.classList.toggle('hidden', !visible);
  customerCreateOverlay.setAttribute('aria-hidden', visible ? 'false' : 'true');
  if (showCreateCustomerButton) {
    showCreateCustomerButton.classList.toggle('hidden', visible);
  }
  if (visible) {
    lastCreateCustomerTrigger = document.activeElement;
    if (customerMeasurementsContainer && !customerMeasurementsContainer.children.length) {
      createMeasurementSetBlock(customerMeasurementsContainer);
    }
    requestAnimationFrame(() => {
      if (customerCreateDialog?.isConnected) {
        customerCreateDialog.focus();
      }
      const firstField = createCustomerForm?.querySelector('input, textarea, select');
      firstField?.focus();
    });
  } else {
    if (
      state.pendingOrderCustomerSelection?.source === 'order' &&
      !state.pendingOrderCustomerSelection?.customerId
    ) {
      state.pendingOrderCustomerSelection = null;
    }
    resetCreateCustomerForm();
    const trigger = lastCreateCustomerTrigger;
    lastCreateCustomerTrigger = null;
    if (trigger?.isConnected) {
      trigger.focus();
    } else if (showCreateCustomerButton?.isConnected) {
      showCreateCustomerButton.focus();
    }
  }
  updateModalBodyState();
}

function setCustomerDetailVisible(visible) {
  if (!customerDetail || !customerDetailOverlay) return;
  state.isCustomerDetailVisible = visible;
  customerDetail.classList.toggle('hidden', !visible);
  customerDetail.setAttribute('aria-hidden', visible ? 'false' : 'true');
  customerDetailOverlay.classList.toggle('hidden', !visible);
  customerDetailOverlay.setAttribute('aria-hidden', visible ? 'false' : 'true');
  if (visible) {
    requestAnimationFrame(() => {
      if (customerDetailDialog?.isConnected) {
        customerDetailDialog.focus();
      }
    });
  }
  updateModalBodyState();
}

function setContificoCustomerInvoicesVisible(visible) {
  if (!contificoCustomerInvoicesModal || !contificoCustomerInvoicesOverlay) return;
  const normalizedVisible = Boolean(visible);
  if (state.contificoCustomerInvoicesModalVisible === normalizedVisible) {
    updateModalBodyState();
    return;
  }
  state.contificoCustomerInvoicesModalVisible = normalizedVisible;
  contificoCustomerInvoicesModal.classList.toggle('hidden', !normalizedVisible);
  contificoCustomerInvoicesModal.setAttribute('aria-hidden', normalizedVisible ? 'false' : 'true');
  contificoCustomerInvoicesOverlay.classList.toggle('hidden', !normalizedVisible);
  contificoCustomerInvoicesOverlay.setAttribute('aria-hidden', normalizedVisible ? 'false' : 'true');
  if (normalizedVisible) {
    lastContificoCustomerInvoicesTrigger = document.activeElement;
    requestAnimationFrame(() => {
      if (contificoCustomerInvoicesDialog?.isConnected) {
        contificoCustomerInvoicesDialog.focus();
      }
    });
  } else {
    if (lastContificoCustomerInvoicesTrigger?.isConnected) {
      lastContificoCustomerInvoicesTrigger.focus();
    } else if (contificoCustomerInvoicesModalButton?.isConnected) {
      contificoCustomerInvoicesModalButton.focus();
    }
    lastContificoCustomerInvoicesTrigger = null;
  }
  updateModalBodyState();
}

function setContificoInvoiceLookupVisible(visible) {
  if (!contificoInvoiceLookupModal || !contificoInvoiceLookupOverlay) return;
  const normalizedVisible = Boolean(visible);
  if (state.contificoInvoiceLookupModalVisible === normalizedVisible) {
    updateModalBodyState();
    return;
  }
  logInvoiceLookupInfo(normalizedVisible ? 'Mostrando modal de factura puntual.' : 'Ocultando modal de factura puntual.', {
    requestId: state.contificoPreviewInvoiceLookupRequestId || null,
    visible: normalizedVisible,
  });
  state.contificoInvoiceLookupModalVisible = normalizedVisible;
  contificoInvoiceLookupModal.classList.toggle('hidden', !normalizedVisible);
  contificoInvoiceLookupModal.setAttribute('aria-hidden', normalizedVisible ? 'false' : 'true');
  contificoInvoiceLookupOverlay.classList.toggle('hidden', !normalizedVisible);
  contificoInvoiceLookupOverlay.setAttribute('aria-hidden', normalizedVisible ? 'false' : 'true');
  if (normalizedVisible) {
    lastContificoInvoiceLookupTrigger = document.activeElement;
    requestAnimationFrame(() => {
      if (contificoInvoiceLookupDialog?.isConnected) {
        contificoInvoiceLookupDialog.focus();
      }
    });
  } else {
    if (lastContificoInvoiceLookupTrigger?.isConnected) {
      lastContificoInvoiceLookupTrigger.focus();
    } else if (contificoInvoiceLookupModalButton?.isConnected) {
      contificoInvoiceLookupModalButton.focus();
    }
    lastContificoInvoiceLookupTrigger = null;
  }
  updateModalBodyState();
}

function renderCustomerMeasurementOptions(customer) {
  if (!customerMeasurementOptions) return;
  if (!customer) {
    customerMeasurementOptions.classList.add('muted');
    customerMeasurementOptions.innerHTML = 'Selecciona un cliente para ver sus medidas guardadas.';
    return;
  }
  if (!customer.measurements?.length) {
    customerMeasurementOptions.classList.add('muted');
    customerMeasurementOptions.innerHTML = 'El cliente no tiene medidas guardadas.';
    return;
  }
  customerMeasurementOptions.classList.remove('muted');
  customerMeasurementOptions.innerHTML = '';
  customer.measurements.forEach((set) => {
    const card = document.createElement('div');
    card.className = 'measurement-option';

    const header = document.createElement('div');
    header.className = 'measurement-option-header';

    const title = document.createElement('strong');
    title.textContent = set.name;

    const useButton = document.createElement('button');
    useButton.type = 'button';
    useButton.className = 'secondary small';
    useButton.textContent = 'Usar en la orden';
    useButton.addEventListener('click', () => {
      measurementsList.innerHTML = '';
      if (set.measurements?.length) {
        set.measurements.forEach((item) => addMeasurementRow(item));
      }
      ensureMeasurementRow();
      showToast(`Se aplicaron las medidas del conjunto "${set.name}".`, 'success');
    });

    header.appendChild(title);
    header.appendChild(useButton);

    const tags = document.createElement('div');
    tags.className = 'measurement-tags';
    if (set.measurements?.length) {
      set.measurements.forEach((item) => {
        const tagButton = document.createElement('button');
        tagButton.type = 'button';
        tagButton.className = 'tag measurement-tag-button';
        tagButton.textContent = `${item.nombre}: ${item.valor}`;
        tagButton.title = 'Copiar esta medida a la orden';
        tagButton.addEventListener('click', () => {
          const applied = applyMeasurementToOrder(item);
          if (applied) {
            showToast(`Se copió la medida "${item.nombre}" a la orden.`, 'success');
          } else {
            showToast('No se pudo copiar la medida. Regístrala manualmente.', 'error');
          }
        });
        tags.appendChild(tagButton);
      });
    } else {
      const empty = document.createElement('span');
      empty.className = 'muted';
      empty.textContent = 'Sin medidas registradas';
      tags.appendChild(empty);
    }

    card.appendChild(header);
    card.appendChild(tags);
    customerMeasurementOptions.appendChild(card);
  });
}
function updateUserInfo() {
  if (!state.user) {
    updateUserCreationForm();
    return;
  }
  if (currentUserNameElement) {
    currentUserNameElement.textContent = state.user.full_name;
  }
  if (currentUserRoleElement) {
    currentUserRoleElement.textContent = ROLE_LABELS[state.user.role] || state.user.role;
  }
  if (deleteCustomerButton) {
    if (state.user.role === 'administrador') {
      deleteCustomerButton.classList.remove('hidden');
    } else {
      deleteCustomerButton.classList.add('hidden');
    }
  }
  if (deleteOrderButton) {
    if (state.user.role === 'administrador') {
      deleteOrderButton.classList.remove('hidden');
      deleteOrderButton.disabled = state.selectedOrderId === null;
    } else {
      deleteOrderButton.classList.add('hidden');
      deleteOrderButton.disabled = true;
    }
  }
  const isAdmin = state.user.role === 'administrador';
  if (!isAdmin && ADMIN_ONLY_TABS.has(activeDashboardTab)) {
    setActiveDashboardTab('ordersPanel');
  } else {
    setActiveDashboardTab(activeDashboardTab);
  }
  applyRoleVisibility();
  updateUserCreationForm();
  renderOrderTasks();
  updateDashboardShortcutVisibility();
  updateOrderActionButtons();
  renderContificoPreview();
}

function showDashboard() {
  if (staffDashboard) {
    staffDashboard.classList.remove('hidden');
  }
  if (staffLoginCard) {
    staffLoginCard.classList.add('hidden');
  }
  setActiveDashboardTab('ordersPanel');
}

function hideDashboard() {
  if (staffDashboard) {
    staffDashboard.classList.add('hidden');
  }
  if (staffLoginCard) {
    staffLoginCard.classList.remove('hidden');
  }
}

function updateNavigationForAuth() {
  const isAuthenticated = Boolean(state.token);
  if (panelNavButton) {
    panelNavButton.classList.toggle('hidden', !isAuthenticated);
  }
  if (loginNavButton) {
    loginNavButton.classList.toggle('hidden', isAuthenticated);
    if (isAuthenticated) {
      loginNavButton.classList.remove('active');
    }
  }
  updateDashboardShortcutVisibility();
  updateOrderInvoiceLookupButtonState();
}

async function bootstrapAuthenticatedSession({ showWelcomeToast = false } = {}) {
  state.customerSearchTerm = '';
  state.orderSearchTerm = '';
  if (customerSearchInput) {
    customerSearchInput.value = '';
  }
  if (orderSearchInput) {
    orderSearchInput.value = '';
  }

  await loadCurrentUser();
  updateUserInfo();
  await loadStatuses();
  await loadTailors();
  await loadVendors();
  await loadCustomers();
  await refreshCustomerOptions();
  await loadOrders();
  if (state.user?.role === 'administrador') {
    await loadUsers();
    await loadAuditLogs();
  } else {
    state.users = [];
    state.usersLoaded = false;
    state.usersLoadError = null;
    renderUsers();
  }

  setCreateCustomerVisible(false);
  setCreateUserVisible(false);
  resetCreateOrderForm();
  showDashboard();
  updateNavigationForAuth();
  setActiveView('staff-view');

  if (showWelcomeToast) {
    showToast('Bienvenido, sesión iniciada.', 'success');
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const usernameInput = document.getElementById('username').value.trim();
  const username = usernameInput.toLocaleLowerCase();
  const password = document.getElementById('password').value.trim();
  const submitButton = staffLoginForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  try {
    const tokenResponse = await apiFetch('/auth/login', {
      method: 'POST',
      body: { username, password },
      auth: false,
    });
    const rawToken = typeof tokenResponse?.access_token === 'string' ? tokenResponse.access_token : '';
    const accessToken = rawToken.trim();
    if (!accessToken) {
      throw new Error('Token de autenticación inválido.');
    }
    state.token = accessToken;
    persistToken(state.token);
    await bootstrapAuthenticatedSession({ showWelcomeToast: true });
  } catch (error) {
    if (state.token) {
      handleLogout(false);
    }
    showToast(error.message, 'error');
  } finally {
    submitButton.disabled = false;
  }
}

async function loadStatuses() {
  const statuses = await apiFetch('/statuses', { auth: false });
  state.statuses = statuses;
  populateStatusSelect(statusSelect);
  if (orderDetailStatusSelect) {
    const selectedStatus =
      state.selectedOrderId !== null
        ? state.orders.find((order) => order.id === state.selectedOrderId)?.status
        : orderDetailStatusSelect.value;
    populateStatusSelect(orderDetailStatusSelect, selectedStatus);
  }
}

async function loadTailors() {
  if (!state.token) return;
  try {
    state.tailors = await apiFetch('/users/tailors');
  } catch (error) {
    showToast(error.message, 'error');
  }
  populateTailorSelect(assignTailorSelect);
  populateTailorSelect(orderTaskResponsibleSelect);
  populateNewOrderTaskResponsibles();
  if (orderDetailTailorSelect) {
    const selectedValue =
      orderDetailTailorSelect.value ||
      (state.selectedOrderId !== null
        ? state.orders.find((order) => order.id === state.selectedOrderId)?.assigned_tailor?.id ?? ''
        : '');
    populateTailorSelect(orderDetailTailorSelect, selectedValue);
  }
}

async function loadVendors() {
  if (!state.token) return;
  const role = state.user?.role;
  if (role !== 'administrador' && role !== 'vendedor') {
    state.vendors = [];
    populateVendorSelect(assignVendorSelect);
    if (orderDetailVendorSelect) {
      const selectedDetailValue =
        state.selectedOrderId !== null
          ? state.orders.find((order) => order.id === state.selectedOrderId)?.assigned_vendor?.id ?? ''
          : '';
      const selectedDetailLabel =
        state.selectedOrderId !== null
          ? state.orders.find((order) => order.id === state.selectedOrderId)?.assigned_vendor?.full_name || ''
          : '';
      populateVendorSelect(orderDetailVendorSelect, selectedDetailValue, selectedDetailLabel);
    }
    return;
  }
  try {
    state.vendors = await apiFetch('/users/vendors');
  } catch (error) {
    state.vendors = [];
    showToast(error.message, 'error');
  }
  let selectedCreateValue = assignVendorSelect?.value || '';
  let selectedCreateLabel = '';
  if (!selectedCreateValue && state.user?.role === 'vendedor' && state.user?.id) {
    selectedCreateValue = String(state.user.id);
    selectedCreateLabel = state.user?.full_name || '';
  }
  populateVendorSelect(assignVendorSelect, selectedCreateValue, selectedCreateLabel);
  if (orderDetailVendorSelect) {
    let selectedDetailValue = orderDetailVendorSelect.value || '';
    let selectedDetailLabel = '';
    if (!selectedDetailValue && state.selectedOrderId !== null) {
      const activeOrder = state.orders.find((order) => order.id === state.selectedOrderId);
      if (activeOrder?.assigned_vendor?.id) {
        selectedDetailValue = String(activeOrder.assigned_vendor.id);
        selectedDetailLabel = activeOrder.assigned_vendor.full_name || '';
      }
    }
    populateVendorSelect(orderDetailVendorSelect, selectedDetailValue, selectedDetailLabel);
  }
}

async function loadOrders({ page, pageSize } = {}) {
  if (!state.token) return null;
  const requestedPage = Number(page);
  const normalizedPage = Number.isFinite(requestedPage) && requestedPage > 0
    ? requestedPage
    : Number(state.orderPage) || 1;
  const requestedPageSize = Number(pageSize ?? state.orderPageSize ?? DEFAULT_PAGE_SIZE);
  const normalizedPageSize = getValidPageSize(requestedPageSize);
  const params = new URLSearchParams({
    page: String(Math.max(normalizedPage, 1)),
    page_size: String(normalizedPageSize),
  });
  const trimmedSearch = state.orderSearchTerm.trim();
  if (trimmedSearch) {
    params.set('search', trimmedSearch);
  }
  const requestId = Date.now();
  state.orderRequestId = requestId;
  try {
    const response = await apiFetch(`/orders?${params.toString()}`);
    if (state.orderRequestId !== requestId) {
      return null;
    }
    const items = Array.isArray(response?.items) ? response.items : [];
    const total = typeof response?.total === 'number' ? response.total : items.length;
    const resolvedPageSize = getValidPageSize(response?.page_size ?? normalizedPageSize);
    const resolvedPage = response?.page && response.page > 0 ? response.page : 1;
    state.orders = items;
    state.orderTotal = total;
    state.orderPageSize = resolvedPageSize;
    state.orderPage = resolvedPage;
    if (state.selectedOrderId !== null) {
      const selected = items.find((order) => order.id === state.selectedOrderId);
      if (selected) {
        populateOrderDetail(selected, { skipRender: true, focusOnDetail: false });
      } else {
        clearOrderDetail({ skipRender: true });
      }
    }
    renderOrders();
    return response;
  } catch (error) {
    if (state.orderRequestId === requestId) {
      showToast(error.message, 'error');
    }
    return null;
  }
}

async function loadKanbanOrders({ force = false } = {}) {
  if (!state.token) {
    state.kanbanOrders = [];
    state.kanbanLastUpdated = null;
    state.kanbanNeedsRefresh = true;
    renderOrderKanban();
    return;
  }

  if (state.kanbanLoading) {
    return;
  }

  if (!force && !state.kanbanNeedsRefresh && state.kanbanOrders.length) {
    renderOrderKanban();
    return;
  }

  state.kanbanLoading = true;
  state.kanbanError = null;
  renderOrderKanban();

  const collected = [];
  let page = 1;
  let total = 0;

  try {
    while (true) {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(KANBAN_FETCH_PAGE_SIZE),
      });
      const response = await apiFetch(`/orders?${params.toString()}`);
      const items = Array.isArray(response?.items) ? response.items : [];
      const reportedTotal = typeof response?.total === 'number' ? response.total : total;
      if (reportedTotal) {
        total = reportedTotal;
      }
      collected.push(...items);
      if (collected.length >= total || !items.length) {
        break;
      }
      page += 1;
    }

    state.kanbanOrders = collected;
    state.kanbanLastUpdated = new Date().toISOString();
    state.kanbanNeedsRefresh = false;
    state.kanbanError = null;
  } catch (error) {
    state.kanbanError = error.message || 'No se pudieron cargar las órdenes.';
    showToast(state.kanbanError, 'error');
  } finally {
    state.kanbanLoading = false;
    renderOrderKanban();
  }
}

function ensureKanbanDataLoaded() {
  if (!state.token || state.activeOrdersView !== 'kanban') {
    renderOrderKanban();
    return;
  }
  if (state.kanbanLoading) {
    renderOrderKanban();
    return;
  }
  if (state.kanbanNeedsRefresh || !state.kanbanOrders.length) {
    loadKanbanOrders({ force: true });
  } else {
    renderOrderKanban();
  }
}

function markKanbanDataStale() {
  state.kanbanNeedsRefresh = true;
  renderOrderKanban();
  const shouldReload =
    activeDashboardTab === 'ordersPanel' &&
    state.activeOrdersView === 'kanban' &&
    state.token &&
    !state.kanbanLoading;
  if (shouldReload) {
    loadKanbanOrders({ force: true });
  }
}

async function loadCustomers({ page, pageSize } = {}) {
  if (!state.token) return null;
  const requestedPage = Number(page);
  const normalizedPage = Number.isFinite(requestedPage) && requestedPage > 0
    ? requestedPage
    : Number(state.customerPage) || 1;
  const requestedPageSize = Number(pageSize ?? state.customerPageSize ?? DEFAULT_PAGE_SIZE);
  const normalizedPageSize = getValidPageSize(requestedPageSize);
  const params = new URLSearchParams({
    page: String(Math.max(normalizedPage, 1)),
    page_size: String(normalizedPageSize),
  });
  const trimmedSearch = state.customerSearchTerm.trim();
  if (trimmedSearch) {
    params.set('search', trimmedSearch);
  }
  const requestId = Date.now();
  state.customerRequestId = requestId;
  try {
    const response = await apiFetch(`/customers?${params.toString()}`);
    if (state.customerRequestId !== requestId) {
      return null;
    }
    const items = Array.isArray(response?.items) ? response.items : [];
    const total = typeof response?.total === 'number' ? response.total : items.length;
    const resolvedPageSize = getValidPageSize(response?.page_size ?? normalizedPageSize);
    const resolvedPage = response?.page && response.page > 0 ? response.page : 1;
    state.customers = items;
    state.customerTotal = total;
    state.customerPageSize = resolvedPageSize;
    state.customerPage = resolvedPage;
    renderCustomers();
    if (orderCustomerSelect) {
      populateCustomerSelect(orderCustomerSelect);
      handleOrderCustomerChange();
    }
    if (state.selectedCustomerId) {
      const selected = items.find((customer) => customer.id === state.selectedCustomerId);
      if (selected) {
        await populateCustomerDetail(selected);
      } else {
        clearCustomerDetail();
      }
    } else {
      clearCustomerDetail();
    }
    return response;
  } catch (error) {
    if (state.customerRequestId === requestId) {
      showToast(error.message, 'error');
    }
    return null;
  }
}

async function refreshCustomerOptions() {
  if (!state.token) return;
  const pageSize = 100;
  const requestId = Date.now();
  state.customerOptionsRequestId = requestId;
  const collected = [];
  let total = 0;
  let page = 1;
  try {
    while (true) {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      const response = await apiFetch(`/customers?${params.toString()}`);
      if (state.customerOptionsRequestId !== requestId) {
        return;
      }
      const items = Array.isArray(response?.items) ? response.items : [];
      total = typeof response?.total === 'number' ? response.total : total;
      collected.push(...items);
      if (collected.length >= total || !items.length) {
        break;
      }
      page += 1;
    }
    state.customerOptions = collected;
    if (orderCustomerSelect) {
      let desiredValue = orderCustomerSelect.value || '';
      if (
        state.pendingOrderCustomerSelection?.source === 'order' &&
        state.pendingOrderCustomerSelection?.customerId
      ) {
        desiredValue = String(state.pendingOrderCustomerSelection.customerId);
      }
      populateCustomerSelect(orderCustomerSelect, desiredValue);
      if (desiredValue) {
        orderCustomerSelect.value = desiredValue;
      }
      handleOrderCustomerChange();
      if (
        state.pendingOrderCustomerSelection?.source === 'order' &&
        state.pendingOrderCustomerSelection?.customerId
      ) {
        state.pendingOrderCustomerSelection = null;
      }
    }
  } catch (error) {
    if (state.customerOptionsRequestId === requestId) {
      showToast(error.message, 'error');
    }
  }
}

async function fetchOrdersForCustomer(customerId) {
  if (!state.token) return [];
  const numericId = Number(customerId);
  if (!Number.isFinite(numericId)) {
    return [];
  }
  const cacheKey = String(numericId);
  const pageSize = 50;
  const collected = [];
  let total = 0;
  let page = 1;
  try {
    while (true) {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        customer_id: String(numericId),
      });
      const response = await apiFetch(`/orders?${params.toString()}`);
      const items = Array.isArray(response?.items) ? response.items : [];
      total = typeof response?.total === 'number' ? response.total : total;
      collected.push(...items);
      if (collected.length >= total || !items.length) {
        break;
      }
      page += 1;
    }
    state.customerOrdersCache[cacheKey] = {
      items: sortOrdersByRecency(collected),
      total: total || collected.length,
      complete: true,
    };
  } catch (error) {
    showToast(error.message, 'error');
    state.customerOrdersCache[cacheKey] = {
      items: sortOrdersByRecency(collected),
      total: collected.length,
      complete: false,
    };
  }
  return state.customerOrdersCache[cacheKey]?.items ?? [];
}

async function loadAuditLogs() {
  if (!state.token || state.user?.role !== 'administrador') return;
  try {
    state.auditLogs = await apiFetch('/audit-logs');
    renderAuditLogs();
  } catch (error) {
    showToast(error.message, 'error');
  }
}

function getCachedCustomerInvoices(customerId) {
  const numericId = Number(customerId);
  if (!Number.isFinite(numericId) || numericId <= 0) {
    return null;
  }
  const cacheKey = String(numericId);
  const cached = state.customerInvoicesCache[cacheKey];
  if (!cached || !Array.isArray(cached.items)) {
    return null;
  }
  return cached;
}

function updateOrderInvoiceLookupButtonState() {
  if (!orderInvoiceLookupButton) return;
  const hasToken = Boolean(state.token);
  const hasCustomer = Number(orderCustomerSelect?.value) > 0;
  const invoiceValue = newOrderInvoiceInput?.value?.trim() || '';
  orderInvoiceLookupButton.disabled =
    !hasToken || state.orderInvoiceLookupLoading || !hasCustomer || !invoiceValue;
}

function renderOrderInvoiceLookupDetails() {
  if (!orderInvoiceLookupDetails) {
    updateOrderInvoiceLookupButtonState();
    return;
  }
  orderInvoiceLookupDetails.innerHTML = '';
  orderInvoiceLookupDetails.classList.remove('status-error', 'status-success');
  const { orderInvoiceLookupLoading, orderInvoiceLookupError, orderInvoiceLookup } = state;
  if (orderInvoiceLookupLoading) {
    orderInvoiceLookupDetails.textContent = 'Consultando factura en Contífico...';
    orderInvoiceLookupDetails.classList.remove('hidden');
  } else if (orderInvoiceLookupError) {
    orderInvoiceLookupDetails.textContent = orderInvoiceLookupError;
    orderInvoiceLookupDetails.classList.remove('hidden');
    orderInvoiceLookupDetails.classList.add('status-error');
  } else if (orderInvoiceLookup) {
    const summary = document.createElement('div');
    summary.className = 'invoice-lookup-summary';
    const number = document.createElement('span');
    number.className = 'invoice-lookup-number';
    number.textContent =
      orderInvoiceLookup.numero || state.orderInvoiceLookupNumber || 'Factura confirmada';
    summary.append('Factura confirmada: ', number);
    orderInvoiceLookupDetails.appendChild(summary);

    const metaValues = [];
    if (orderInvoiceLookup.cliente) {
      metaValues.push(`Cliente: ${orderInvoiceLookup.cliente}`);
    }
    if (orderInvoiceLookup.fecha_emision) {
      metaValues.push(`Emisión: ${formatDate(orderInvoiceLookup.fecha_emision)}`);
    }
    if (orderInvoiceLookup.estado) {
      metaValues.push(`Estado: ${orderInvoiceLookup.estado}`);
    }
    if (
      typeof orderInvoiceLookup.total === 'number' &&
      Number.isFinite(orderInvoiceLookup.total)
    ) {
      metaValues.push(`Total: ${formatCurrencyUSD(orderInvoiceLookup.total)}`);
    }
    if (metaValues.length) {
      const metaList = document.createElement('ul');
      metaList.className = 'invoice-lookup-meta';
      metaValues.forEach((value) => {
        const item = document.createElement('li');
        item.textContent = value;
        metaList.appendChild(item);
      });
      orderInvoiceLookupDetails.appendChild(metaList);
    }
    orderInvoiceLookupDetails.classList.remove('hidden');
    orderInvoiceLookupDetails.classList.add('status-success');
  } else {
    orderInvoiceLookupDetails.classList.add('hidden');
  }
  updateOrderInvoiceLookupButtonState();
}

function clearOrderInvoiceLookup() {
  state.orderInvoiceLookup = null;
  state.orderInvoiceLookupError = null;
  state.orderInvoiceLookupLoading = false;
  state.orderInvoiceLookupCustomerId = null;
  state.orderInvoiceLookupNumber = '';
  state.orderInvoiceLookupRequestId = 0;
  renderOrderInvoiceLookupDetails();
}

function setOrderInvoiceSuggestionsStatus(message, { isError = false } = {}) {
  if (!orderInvoiceSuggestionsStatus) return;
  orderInvoiceSuggestionsStatus.textContent = message || '';
  orderInvoiceSuggestionsStatus.classList.toggle('status-error', Boolean(isError));
}

function renderOrderInvoiceSuggestions() {
  updateOrderInvoiceLookupButtonState();
  if (orderInvoiceSuggestionsList) {
    orderInvoiceSuggestionsList.innerHTML = '';
    const suggestions = Array.isArray(state.orderInvoiceSuggestions)
      ? state.orderInvoiceSuggestions
      : [];
    const seenNumbers = new Set();
    suggestions.forEach((entry) => {
      const invoiceData = entry?.invoice || entry || {};
      const rawNumber = invoiceData?.numero;
      const invoiceNumber = typeof rawNumber === 'string' ? rawNumber.trim() : '';
      if (!invoiceNumber || seenNumbers.has(invoiceNumber)) {
        return;
      }
      seenNumbers.add(invoiceNumber);
      const option = document.createElement('option');
      option.value = invoiceNumber;
      const parts = [invoiceNumber];
      if (invoiceData?.fecha_emision) {
        parts.push(invoiceData.fecha_emision);
      }
      if (typeof invoiceData?.total === 'number' && Number.isFinite(invoiceData.total)) {
        parts.push(formatCurrencyUSD(invoiceData.total));
      }
      option.label = parts.join(' • ');
      orderInvoiceSuggestionsList.appendChild(option);
    });
  }

  if (!state.orderInvoiceSuggestionsCustomerId) {
    setOrderInvoiceSuggestionsStatus(
      'Selecciona un cliente para ver las facturas sugeridas.'
    );
    return;
  }
  if (state.orderInvoiceSuggestionsLoading) {
    setOrderInvoiceSuggestionsStatus('Consultando facturas del cliente...');
    return;
  }
  if (state.orderInvoiceSuggestionsError) {
    setOrderInvoiceSuggestionsStatus(state.orderInvoiceSuggestionsError, { isError: true });
    return;
  }
  if (!state.orderInvoiceSuggestions || !state.orderInvoiceSuggestions.length) {
    setOrderInvoiceSuggestionsStatus('No se encontraron facturas recientes para el cliente.');
    return;
  }
  setOrderInvoiceSuggestionsStatus(
    'Selecciona un número de la lista o ingrésalo manualmente.'
  );
  updateOrderInvoiceLookupButtonState();
}

function clearOrderInvoiceSuggestions() {
  state.orderInvoiceSuggestions = [];
  state.orderInvoiceSuggestionsCustomerId = null;
  state.orderInvoiceSuggestionsError = null;
  state.orderInvoiceSuggestionsLoading = false;
  if (orderInvoiceSuggestionsList) {
    orderInvoiceSuggestionsList.innerHTML = '';
  }
  setOrderInvoiceSuggestionsStatus('Selecciona un cliente para ver las facturas sugeridas.');
  clearOrderInvoiceLookup();
}

async function fetchCustomerInvoicesData(customerId, { force = false } = {}) {
  if (!state.token) {
    throw new Error('Inicia sesión para consultar las facturas del cliente.');
  }
  const numericId = Number(customerId);
  if (!Number.isFinite(numericId) || numericId <= 0) {
    throw new Error('El cliente seleccionado no es válido.');
  }
  const cacheKey = String(numericId);
  if (!force) {
    const cached = getCachedCustomerInvoices(numericId);
    if (cached) {
      return cached;
    }
  }
  const params = new URLSearchParams({
    page: '1',
    page_size: String(CUSTOMER_INVOICE_PAGE_SIZE),
  });
  const response = await apiFetch(
    `/customers/${numericId}/contifico/invoices?${params.toString()}`
  );
  const items = Array.isArray(response?.items) ? response.items : [];
  const cacheEntry = {
    customerId: numericId,
    documentId: typeof response?.document_id === 'string' ? response.document_id : '',
    page: typeof response?.page === 'number' ? response.page : 1,
    pageSize:
      typeof response?.page_size === 'number' ? response.page_size : CUSTOMER_INVOICE_PAGE_SIZE,
    items,
    fetchedAt: Date.now(),
  };
  state.customerInvoicesCache[cacheKey] = cacheEntry;
  return cacheEntry;
}

async function loadOrderInvoiceSuggestions(customer, options = {}) {
  const { force = false } = options;
  if (!orderInvoiceSuggestionsStatus) return;
  if (!customer || !customer.id || !customer.document_id) {
    clearOrderInvoiceSuggestions();
    return;
  }
  const numericId = Number(customer.id);
  if (!Number.isFinite(numericId) || numericId <= 0) {
    clearOrderInvoiceSuggestions();
    return;
  }
  state.orderInvoiceSuggestionsCustomerId = numericId;
  state.orderInvoiceSuggestionsLoading = true;
  state.orderInvoiceSuggestionsError = null;

  const cached = !force ? getCachedCustomerInvoices(numericId) : null;
  if (cached) {
    state.orderInvoiceSuggestions = cached.items || [];
    state.orderInvoiceSuggestionsLoading = false;
    renderOrderInvoiceSuggestions();
    return;
  }

  renderOrderInvoiceSuggestions();
  const requestId = Date.now();
  state.orderInvoiceSuggestionRequestId = requestId;
  try {
    const data = await fetchCustomerInvoicesData(numericId, { force });
    if (state.orderInvoiceSuggestionRequestId !== requestId) {
      return;
    }
    state.orderInvoiceSuggestions = Array.isArray(data?.items) ? data.items : [];
    state.orderInvoiceSuggestionsLoading = false;
    renderOrderInvoiceSuggestions();
  } catch (error) {
    if (state.orderInvoiceSuggestionRequestId !== requestId) {
      return;
    }
    state.orderInvoiceSuggestions = [];
    state.orderInvoiceSuggestionsLoading = false;
    state.orderInvoiceSuggestionsError = error?.message || 'No se pudo consultar Contífico.';
    renderOrderInvoiceSuggestions();
  }
}

async function handleOrderInvoiceLookup() {
  if (!orderInvoiceLookupButton) return;
  if (!state.token) {
    showToast('Inicia sesión para consultar Contífico.', 'error');
    return;
  }
  const selectedCustomerId = Number(orderCustomerSelect?.value);
  if (!Number.isFinite(selectedCustomerId) || selectedCustomerId <= 0) {
    showToast('Selecciona un cliente antes de consultar la factura.', 'error');
    return;
  }
  const invoiceNumber = newOrderInvoiceInput?.value?.trim() || '';
  if (!invoiceNumber) {
    showToast('Ingresa un número de factura para consultarlo.', 'error');
    newOrderInvoiceInput?.focus();
    return;
  }

  const customer =
    (state.customerOptions || []).find((item) => item.id === selectedCustomerId) ||
    (state.customers || []).find((item) => item.id === selectedCustomerId) ||
    null;
  const documentInput = document.getElementById('newCustomerDocument');
  const fallbackDocument = documentInput?.value?.trim() || '';
  const documentId = customer?.document_id?.trim?.() || fallbackDocument;
  if (!documentId) {
    showToast(
      'El cliente seleccionado no tiene un número de documento registrado.',
      'error'
    );
    return;
  }

  const requestId = Date.now();
  state.orderInvoiceLookupRequestId = requestId;
  state.orderInvoiceLookupLoading = true;
  state.orderInvoiceLookupError = null;
  state.orderInvoiceLookup = null;
  state.orderInvoiceLookupCustomerId = selectedCustomerId;
  state.orderInvoiceLookupNumber = invoiceNumber;
  renderOrderInvoiceLookupDetails();

  try {
    const params = new URLSearchParams({
      customer_document: documentId,
      document_number: invoiceNumber,
    });
    const response = await apiFetch(
      `/integrations/contifico/invoices/by-customer-and-number?${params.toString()}`
    );
    if (state.orderInvoiceLookupRequestId !== requestId) {
      return;
    }
    state.orderInvoiceLookupLoading = false;
    state.orderInvoiceLookupError = null;
    state.orderInvoiceLookup = response || null;
    const normalizedNumber =
      typeof response?.numero === 'string' && response.numero.trim()
        ? response.numero.trim()
        : invoiceNumber;
    state.orderInvoiceLookupNumber = normalizedNumber;
    if (newOrderInvoiceInput && normalizedNumber) {
      newOrderInvoiceInput.value = normalizedNumber;
    }

    const numericId = selectedCustomerId;
    const cacheKey = String(numericId);
    const cacheEntry = getCachedCustomerInvoices(numericId);
    const newInvoiceEntry = { invoice: response, linked_orders: [] };
    if (cacheEntry) {
      const items = Array.isArray(cacheEntry.items) ? cacheEntry.items : [];
      const existingIndex = items.findIndex(
        (entry) => (entry?.invoice?.numero || '').trim() === normalizedNumber
      );
      if (existingIndex >= 0) {
        items[existingIndex] = { ...items[existingIndex], invoice: response };
      } else {
        items.unshift(newInvoiceEntry);
      }
      cacheEntry.items = items;
      cacheEntry.documentId = cacheEntry.documentId || documentId;
      cacheEntry.fetchedAt = Date.now();
    } else {
      state.customerInvoicesCache[cacheKey] = {
        customerId: numericId,
        documentId,
        page: 1,
        pageSize: CUSTOMER_INVOICE_PAGE_SIZE,
        items: [newInvoiceEntry],
        fetchedAt: Date.now(),
      };
    }
    if (state.selectedCustomerId === numericId) {
      renderCustomerInvoices(numericId);
    }

    if (state.orderInvoiceSuggestionsCustomerId === numericId) {
      const suggestions = Array.isArray(state.orderInvoiceSuggestions)
        ? [...state.orderInvoiceSuggestions]
        : [];
      const existingSuggestionIndex = suggestions.findIndex((entry) => {
        const invoiceData = entry?.invoice || entry || {};
        return (invoiceData.numero || '').trim() === normalizedNumber;
      });
      if (existingSuggestionIndex >= 0) {
        suggestions[existingSuggestionIndex] = {
          ...suggestions[existingSuggestionIndex],
          invoice: response,
        };
      } else {
        suggestions.unshift(newInvoiceEntry);
      }
      state.orderInvoiceSuggestions = suggestions;
      state.orderInvoiceSuggestionsError = null;
      renderOrderInvoiceSuggestions();
    }

    renderOrderInvoiceLookupDetails();
    showToast('Factura confirmada en Contífico.', 'success');
  } catch (error) {
    if (state.orderInvoiceLookupRequestId !== requestId) {
      return;
    }
    state.orderInvoiceLookupLoading = false;
    state.orderInvoiceLookup = null;
    state.orderInvoiceLookupError =
      error?.message || 'No se pudo consultar la factura en Contífico.';
    renderOrderInvoiceLookupDetails();
    showToast(state.orderInvoiceLookupError, 'error');
  }
}

function setCustomerInvoicesStatus(message, { isError = false } = {}) {
  if (!customerInvoicesStatus) return;
  customerInvoicesStatus.textContent = message || '';
  customerInvoicesStatus.classList.toggle('status-error', Boolean(isError));
}

function clearCustomerInvoices() {
  if (customerInvoicesTableBody) {
    customerInvoicesTableBody.innerHTML = '';
  }
  setCustomerInvoicesStatus('Selecciona un cliente para consultar sus facturas en Contífico.');
}

function renderCustomerInvoices(customerId) {
  if (!customerInvoicesTableBody) return;
  const cacheEntry = getCachedCustomerInvoices(customerId);
  const invoices = Array.isArray(cacheEntry?.items) ? cacheEntry.items : [];
  customerInvoicesTableBody.innerHTML = '';
  if (!invoices.length) {
    setCustomerInvoicesStatus('No se encontraron facturas registradas para el cliente.');
    return;
  }
  const summaryMessage =
    invoices.length === 1
      ? 'Se encontró 1 factura para el cliente.'
      : `Se encontraron ${invoices.length} facturas para el cliente.`;
  setCustomerInvoicesStatus(summaryMessage);

  invoices.forEach((entry) => {
    const invoiceData = entry?.invoice || {};
    const row = document.createElement('tr');

    const numberCell = document.createElement('td');
    numberCell.textContent = invoiceData?.numero || '—';
    row.appendChild(numberCell);

    const dateCell = document.createElement('td');
    dateCell.textContent = invoiceData?.fecha_emision ? formatDate(invoiceData.fecha_emision) : '—';
    row.appendChild(dateCell);

    const statusCell = document.createElement('td');
    statusCell.textContent = invoiceData?.estado || '—';
    row.appendChild(statusCell);

    const totalCell = document.createElement('td');
    totalCell.textContent =
      typeof invoiceData?.total === 'number' && Number.isFinite(invoiceData.total)
        ? formatCurrencyUSD(invoiceData.total)
        : '—';
    row.appendChild(totalCell);

    const ordersCell = document.createElement('td');
    const linkedOrders = Array.isArray(entry?.linked_orders) ? entry.linked_orders : [];
    if (!linkedOrders.length) {
      const emptyLabel = document.createElement('span');
      emptyLabel.className = 'muted';
      emptyLabel.textContent = 'Sin órdenes vinculadas';
      ordersCell.appendChild(emptyLabel);
    } else {
      const container = document.createElement('div');
      container.className = 'invoice-orders';
      linkedOrders.forEach((linkedOrder) => {
        const pill = document.createElement('span');
        pill.className = 'invoice-order-pill';
        const orderNumber = linkedOrder?.order_number || `Orden #${linkedOrder?.order_id || ''}`;
        const statusLabel = linkedOrder?.status || '';
        const parts = [orderNumber];
        if (statusLabel) {
          parts.push(statusLabel);
        }
        pill.textContent = parts.join(' • ');
        container.appendChild(pill);
      });
      ordersCell.appendChild(container);
    }
    row.appendChild(ordersCell);

    customerInvoicesTableBody.appendChild(row);
  });
}

async function loadCustomerInvoicesForDetail(customer, options = {}) {
  const { force = false } = options;
  if (!customer) {
    clearCustomerInvoices();
    return;
  }
  const numericId = Number(customer.id);
  if (!Number.isFinite(numericId) || numericId <= 0) {
    clearCustomerInvoices();
    return;
  }
  const cached = !force ? getCachedCustomerInvoices(numericId) : null;
  if (cached && !force) {
    renderCustomerInvoices(numericId);
    return;
  }

  setCustomerInvoicesStatus('Consultando facturas del cliente...');
  const requestId = Date.now();
  state.customerInvoicesRequestId = requestId;
  try {
    const data = await fetchCustomerInvoicesData(numericId, { force });
    if (state.customerInvoicesRequestId !== requestId) {
      return;
    }
    renderCustomerInvoices(numericId);
    if (state.orderInvoiceSuggestionsCustomerId === numericId) {
      state.orderInvoiceSuggestions = Array.isArray(data?.items) ? data.items : [];
      state.orderInvoiceSuggestionsLoading = false;
      state.orderInvoiceSuggestionsError = null;
      renderOrderInvoiceSuggestions();
    }
  } catch (error) {
    if (state.customerInvoicesRequestId !== requestId) {
      return;
    }
    customerInvoicesTableBody.innerHTML = '';
    const message = error?.message || 'No se pudieron obtener las facturas del cliente.';
    setCustomerInvoicesStatus(message, { isError: true });
    if (state.orderInvoiceSuggestionsCustomerId === numericId) {
      state.orderInvoiceSuggestions = [];
      state.orderInvoiceSuggestionsLoading = false;
      state.orderInvoiceSuggestionsError = message;
      renderOrderInvoiceSuggestions();
    }
  } finally {
    if (state.customerInvoicesRequestId === requestId) {
      state.customerInvoicesRequestId = 0;
    }
  }
}

async function loadUsers() {
  if (!state.token || state.user?.role !== 'administrador') {
    return;
  }
  state.usersLoadError = null;
  state.usersLoaded = false;
  renderUsers();
  try {
    state.users = await apiFetch('/users');
    state.usersLoaded = true;
    state.usersLoadError = null;
  } catch (error) {
    state.users = [];
    state.usersLoaded = false;
    state.usersLoadError = error.message || 'No se pudieron cargar los usuarios.';
    showToast(error.message, 'error');
  }
  renderUsers();
}

async function loadCurrentUser() {
  state.user = await apiFetch('/users/me');
}

function handleLogout(auto = false) {
  clearStoredToken();
  state.token = null;
  state.user = null;
  state.orders = [];
  state.tailors = [];
  state.vendors = [];
  state.customers = [];
  state.customerOptions = [];
  state.customerOrdersCache = {};
  state.customerDisplayCache = {};
  state.customerInvoicesCache = {};
  state.customerInvoicesRequestId = 0;
  state.customerSearchTerm = '';
  state.orderSearchTerm = '';
  state.customerPage = 1;
  state.customerPageSize = DEFAULT_PAGE_SIZE;
  state.orderPage = 1;
  state.orderPageSize = DEFAULT_PAGE_SIZE;
  state.customerTotal = 0;
  state.orderTotal = 0;
  state.kanbanOrders = [];
  state.kanbanLoading = false;
  state.kanbanError = null;
  state.kanbanSearchTerm = '';
  state.kanbanNeedsRefresh = true;
  state.kanbanLastUpdated = null;
  state.isCreateCustomerVisible = false;
  state.isCustomerDetailVisible = false;
  state.isCreateUserVisible = false;
  state.auditLogs = [];
  state.selectedCustomerId = null;
  state.selectedOrderId = null;
  state.orderTasks = [];
  state.orderTasksOrderId = null;
  state.orderTasksLoading = false;
  state.orderTasksRequestId = 0;
  state.customerRequestId = 0;
  state.orderRequestId = 0;
  state.customerOptionsRequestId = 0;
  state.orderInvoiceSuggestions = [];
  state.orderInvoiceSuggestionsCustomerId = null;
  state.orderInvoiceSuggestionRequestId = 0;
  state.orderInvoiceSuggestionsLoading = false;
  state.orderInvoiceSuggestionsError = null;
  state.orderInvoiceLookup = null;
  state.orderInvoiceLookupLoading = false;
  state.orderInvoiceLookupError = null;
  state.orderInvoiceLookupCustomerId = null;
  state.orderInvoiceLookupNumber = '';
  state.orderInvoiceLookupRequestId = 0;
  state.users = [];
  state.usersLoaded = false;
  state.usersLoadError = null;
  state.editingUserId = null;
  resetContificoPreviewState();
  setCustomerInvoicesStatus('');
  if (customerInvoicesTableBody) {
    customerInvoicesTableBody.innerHTML = '';
  }
  setOrderInvoiceSuggestionsStatus('');
  renderOrderInvoiceSuggestions();
  renderOrderInvoiceLookupDetails();
  if (currentUserNameElement) {
    currentUserNameElement.textContent = '';
  }
  if (currentUserRoleElement) {
    currentUserRoleElement.textContent = '';
  }
  if (assignTailorSelect) {
    populateTailorSelect(assignTailorSelect);
  }
  if (assignVendorSelect) {
    populateVendorSelect(assignVendorSelect);
  }
  if (orderTaskDescriptionInput) {
    orderTaskDescriptionInput.value = '';

  }
  if (orderCustomerSelect) {
    populateCustomerSelect(orderCustomerSelect);
  }
  if (auditLogTabButton) {
    auditLogTabButton.classList.add('hidden');
  }
  if (usersTabButton) {
    usersTabButton.classList.add('hidden');
  }
  if (contificoPreviewTabButton) {
    contificoPreviewTabButton.classList.add('hidden');
  }
  setActiveDashboardTab('ordersPanel');
  hideDashboard();
  if (customerSearchInput) {
    customerSearchInput.value = '';
  }
  if (orderSearchInput) {
    orderSearchInput.value = '';
  }
  if (orderKanbanSearchInput) {
    orderKanbanSearchInput.value = '';
  }
  if (customerPageSizeSelect) {
    customerPageSizeSelect.value = String(DEFAULT_PAGE_SIZE);
  }
  if (orderPageSizeSelect) {
    orderPageSizeSelect.value = String(DEFAULT_PAGE_SIZE);
  }
  setCreateCustomerVisible(false);
  if (ordersTableBody) {
    ordersTableBody.innerHTML = '';
  }
  if (orderKanbanColumns) {
    orderKanbanColumns.innerHTML = '';
  }
  if (orderKanbanStatus) {
    orderKanbanStatus.textContent = '';
    orderKanbanStatus.classList.add('hidden');
  }
  if (orderDetailVendorSelect) {
    populateVendorSelect(orderDetailVendorSelect);
  }
  if (customersTableBody) {
    customersTableBody.innerHTML = '';
  }
  if (auditLogTableBody) {
    auditLogTableBody.innerHTML = '';
  }
  if (usersTableBody) {
    usersTableBody.innerHTML = '';
  }
  clearCustomerDetail();
  clearOrderDetail({ skipRender: true });
  resetCreateCustomerForm();
  resetCreateUserForm();
  clearUserEditForm();
  updateUserCreationForm();
  renderUsers();

  measurementsList.innerHTML = '';
  ensureMeasurementRow();
  renderCustomerMeasurementOptions(null);
  clearOrderResult();
  updatePaginationControls({
    infoElement: customerPaginationInfo,
    prevButton: customerPrevPageButton,
    nextButton: customerNextPageButton,
    pageSizeSelect: customerPageSizeSelect,
    currentPage: 1,
    totalItems: 0,
    pageSize: state.customerPageSize,
    emptyLabel: 'clientes',
  });
  updatePaginationControls({
    infoElement: orderPaginationInfo,
    prevButton: orderPrevPageButton,
    nextButton: orderNextPageButton,
    pageSizeSelect: orderPageSizeSelect,
    currentPage: 1,
    totalItems: 0,
    pageSize: state.orderPageSize,
    emptyLabel: 'órdenes',
  });
  updateNavigationForAuth();
  setActiveView('staff-view');
  renderUsers();
  renderOrderTasks();
  renderOrderKanban();
  if (auto) {
    showToast('La sesión ha expirado, vuelve a iniciar sesión.', 'error');
  }
}

if (staffLoginForm) {
  staffLoginForm.addEventListener('submit', handleLogin);
}

if (logoutButton) {
  logoutButton.addEventListener('click', () => {
    handleLogout(false);
    showToast('Sesión cerrada correctamente.', 'success');
  });
}

if (contificoPreviewProductsForm) {
  contificoPreviewProductsForm.addEventListener('submit', handleContificoPreviewProductsFetch);
}

if (contificoPreviewWarehousesButton) {
  contificoPreviewWarehousesButton.addEventListener('click', handleContificoPreviewWarehousesFetch);
}

if (contificoCustomerInvoicesForm) {
  contificoCustomerInvoicesForm.addEventListener('submit', handleContificoCustomerInvoicesFetch);
}

if (contificoCustomerInvoiceLookupForm) {
  contificoCustomerInvoiceLookupForm.addEventListener(
    'submit',
    handleContificoCustomerInvoiceLookup
  );
}

if (contificoInvoiceLookupForm) {
  contificoInvoiceLookupForm.addEventListener('submit', handleContificoInvoiceLookup);
}

function getOrdersForCustomer(customerId) {
  if (customerId === null || customerId === undefined) {
    return [];
  }
  const numericId = Number(customerId);
  if (!Number.isFinite(numericId)) {
    return [];
  }
  const key = String(numericId);
  const cached = state.customerOrdersCache?.[key];
  if (cached?.items) {
    return cached.items;
  }
  return state.orders.filter((order) => Number(order.customer_id) === numericId);
}

function sortOrdersByRecency(orders) {
  return [...orders].sort((a, b) => {
    const aTimestamp = toTimestamp(a?.updated_at) ?? toTimestamp(a?.created_at) ?? 0;
    const bTimestamp = toTimestamp(b?.updated_at) ?? toTimestamp(b?.created_at) ?? 0;
    if (aTimestamp !== bTimestamp) {
      return bTimestamp - aTimestamp;
    }
    const aId = typeof a?.id === 'number' ? a.id : Number(a?.id) || 0;
    const bId = typeof b?.id === 'number' ? b.id : Number(b?.id) || 0;
    return bId - aId;
  });
}

function getCustomerDisplayData(customer, ordersForCustomer = []) {
  const normalizedName =
    typeof customer?.full_name === 'string' ? customer.full_name.trim() : '';
  const normalizedDocument =
    typeof customer?.document_id === 'string' ? customer.document_id.trim() : '';
  const normalizedContact =
    typeof customer?.phone === 'string' ? customer.phone.trim() : '';
  const normalizedEmail =
    typeof customer?.email === 'string' ? customer.email.trim() : '';
  const normalizedAddress =
    typeof customer?.address === 'string' ? customer.address.trim() : '';

  const cacheKey =
    customer?.id !== null && customer?.id !== undefined ? String(customer.id) : null;
  const cachedDisplay =
    cacheKey && state.customerDisplayCache ? state.customerDisplayCache[cacheKey] || {} : {};

  let fallbackName = '';
  let fallbackDocument = '';
  let fallbackContact = '';

  if (!normalizedName || !normalizedDocument || !normalizedContact) {
    const orderList = Array.isArray(ordersForCustomer) ? ordersForCustomer : [];
    const ordersByRecency = sortOrdersByRecency(orderList);
    for (const order of ordersByRecency) {
      if (!fallbackName && typeof order?.customer_name === 'string') {
        const trimmed = order.customer_name.trim();
        if (trimmed) {
          fallbackName = trimmed;
        }
      }
      if (!fallbackDocument && typeof order?.customer_document === 'string') {
        const trimmed = order.customer_document.trim();
        if (trimmed) {
          fallbackDocument = trimmed;
        }
      }
      if (!fallbackContact && typeof order?.customer_contact === 'string') {
        const trimmed = order.customer_contact.trim();
        if (trimmed) {
          fallbackContact = trimmed;
        }
      }
      if (fallbackName && fallbackDocument && fallbackContact) {
        break;
      }
    }
  }

  const name = normalizedName || fallbackName || cachedDisplay.name || '';
  const document = normalizedDocument || fallbackDocument || cachedDisplay.document || '';
  const contact = normalizedContact || fallbackContact || cachedDisplay.contact || '';
  const email = normalizedEmail || cachedDisplay.email || '';
  const address = normalizedAddress || cachedDisplay.address || '';

  if (cacheKey) {
    if (!state.customerDisplayCache) {
      state.customerDisplayCache = {};
    }
    state.customerDisplayCache[cacheKey] = {
      name,
      document,
      contact,
      email,
      address,
    };
  }

  return {
    name,
    document,
    contact,
    email,
    address,
  };
}


function showCustomerOrderHistoryLoading() {
  if (!customerOrderHistoryContainer) return;
  customerOrderHistoryContainer.classList.add('muted');
  customerOrderHistoryContainer.textContent = 'Cargando historial de órdenes...';
}


function renderCustomerOrderHistory(customer) {
  if (!customerOrderHistoryContainer) return;
  if (!customer) {
    customerOrderHistoryContainer.classList.add('muted');
    customerOrderHistoryContainer.textContent = CUSTOMER_ORDER_HISTORY_PROMPT;
    return;
  }

  const ordersForCustomer = sortOrdersByRecency(getOrdersForCustomer(customer.id));
  if (!ordersForCustomer.length) {
    customerOrderHistoryContainer.classList.add('muted');
    customerOrderHistoryContainer.textContent = CUSTOMER_ORDER_HISTORY_EMPTY_MESSAGE;
    return;
  }

  customerOrderHistoryContainer.classList.remove('muted');
  customerOrderHistoryContainer.innerHTML = '';

  const list = document.createElement('ul');
  list.className = 'customer-order-history-items';

  ordersForCustomer.forEach((order) => {
    const item = document.createElement('li');
    item.className = 'customer-order-history-item';

    const header = document.createElement('div');
    header.className = 'customer-order-history-item-header';

    const orderNumber = document.createElement('strong');
    orderNumber.textContent = order.order_number;

    const statusWrapper = document.createElement('div');
    statusWrapper.appendChild(createStatusBadge(order.status));

    const actions = document.createElement('div');
    actions.className = 'customer-order-history-item-actions';
    actions.appendChild(statusWrapper);

    if (state.token) {
      const openButton = document.createElement('button');
      openButton.type = 'button';
      openButton.className = 'link-button customer-order-history-open';
      openButton.textContent = 'Ver orden';
      openButton.addEventListener('click', () => {
        openOrderDetailFromCustomerHistory(order);
      });
      actions.appendChild(openButton);
    }

    header.appendChild(orderNumber);
    header.appendChild(actions);

    const invoice = document.createElement('p');
    invoice.className = 'customer-order-history-item-invoice';
    invoice.textContent = order.invoice_number
      ? `Factura: ${order.invoice_number}`
      : 'Factura: Sin número registrado';

    const meta = document.createElement('p');
    meta.className = 'customer-order-history-item-meta';
    const parts = [];
    if (order.origin_branch) {
      parts.push(`Establecimiento: ${order.origin_branch}`);
    }

    const deliveryLabel = formatDeliveryDateDisplay(order);
    if (deliveryLabel) {
      parts.push(`Entrega: ${deliveryLabel}`);
    }
    if (order.updated_at) {
      parts.push(`Actualizado: ${formatDate(order.updated_at)}`);
    }
    meta.textContent = parts.length ? parts.join(' • ') : 'Sin información adicional disponible.';

    item.appendChild(header);
    item.appendChild(invoice);

    item.appendChild(meta);
    list.appendChild(item);
  });

  customerOrderHistoryContainer.appendChild(list);
}

async function openOrderDetailFromCustomerHistory(order) {
  if (!state.token) {
    showToast('Inicia sesión para gestionar las órdenes.', 'error');
    return;
  }
  if (!order || order.id === undefined || order.id === null) {
    showToast('No se pudo abrir el detalle de la orden seleccionada.', 'error');
    return;
  }

  const orderIdKey = String(order.id);
  setActiveDashboardTab('ordersPanel');
  if (state.activeOrdersView !== 'list') {
    setActiveOrdersView('list');
  }

  let detail = state.orders.find((item) => String(item.id) === orderIdKey);
  if (!detail) {
    try {
      detail = await apiFetch(`/orders/${encodeURIComponent(orderIdKey)}`);
    } catch (error) {
      /* ignore fetch failure and fall back to cached data */
    }
  }

  if (!detail) {
    detail = order;
  }

  if (!detail || detail.id === undefined || detail.id === null) {
    showToast('No se pudo abrir el detalle de la orden seleccionada.', 'error');
    return;
  }

  const remainingOrders = state.orders.filter((item) => String(item.id) !== orderIdKey);
  state.orders = [...remainingOrders, detail];
  if (typeof state.orderTotal !== 'number' || state.orderTotal < state.orders.length) {
    state.orderTotal = state.orders.length;
  }

  populateOrderDetail(detail, { focusOnDetail: false });
  attachOrderDetailToOverlay();
}
function renderCustomers() {
  if (!customersTableBody) return;

  const pageSize = getValidPageSize(state.customerPageSize);
  if (state.customerPageSize !== pageSize) {
    state.customerPageSize = pageSize;
  }

  customersTableBody.innerHTML = '';

  if (customerSearchInput && customerSearchInput.value !== state.customerSearchTerm) {
    customerSearchInput.value = state.customerSearchTerm;
  }

  const totalItems =
    typeof state.customerTotal === 'number'
      ? state.customerTotal
      : state.customers.length;

  const normalizedPage =
    updatePaginationControls({
      infoElement: customerPaginationInfo,
      prevButton: customerPrevPageButton,
      nextButton: customerNextPageButton,
      pageSizeSelect: customerPageSizeSelect,
      currentPage: state.customerPage || 1,
      totalItems,
      pageSize,
      emptyLabel: 'clientes',
    }) || (state.customerPage || 1);

  if (state.customerPage !== normalizedPage) {
    state.customerPage = normalizedPage;
  }

  if (!state.customers.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = CUSTOMER_TABLE_COLUMN_COUNT;
    const hasSearch = Boolean(state.customerSearchTerm.trim());
    if (totalItems === 0) {
      cell.textContent = hasSearch
        ? 'No se encontraron clientes que coincidan con la búsqueda.'
        : 'No hay clientes registrados aún.';
      if (state.isCustomerDetailVisible) {
        clearCustomerDetail({ skipFocus: true });
      }
    } else {
      cell.textContent = 'No hay clientes para la página seleccionada.';
    }
    cell.className = 'muted';
    row.appendChild(cell);
    customersTableBody.appendChild(row);
    return;
  }

  state.customers.forEach((customer) => {
    const row = document.createElement('tr');
    row.classList.add('customer-row');
    row.dataset.customerId = String(customer.id);

    const isSelected = state.selectedCustomerId === customer.id && state.isCustomerDetailVisible;
    if (isSelected) {
      row.classList.add('is-selected');
    }

    const cachedOrders = getOrdersForCustomer(customer.id);
    const orderCount =
      typeof customer.order_count === 'number'
        ? customer.order_count
        : cachedOrders.length;
    const displayData = getCustomerDisplayData(customer, cachedOrders);

    const nameCell = document.createElement('td');
    nameCell.dataset.label = 'Nombre';
    nameCell.textContent = displayData.name || '—';

    const documentCell = document.createElement('td');
    documentCell.dataset.label = 'Documento';
    documentCell.textContent = displayData.document || '—';

    const phoneCell = document.createElement('td');
    phoneCell.dataset.label = 'Teléfono';
    phoneCell.textContent = displayData.contact || '—';

    const orderCountCell = document.createElement('td');
    orderCountCell.className = 'customer-order-count-cell';
    orderCountCell.dataset.label = 'Órdenes';
    if (orderCount > 0) {
      const badge = document.createElement('span');
      badge.className = 'customer-order-count-badge';
      badge.textContent = orderCount;
      const label =
        orderCount === 1 ? '1 orden registrada' : `${orderCount} órdenes registradas`;
      badge.title = label;
      badge.setAttribute('aria-label', label);
      orderCountCell.appendChild(badge);
    } else {
      orderCountCell.innerHTML = '<span class="muted">0</span>';
    }

    const actionsCell = document.createElement('td');
    actionsCell.dataset.label = 'Acciones';
    const viewButton = document.createElement('button');
    viewButton.type = 'button';
    viewButton.className = 'secondary';
    viewButton.dataset.action = 'toggle-customer-detail';
    viewButton.dataset.customerId = String(customer.id);
    viewButton.setAttribute('aria-controls', 'customerDetail');
    viewButton.textContent = isSelected ? 'Cerrar detalle' : 'Ver detalle';
    viewButton.setAttribute('aria-expanded', isSelected ? 'true' : 'false');
    viewButton.addEventListener('click', async () => {
      lastCustomerDetailTrigger = viewButton;
      if (state.selectedCustomerId === customer.id && state.isCustomerDetailVisible) {
        clearCustomerDetail({ reRender: true });
      } else {
        await populateCustomerDetail(customer);
      }
    });
    actionsCell.appendChild(viewButton);

    row.appendChild(nameCell);
    row.appendChild(documentCell);
    row.appendChild(phoneCell);
    row.appendChild(orderCountCell);
    row.appendChild(actionsCell);

    customersTableBody.appendChild(row);
  });
}

async function populateCustomerDetail(customer) {
  if (!customerDetail) return;
  state.selectedCustomerId = customer.id;

  setContificoLookupStatus(updateContificoCustomerLookupStatus, '');
  if (updateCustomerFetchContificoButton) {
    updateCustomerFetchContificoButton.disabled = false;
  }

  const cacheKey = String(customer.id);
  const expectedOrderCount =
    typeof customer.order_count === 'number' ? customer.order_count : undefined;
  const cached = state.customerOrdersCache[cacheKey];
  const cachedItems = Array.isArray(cached?.items) ? cached.items : [];
  const cacheComplete = cached?.complete === true;
  const hasCache = Boolean(cached);
  const needsFetch =
    expectedOrderCount !== undefined
      ? !cacheComplete || cachedItems.length < expectedOrderCount
      : !hasCache || !cacheComplete;

  if (needsFetch) {
    showCustomerOrderHistoryLoading();
    await fetchOrdersForCustomer(customer.id);
  }

  const ordersForCustomer = getOrdersForCustomer(customer.id);
  const displayData = getCustomerDisplayData(customer, ordersForCustomer);

  if (customerDetailTitle) {
    customerDetailTitle.textContent = displayData.name || CUSTOMER_DETAIL_DEFAULT_TITLE;
  }

  if (customerDetailSummaryElement) {
    const summaryParts = [];
    if (displayData.document) {
      summaryParts.push(`Documento: ${displayData.document}`);
    }
    if (displayData.contact) {
      summaryParts.push(`Teléfono: ${displayData.contact}`);
    }
    if (displayData.email) {
      summaryParts.push(`Correo: ${displayData.email}`);
    }
    if (displayData.address) {
      summaryParts.push(`Dirección: ${displayData.address}`);
    }
    const orderCountForSummary =
      typeof expectedOrderCount === 'number' ? expectedOrderCount : ordersForCustomer.length;
    if (orderCountForSummary > 0) {
      const label =
        orderCountForSummary === 1
          ? '1 orden registrada'
          : `${orderCountForSummary} órdenes registradas`;
      summaryParts.push(label);
    }
    customerDetailSummaryElement.textContent =
      summaryParts.length ? summaryParts.join(' • ') : 'Sin datos de contacto registrados.';
  }

  const nameInput = updateCustomerNameInput || customerDetail?.querySelector('#updateCustomerName');
  const documentInput =
    updateCustomerDocumentInput || customerDetail?.querySelector('#updateCustomerDocument');
  const phoneInput = updateCustomerPhoneInput || customerDetail?.querySelector('#updateCustomerPhone');
  const emailInput = updateCustomerEmailInput || customerDetail?.querySelector('#updateCustomerEmail');
  const addressInput =
    updateCustomerAddressInput || customerDetail?.querySelector('#updateCustomerAddress');

  const normalizedCustomerName =
    typeof customer?.full_name === 'string' ? customer.full_name.trim() : '';
  const normalizedCustomerDocument =
    typeof customer?.document_id === 'string' ? customer.document_id.trim() : '';
  const normalizedCustomerPhone =
    typeof customer?.phone === 'string' ? customer.phone.trim() : '';
  const normalizedCustomerEmail =
    typeof customer?.email === 'string' ? customer.email.trim() : '';
  const normalizedCustomerAddress =
    typeof customer?.address === 'string' ? customer.address.trim() : '';
  if (nameInput) {
    nameInput.value = normalizedCustomerName || displayData.name || '';
  }
  if (documentInput) {
    documentInput.value = normalizedCustomerDocument || displayData.document || '';
  }
  if (phoneInput) {
    phoneInput.value = normalizedCustomerPhone || displayData.contact || '';
  }
  if (emailInput) {
    emailInput.value = normalizedCustomerEmail || displayData.email || '';
  }
  if (addressInput) {
    addressInput.value = normalizedCustomerAddress || displayData.address || '';
  }

  if (updateCustomerMeasurementsContainer) {
    updateCustomerMeasurementsContainer.innerHTML = '';
    if (customer.measurements?.length) {
      customer.measurements.forEach((set) => {
        createMeasurementSetBlock(updateCustomerMeasurementsContainer, set);
      });
    } else {
      createMeasurementSetBlock(updateCustomerMeasurementsContainer);
    }
  }

  renderCustomerOrderHistory(customer);
  await loadCustomerInvoicesForDetail(customer);
  setCustomerDetailVisible(true);
  renderCustomers();
}

function clearCustomerDetail(options = {}) {
  if (!customerDetail) return;
  const { reRender = false, skipFocus = false } = options;
  state.selectedCustomerId = null;
  setCustomerDetailVisible(false);

  if (customerDetailTitle) {
    customerDetailTitle.textContent = CUSTOMER_DETAIL_DEFAULT_TITLE;
  }
  if (customerDetailSummaryElement) {
    customerDetailSummaryElement.textContent = CUSTOMER_DETAIL_DEFAULT_SUMMARY;
  }
  renderCustomerOrderHistory(null);
  clearCustomerInvoices();

  updateCustomerForm?.reset();
  if (updateCustomerMeasurementsContainer) {
    updateCustomerMeasurementsContainer.innerHTML = '';
  }
  setContificoLookupStatus(updateContificoCustomerLookupStatus, '');
  if (updateCustomerFetchContificoButton) {
    updateCustomerFetchContificoButton.disabled = false;
  }

  if (reRender) {
    renderCustomers();
  }

  if (!skipFocus && lastCustomerDetailTrigger?.isConnected) {
    lastCustomerDetailTrigger.focus();
  }
  lastCustomerDetailTrigger = null;
}

if (closeCustomerDetailButton) {
  closeCustomerDetailButton.addEventListener('click', () => {
    clearCustomerDetail({ reRender: true });
  });
}

document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || event.defaultPrevented) {
    return;
  }
  const detailOpen = customerDetailOverlay && !customerDetailOverlay.classList.contains('hidden');
  if (detailOpen) {
    event.preventDefault();
    clearCustomerDetail({ reRender: true });
    return;
  }
  const createOpen = customerCreateOverlay && !customerCreateOverlay.classList.contains('hidden');
  if (createOpen) {
    event.preventDefault();
    setCreateCustomerVisible(false);
  }
});

function populateOrderDetail(order, options = {}) {
  if (!orderDetail || !order) return;
  const { skipRender = false, focusOnDetail = true } = options;

  state.selectedOrderId = order.id;
  state.orderTasksOrderId = order.id;
  state.orderTasksLoading = true;
  state.orderTasks = [];
  renderOrderTasks();
  if (orderDetailNumberElement) {
    orderDetailNumberElement.textContent = order.order_number;
  }
  if (orderDetailCreatedAtElement) {
    orderDetailCreatedAtElement.textContent = formatDate(order.created_at);
  }
  if (orderDetailUpdatedAtElement) {
    orderDetailUpdatedAtElement.textContent = formatDate(order.updated_at);
  }
  if (orderDetailCustomerInput) {
    orderDetailCustomerInput.value = order.customer_name || '';
  }
  if (orderDetailDocumentInput) {
    orderDetailDocumentInput.value = order.customer_document || '';
  }
  if (orderDetailContactInput) {
    orderDetailContactInput.value = order.customer_contact || '';
  }
  if (orderDetailStatusSelect) {
    populateStatusSelect(orderDetailStatusSelect, order.status);
  }
  if (orderDetailTailorSelect) {
    populateTailorSelect(orderDetailTailorSelect, order.assigned_tailor?.id ?? '');
  }
  if (orderDetailVendorSelect) {
    populateVendorSelect(
      orderDetailVendorSelect,
      order.assigned_vendor?.id ?? '',
      order.assigned_vendor?.full_name || '',
    );
  }
  if (orderDetailInvoiceInput) {
    orderDetailInvoiceInput.value = order.invoice_number || '';
  }
  if (orderDetailOriginSelect) {
    populateEstablishmentSelect(orderDetailOriginSelect, order.origin_branch || '');
  }
  if (orderDetailDeliveryDateInput) {
    orderDetailDeliveryDateInput.value = toInputDateTimeValue(order.delivery_date);
  }
  if (orderDetailNotesTextarea) {
    orderDetailNotesTextarea.value = order.notes || '';
  }
  if (orderDetailMeasurementsContainer) {
    orderDetailMeasurementsContainer.innerHTML = '';
    if (order.measurements?.length) {
      orderDetailMeasurementsContainer.classList.remove('muted');
      order.measurements.forEach((item) => {
        const tag = document.createElement('span');
        tag.className = 'tag';
        tag.textContent = `${item.nombre}: ${item.valor}`;
        orderDetailMeasurementsContainer.appendChild(tag);
      });
    } else {
      orderDetailMeasurementsContainer.classList.add('muted');
      orderDetailMeasurementsContainer.textContent = 'Sin medidas registradas.';
    }
  }

  if (order.customer_id) {
    const targetId = Number(order.customer_id);
    const candidate =
      state.customerOptions.find((item) => item.id === targetId) ||
      state.customers.find((item) => item.id === targetId) ||
      (order.customer_document
        ? { id: targetId, document_id: order.customer_document }
        : null);
    if (candidate) {
      void loadOrderInvoiceSuggestions(candidate);
    }
  }

  if (!skipRender) {
    renderOrders();
    if (focusOnDetail) {
      requestAnimationFrame(() => {
        if (orderDetail?.isConnected) {
          orderDetail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
      });
    }
  }

  refreshOrderTasks(order.id);
  updateOrderDetailOverlayVisibility();
}

function clearOrderDetail(options = {}) {
  if (!orderDetail) return;
  const wasOverlayHost = currentOrderDetailHost === 'overlay';
  const defaultSkipRender = wasOverlayHost && state.activeOrdersView === 'kanban';
  const skipRenderOption =
    typeof options.skipRender === 'boolean' ? options.skipRender : defaultSkipRender;
  const focusOrderId = lastKanbanFocusedOrderId;
  const focusElement = lastKanbanFocusedElement;

  state.selectedOrderId = null;
  updateOrderForm?.reset();
  if (orderDetailNumberElement) orderDetailNumberElement.textContent = '';
  if (orderDetailCreatedAtElement) orderDetailCreatedAtElement.textContent = '';
  if (orderDetailUpdatedAtElement) orderDetailUpdatedAtElement.textContent = '';
  if (orderDetailCustomerInput) orderDetailCustomerInput.value = '';
  if (orderDetailDocumentInput) orderDetailDocumentInput.value = '';
  if (orderDetailContactInput) orderDetailContactInput.value = '';
  if (orderDetailStatusSelect) populateStatusSelect(orderDetailStatusSelect);
  if (orderDetailTailorSelect) populateTailorSelect(orderDetailTailorSelect);
  if (orderDetailVendorSelect) populateVendorSelect(orderDetailVendorSelect);
  if (orderDetailInvoiceInput) orderDetailInvoiceInput.value = '';
  if (orderDetailOriginSelect) populateEstablishmentSelect(orderDetailOriginSelect);
  if (orderDetailDeliveryDateInput) orderDetailDeliveryDateInput.value = '';
  if (orderDetailNotesTextarea) orderDetailNotesTextarea.value = '';
  if (orderDetailMeasurementsContainer) {
    orderDetailMeasurementsContainer.innerHTML = '';
    orderDetailMeasurementsContainer.classList.add('muted');
  }

  resetOrderTasksState();

  removeOrderDetailRow();
  orderDetail.classList.add('hidden');

  if (wasOverlayHost) {
    currentOrderDetailHost = null;
  }
  updateOrderDetailOverlayVisibility();

  if (!skipRenderOption) {
    renderOrders();
  }
  renderOrderKanban();

  if (wasOverlayHost) {
    requestAnimationFrame(() => {
      let focusTarget = null;
      if (focusOrderId && orderKanbanColumns) {
        focusTarget = orderKanbanColumns.querySelector(`[data-order-id="${focusOrderId}"]`);
      }
      if (!(focusTarget instanceof HTMLElement) && focusElement instanceof HTMLElement) {
        focusTarget = focusElement.isConnected ? focusElement : null;
      }
      if (!(focusTarget instanceof HTMLElement)) {
        focusTarget = Array.from(ordersViewToggleButtons).find(
          (btn) => btn instanceof HTMLElement && btn.dataset.ordersView === 'kanban',
        );
      }
      if (focusTarget instanceof HTMLElement) {
        focusTarget.focus();
      }
    });
  }

  lastKanbanFocusedElement = null;
  lastKanbanFocusedOrderId = null;
}

async function handleOrderUpdate(event) {
  event.preventDefault();
  if (state.selectedOrderId === null) {
    showToast('Selecciona una orden para actualizar.', 'error');
    return;
  }
  const submitButton = updateOrderForm?.querySelector('button[type="submit"]');
  const originBranchValue = orderDetailOriginSelect?.value || '';
  const invoiceValueRaw = orderDetailInvoiceInput?.value.trim() || '';
  if (!originBranchValue) {
    showToast('Selecciona el establecimiento remitente.', 'error');
    return;
  }
  if (submitButton) {
    submitButton.disabled = true;
  }
  const currentOrder = state.orders.find((order) => order.id === state.selectedOrderId);
  const affectedCustomerId = currentOrder?.customer_id;
  const deliveryDateValueRaw = orderDetailDeliveryDateInput?.value || '';
  const deliveryDateValue = normalizeDateForApi(deliveryDateValueRaw);
  const invoiceValue = invoiceValueRaw || null;
  let orderUpdatedSuccessfully = false;
  try {
    await apiFetch(`/orders/${state.selectedOrderId}`, {
      method: 'PATCH',
      body: {
        status: orderDetailStatusSelect?.value,
        assigned_tailor_id: orderDetailTailorSelect?.value
          ? Number(orderDetailTailorSelect.value)
          : null,
        assigned_vendor_id: orderDetailVendorSelect?.value
          ? Number(orderDetailVendorSelect.value)
          : null,
        customer_contact: orderDetailContactInput?.value.trim() || null,
        notes: orderDetailNotesTextarea?.value.trim() || null,
        delivery_date: deliveryDateValue ? deliveryDateValue : null,
        invoice_number: invoiceValue,
        origin_branch: originBranchValue,
      },
    });
    orderUpdatedSuccessfully = true;
    if (affectedCustomerId) {
      delete state.customerOrdersCache[String(affectedCustomerId)];
      delete state.customerDisplayCache[String(affectedCustomerId)];
    }
    showToast('Orden actualizada.', 'success');
    await loadOrders();
    if (affectedCustomerId && state.selectedCustomerId === affectedCustomerId) {
      const refreshedCustomer = state.customers.find(
        (customer) => customer.id === affectedCustomerId,
      );
      if (refreshedCustomer) {
        await populateCustomerDetail(refreshedCustomer);
      }
    }
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    if (submitButton) {
      submitButton.disabled = false;
    }
    if (orderUpdatedSuccessfully) {
      markKanbanDataStale();
    }
  }
}

if (addCustomerMeasurementSetButton) {
  addCustomerMeasurementSetButton.addEventListener('click', () => {
    createMeasurementSetBlock(customerMeasurementsContainer);
  });
}

if (addUpdateCustomerMeasurementSetButton) {
  addUpdateCustomerMeasurementSetButton.addEventListener('click', () => {
    createMeasurementSetBlock(updateCustomerMeasurementsContainer);
  });
}

let customerSearchDebounce = null;
let orderSearchDebounce = null;

if (customerSearchInput) {
  customerSearchInput.addEventListener('input', (event) => {
    state.customerSearchTerm = event.target.value;
    state.customerPage = 1;
    if (customerSearchDebounce) {
      clearTimeout(customerSearchDebounce);
    }
    customerSearchDebounce = setTimeout(() => {
      loadCustomers({ page: 1 });
    }, 250);
  });
}

if (orderSearchInput) {
  orderSearchInput.addEventListener('input', (event) => {
    state.orderSearchTerm = event.target.value;
    state.orderPage = 1;
    if (orderSearchDebounce) {
      clearTimeout(orderSearchDebounce);
    }
    orderSearchDebounce = setTimeout(() => {
      loadOrders({ page: 1 });
    }, 250);
  });
}

if (orderKanbanSearchInput) {
  orderKanbanSearchInput.addEventListener('input', (event) => {
    state.kanbanSearchTerm = event.target.value;
    renderOrderKanban();
  });
}

if (orderKanbanRefreshButton) {
  orderKanbanRefreshButton.addEventListener('click', () => {
    loadKanbanOrders({ force: true });
  });
}

if (customerPageSizeSelect) {
  customerPageSizeSelect.addEventListener('change', (event) => {
    const newSize = getValidPageSize(event.target.value);
    state.customerPageSize = newSize;
    state.customerPage = 1;
    loadCustomers({ page: 1, pageSize: newSize });
  });
}

if (customerPrevPageButton) {
  customerPrevPageButton.addEventListener('click', () => {
    const currentPage = Number(state.customerPage) || 1;
    if (currentPage > 1) {
      const previousPage = currentPage - 1;
      state.customerPage = previousPage;
      loadCustomers({ page: previousPage });
    }
  });
}

if (customerNextPageButton) {
  customerNextPageButton.addEventListener('click', () => {
    const nextPage = (Number(state.customerPage) || 1) + 1;
    state.customerPage = nextPage;
    loadCustomers({ page: nextPage });
  });
}

if (orderPageSizeSelect) {
  orderPageSizeSelect.addEventListener('change', (event) => {
    const newSize = getValidPageSize(event.target.value);
    state.orderPageSize = newSize;
    state.orderPage = 1;
    loadOrders({ page: 1, pageSize: newSize });
  });
}

if (orderPrevPageButton) {
  orderPrevPageButton.addEventListener('click', () => {
    const currentPage = Number(state.orderPage) || 1;
    if (currentPage > 1) {
      const previousPage = currentPage - 1;
      state.orderPage = previousPage;
      loadOrders({ page: previousPage });
    }
  });
}

if (orderNextPageButton) {
  orderNextPageButton.addEventListener('click', () => {
    const nextPage = (Number(state.orderPage) || 1) + 1;
    state.orderPage = nextPage;
    loadOrders({ page: nextPage });
  });
}

if (showCreateCustomerButton) {
  showCreateCustomerButton.addEventListener('click', () => {
    state.pendingOrderCustomerSelection = null;
    setCreateCustomerVisible(true);
  });
}

if (orderCreateCustomerButton) {
  orderCreateCustomerButton.addEventListener('click', () => {
    state.pendingOrderCustomerSelection = { source: 'order', customerId: null };
    setCreateCustomerVisible(true);
  });
}

if (customerInvoicesRefreshButton) {
  customerInvoicesRefreshButton.addEventListener('click', async () => {
    if (!state.selectedCustomerId) {
      showToast('Selecciona un cliente para actualizar sus facturas.', 'error');
      return;
    }
    const targetId = Number(state.selectedCustomerId);
    const candidate =
      state.customers.find((item) => item.id === targetId) ||
      state.customerOptions.find((item) => item.id === targetId);
    if (!candidate) {
      await loadCustomerInvoicesForDetail({ id: targetId }, { force: true });
      return;
    }
    await loadCustomerInvoicesForDetail(candidate, { force: true });
    if (orderCustomerSelect && Number(orderCustomerSelect.value) === targetId) {
      await loadOrderInvoiceSuggestions(candidate, { force: true });
    }
  });
}

if (closeCreateCustomerButton) {
  closeCreateCustomerButton.addEventListener('click', () => {
    setCreateCustomerVisible(false);
  });
}

document.querySelectorAll('[data-modal-close]').forEach((element) => {
  element.addEventListener('click', () => {
    const target = element.dataset.modalClose;
    if (target === 'customer-create') {
      setCreateCustomerVisible(false);
    } else if (target === 'customer-detail') {
      clearCustomerDetail({ reRender: true });
    } else if (target === 'contifico-customer-invoices') {
      setContificoCustomerInvoicesVisible(false);
    } else if (target === 'contifico-invoice-lookup') {
      setContificoInvoiceLookupVisible(false);
    }
  });
});

if (contificoCustomerInvoicesModalButton) {
  contificoCustomerInvoicesModalButton.addEventListener('click', () => {
    setContificoCustomerInvoicesVisible(true);
  });
}

if (contificoInvoiceLookupModalButton) {
  contificoInvoiceLookupModalButton.addEventListener('click', () => {
    logInvoiceLookupInfo('Solicitud manual para abrir el modal de factura puntual.', {
      requestId: state.contificoPreviewInvoiceLookupRequestId || null,
    });
    setContificoInvoiceLookupVisible(true);
  });
}

if (toggleCreateUserButton) {
  toggleCreateUserButton.addEventListener('click', () => {
    const shouldShow = !state.isCreateUserVisible;
    setCreateUserVisible(shouldShow);
  });
}

if (closeCreateUserButton) {
  closeCreateUserButton.addEventListener('click', () => {
    setCreateUserVisible(false);
    toggleCreateUserButton?.focus();
  });
}


if (updateOrderForm) {
  updateOrderForm.addEventListener('submit', handleOrderUpdate);
}

if (orderTaskAddButton) {
  orderTaskAddButton.addEventListener('click', handleOrderTaskCreate);
}

if (orderTaskDescriptionInput) {
  orderTaskDescriptionInput.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      void handleOrderTaskCreate();
    }
  });
}

if (createUserForm) {
  createUserForm.addEventListener('submit', handleCreateUser);
}

if (editUserForm) {
  editUserForm.addEventListener('submit', handleEditUserSubmit);
}

if (cancelEditUserButton) {
  cancelEditUserButton.addEventListener('click', () => {
    cancelUserEdit({ focusTable: true });
  });
}

if (closeOrderDetailButton) {
  closeOrderDetailButton.addEventListener('click', () => {
    clearOrderDetail();
  });
}

kanbanDetailCloseElements.forEach((element) => {
  element.addEventListener('click', (event) => {
    event.preventDefault();
    if (
      orderKanbanDetailOverlay &&
      !orderKanbanDetailOverlay.classList.contains('hidden') &&
      currentOrderDetailHost === 'overlay'
    ) {
      clearOrderDetail();
    }
  });
});

if (orderKanbanDetailOverlay) {
  orderKanbanDetailOverlay.addEventListener('click', (event) => {
    if (event.target === orderKanbanDetailOverlay && currentOrderDetailHost === 'overlay') {
      clearOrderDetail();
    }
  });
}

if (typeof document !== 'undefined') {
  document.addEventListener('keydown', (event) => {
    if (
      event.key === 'Escape' &&
      currentOrderDetailHost === 'overlay' &&
      orderKanbanDetailOverlay &&
      !orderKanbanDetailOverlay.classList.contains('hidden')
    ) {
      clearOrderDetail();
    }
  });
}

if (createCustomerForm) {
  createCustomerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const fullName = customerFullNameInput?.value.trim() || '';
    const documentId = customerDocumentInput?.value.trim() || '';
    const phone = customerPhoneInput?.value.trim() || '';
    const email = customerEmailInput?.value.trim() || '';
    const address = customerAddressInput?.value.trim() || '';
    if (!fullName || !documentId) {
      showToast('El nombre y la cédula del cliente son obligatorios.', 'error');
      return;
    }
    const measurements = collectMeasurementSets(customerMeasurementsContainer);
    const submitButton = createCustomerForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
      const createdCustomer = await apiFetch('/customers', {
        method: 'POST',
        body: {
          full_name: fullName,
          document_id: documentId,
          phone: phone || null,
          email: email || null,
          address: address || null,
          measurements,
        },
      });
      if (
        state.pendingOrderCustomerSelection?.source === 'order' &&
        createdCustomer?.id
      ) {
        state.pendingOrderCustomerSelection.customerId = Number(createdCustomer.id);
      }
      await loadCustomers();
      await refreshCustomerOptions();
      setCreateCustomerVisible(false);
      showToast('Cliente registrado correctamente.', 'success');
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      submitButton.disabled = false;
    }
  });
}

if (fetchContificoCustomerButton) {
  fetchContificoCustomerButton.addEventListener('click', () => {
    void handleContificoCustomerLookup('create');
  });
}

if (updateCustomerForm) {
  updateCustomerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!state.selectedCustomerId) {
      showToast('Selecciona un cliente para actualizar.', 'error');
      return;
    }
    const fullNameInput =
      updateCustomerNameInput || customerDetail?.querySelector('#updateCustomerName');
    const documentInput =
      updateCustomerDocumentInput || customerDetail?.querySelector('#updateCustomerDocument');
    const phoneInput =
      updateCustomerPhoneInput || customerDetail?.querySelector('#updateCustomerPhone');
    const emailInput =
      updateCustomerEmailInput || customerDetail?.querySelector('#updateCustomerEmail');
    const addressInput =
      updateCustomerAddressInput || customerDetail?.querySelector('#updateCustomerAddress');
    const fullName = fullNameInput?.value.trim() || '';
    const documentId = documentInput?.value.trim() || '';
    const phone = phoneInput?.value.trim() || '';
    const email = emailInput?.value.trim() || '';
    const address = addressInput?.value.trim() || '';
    const measurements = collectMeasurementSets(updateCustomerMeasurementsContainer);
    const submitButton = updateCustomerForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    try {
      await apiFetch(`/customers/${state.selectedCustomerId}`, {
        method: 'PATCH',
        body: {
          full_name: fullName || null,
          document_id: documentId || null,
          phone: phone || null,
          email: email || null,
          address: address || null,
          measurements,
        },
      });
      await loadCustomers();
      await refreshCustomerOptions();
      const refreshed = state.customers.find((customer) => customer.id === state.selectedCustomerId);
      if (refreshed) {
        await populateCustomerDetail(refreshed);
      }
      showToast('Cliente actualizado correctamente.', 'success');
    } catch (error) {
      showToast(error.message, 'error');
    } finally {
      submitButton.disabled = false;
    }
  });
}

if (updateCustomerFetchContificoButton) {
  updateCustomerFetchContificoButton.addEventListener('click', () => {
    void handleContificoCustomerLookup('update');
  });
}

if (deleteCustomerButton) {
  deleteCustomerButton.addEventListener('click', async () => {
    if (!state.selectedCustomerId) return;
    if (!confirm('¿Estás seguro de eliminar este cliente? Esta acción no se puede deshacer.')) {
      return;
    }
    try {
      const deletedId = state.selectedCustomerId;
      await apiFetch(`/customers/${state.selectedCustomerId}`, { method: 'DELETE' });
      showToast('Cliente eliminado correctamente.', 'success');
      if (deletedId !== null && deletedId !== undefined) {
        delete state.customerOrdersCache[String(deletedId)];
        delete state.customerDisplayCache[String(deletedId)];
      }
      state.selectedCustomerId = null;
      await loadCustomers();
      await refreshCustomerOptions();
    } catch (error) {
      showToast(error.message, 'error');
    }
  });
}

if (deleteOrderButton) {
  deleteOrderButton.addEventListener('click', async () => {
    if (state.selectedOrderId === null) {
      return;
    }
    if (!confirm('¿Estás seguro de eliminar esta orden? Esta acción no se puede deshacer.')) {
      return;
    }
    const orderId = state.selectedOrderId;
    const orderToDelete = state.orders.find((order) => order.id === orderId);
    const affectedCustomerId = orderToDelete?.customer_id ?? null;
    try {
      await apiFetch(`/orders/${orderId}`, { method: 'DELETE' });
      showToast('Orden eliminada correctamente.', 'success');
      if (affectedCustomerId !== null && affectedCustomerId !== undefined) {
        delete state.customerOrdersCache[String(affectedCustomerId)];
        delete state.customerDisplayCache[String(affectedCustomerId)];
        const customerEntry = state.customers.find((customer) => customer.id === affectedCustomerId);
        if (customerEntry && typeof customerEntry.order_count === 'number' && customerEntry.order_count > 0) {
          customerEntry.order_count = Math.max(0, customerEntry.order_count - 1);
        }
      }
      clearOrderDetail({ skipRender: true });
      await loadOrders();
      if (affectedCustomerId) {
        await loadCustomers();
      }
      markKanbanDataStale();
    } catch (error) {
      showToast(error.message, 'error');
    }
  });
}
async function createOrder(event) {
  event.preventDefault();
  if (!createOrderForm) return;
  const isCreatePanelHidden = !orderCreatePanel || orderCreatePanel.classList.contains('hidden');
  if (createOrderForm.dataset.disabled === 'true' || isCreatePanelHidden) {
    return;
  }
  const newOrderNumber = document.getElementById('newOrderNumber').value.trim();
  const selectedCustomerId = Number(orderCustomerSelect.value);
  const newCustomerName = document.getElementById('newCustomerName').value.trim();
  const newCustomerDocument = document.getElementById('newCustomerDocument').value.trim();
  const newCustomerContact = document.getElementById('newCustomerContact').value.trim();
  const newOrderStatus = document.getElementById('newOrderStatus').value;
  const newOrderDeliveryDateRaw = newOrderDeliveryDateInput?.value || '';
  const newOrderDeliveryDate = normalizeDateForApi(newOrderDeliveryDateRaw);
  const newOrderNotes = document.getElementById('newOrderNotes').value.trim();
  const assignedTailorId = assignTailorSelect.value ? Number(assignTailorSelect.value) : null;
  const assignedVendorId = assignVendorSelect?.value ? Number(assignVendorSelect.value) : null;
  const invoiceNumber = newOrderInvoiceInput?.value.trim() || '';
  const originBranch = newOrderOriginSelect?.value || '';
  const measurements = collectMeasurements();
  const { tasks: orderTasks, firstInput: firstTaskInput } = collectNewOrderTasks();


  if (!selectedCustomerId) {
    showToast('Selecciona un cliente para registrar la orden.', 'error');
    return;
  }

  if (!originBranch) {
    showToast('Selecciona el establecimiento remitente.', 'error');
    return;
  }

  if (!orderTasks.length) {
    showToast('Agrega al menos un trabajo para la orden.', 'error');
    if (firstTaskInput) {
      firstTaskInput.focus();
    }
    return;
  }

  const submitButton = createOrderForm.querySelector('button[type="submit"]');
  if (submitButton) {
    submitButton.disabled = true;
  }
  let orderCreatedSuccessfully = false;
  try {
    await apiFetch('/orders', {
      method: 'POST',
      body: {
        order_number: newOrderNumber,
        customer_id: selectedCustomerId,
        customer_name: newCustomerName || null,
        customer_document: newCustomerDocument || null,
        customer_contact: newCustomerContact || null,
        status: newOrderStatus,
        notes: newOrderNotes || null,
        measurements,
        assigned_tailor_id: assignedTailorId,
        assigned_vendor_id: assignedVendorId,
        delivery_date: newOrderDeliveryDate ? newOrderDeliveryDate : null,
        invoice_number: invoiceNumber || null,
        origin_branch: originBranch,
        tasks: orderTasks,
      },
    });
    orderCreatedSuccessfully = true;
    delete state.customerOrdersCache[String(selectedCustomerId)];
    delete state.customerDisplayCache[String(selectedCustomerId)];
    await loadOrders();
    await loadCustomers();
    resetCreateOrderForm();
    showToast('Orden creada correctamente.', 'success');
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    if (orderCreatedSuccessfully) {
      markKanbanDataStale();
    }
    syncCreateOrderFormDisabled();
  }
}

if (createOrderForm) {
  createOrderForm.addEventListener('submit', createOrder);
}

function handleOrderCustomerChange() {
  const selectedId = Number(orderCustomerSelect.value);
  const customer = (state.customerOptions || []).find((item) => item.id === selectedId);
  const documentInput = document.getElementById('newCustomerDocument');
  const nameInput = document.getElementById('newCustomerName');
  const contactInput = document.getElementById('newCustomerContact');
  clearOrderInvoiceLookup();
  if (!customer) {
    if (documentInput) documentInput.value = '';
    if (nameInput) nameInput.value = '';
    if (contactInput) contactInput.value = '';
    renderCustomerMeasurementOptions(null);
    clearOrderInvoiceSuggestions();
    updateOrderInvoiceLookupButtonState();
    return;
  }
  if (documentInput) documentInput.value = customer.document_id || '';
  if (nameInput) nameInput.value = customer.full_name || '';
  if (contactInput) contactInput.value = customer.phone || '';
  renderCustomerMeasurementOptions(customer);
  void loadOrderInvoiceSuggestions(customer);
  updateOrderInvoiceLookupButtonState();
}

if (orderCustomerSelect) {
  orderCustomerSelect.addEventListener('change', handleOrderCustomerChange);
}

if (newOrderInvoiceInput) {
  newOrderInvoiceInput.addEventListener('input', updateOrderInvoiceLookupButtonState);
}

if (orderInvoiceLookupButton) {
  orderInvoiceLookupButton.addEventListener('click', () => {
    void handleOrderInvoiceLookup();
  });
}

populateEstablishmentSelect(newOrderOriginSelect);
populateEstablishmentSelect(orderDetailOriginSelect);
ensureNewOrderTaskRow();
clearOrderInvoiceSuggestions();

function parseDateValue(value) {
  if (!value) {
    return null;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return parsed;
}

function formatDateTimeForApi(date) {
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

function normalizeDateForApi(value) {
  if (!value) {
    return '';
  }
  if (value instanceof Date) {
    return formatDateTimeForApi(value);
  }
  if (typeof value === 'number') {
    return formatDateTimeForApi(new Date(value));
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return '';
    }
    const match = trimmed.match(
      /^(\d{4}-\d{2}-\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?)?(?:\.\d+)?(?:Z)?$/,
    );
    if (match) {
      const datePart = match[1];
      const hourPart = match[2] ?? '00';
      const minutePart = match[3] ?? '00';
      const secondPart = match[4] ?? '00';
      return `${datePart}T${hourPart}:${minutePart}:${secondPart}`;
    }
    const parsed = parseDateValue(trimmed);
    if (parsed) {
      return formatDateTimeForApi(parsed);
    }
  }
  return '';
}

function toTimestamp(value) {
  const parsed = parseDateValue(value);
  return parsed ? parsed.getTime() : null;
}

function compareOrdersForDisplay(a, b) {
  const aDelivered = isOrderDelivered(a.status);
  const bDelivered = isOrderDelivered(b.status);
  if (aDelivered !== bDelivered) {
    return aDelivered ? 1 : -1;
  }

  const aDelivery = toTimestamp(a.delivery_date);
  const bDelivery = toTimestamp(b.delivery_date);

  if (aDelivered && bDelivered) {
    if (aDelivery !== bDelivery) {
      if (aDelivery === null) return 1;
      if (bDelivery === null) return -1;
      return bDelivery - aDelivery;
    }
  } else if (aDelivery !== bDelivery) {
    if (aDelivery === null) return 1;
    if (bDelivery === null) return -1;
    return aDelivery - bDelivery;
  }

  if (!aDelivered) {
    const aCreated = toTimestamp(a.created_at);
    const bCreated = toTimestamp(b.created_at);
    if (aCreated !== bCreated) {
      if (aCreated === null) return 1;
      if (bCreated === null) return -1;
      return aCreated - bCreated;
    }
  } else {
    const aUpdated = toTimestamp(a.updated_at);
    const bUpdated = toTimestamp(b.updated_at);
    if (aUpdated !== bUpdated) {
      if (aUpdated === null) return 1;
      if (bUpdated === null) return -1;
      return bUpdated - aUpdated;
    }
  }

  const aOrder = (a.order_number || '').toString().toLowerCase();
  const bOrder = (b.order_number || '').toString().toLowerCase();
  const orderComparison = aOrder.localeCompare(bOrder, undefined, {
    numeric: true,
    sensitivity: 'base',
  });
  if (orderComparison !== 0) {
    return orderComparison;
  }

  const aId = typeof a.id === 'number' ? a.id : Number(a.id) || 0;
  const bId = typeof b.id === 'number' ? b.id : Number(b.id) || 0;
  return aId - bId;
}

function removeOrderDetailRow() {
  if (activeOrderDetailRow && activeOrderDetailRow.parentNode) {
    activeOrderDetailRow.parentNode.removeChild(activeOrderDetailRow);
  }
  activeOrderDetailRow = null;
}

function attachOrderDetailToOverlay() {
  if (!orderDetail || !orderKanbanDetailContainer) {
    return;
  }
  if (activeOrderDetailRow && activeOrderDetailRow.parentNode) {
    activeOrderDetailRow.parentNode.removeChild(activeOrderDetailRow);
    activeOrderDetailRow = null;
  }
  orderKanbanDetailContainer.appendChild(orderDetail);
  currentOrderDetailHost = 'overlay';
  orderDetail.classList.remove('hidden');
  updateOrderDetailOverlayVisibility();
  requestAnimationFrame(() => {
    if (orderKanbanDetailDialog?.isConnected) {
      orderKanbanDetailDialog.focus();
    }
  });
}

function updateOrderDetailOverlayVisibility() {
  if (!orderKanbanDetailContainer) {
    return;
  }
  const isOverlayHost =
    currentOrderDetailHost === 'overlay' && orderKanbanDetailContainer.contains(orderDetail);
  const shouldShowDetail = isOverlayHost && state.selectedOrderId !== null;
  if (currentOrderDetailHost === 'overlay') {
    orderKanbanDetailContainer.classList.toggle('hidden', !shouldShowDetail);
    if (orderKanbanDetailOverlay) {
      orderKanbanDetailOverlay.classList.toggle('hidden', !shouldShowDetail);
      orderKanbanDetailOverlay.setAttribute('aria-hidden', shouldShowDetail ? 'false' : 'true');
    }
    if (orderKanbanDetailMessage) {
      orderKanbanDetailMessage.classList.toggle('hidden', shouldShowDetail);
    }
  } else {
    orderKanbanDetailContainer.classList.add('hidden');
    if (orderKanbanDetailOverlay) {
      orderKanbanDetailOverlay.classList.add('hidden');
      orderKanbanDetailOverlay.setAttribute('aria-hidden', 'true');
    }
    if (orderKanbanDetailMessage) {
      orderKanbanDetailMessage.classList.remove('hidden');
    }
  }
  if (orderDetail) {
    orderDetail.classList.toggle('kanban-mode', isOverlayHost);
    const hideDetailElement = currentOrderDetailHost === 'overlay' && !shouldShowDetail;
    if (currentOrderDetailHost === 'overlay') {
      orderDetail.classList.toggle('hidden', hideDetailElement);
      orderDetail.setAttribute('aria-hidden', shouldShowDetail ? 'false' : 'true');
    } else {
      orderDetail.removeAttribute('aria-hidden');
    }
  }
  if (document.body) {
    if (currentOrderDetailHost === 'overlay') {
      document.body.classList.toggle('kanban-detail-open', shouldShowDetail);
    } else {
      document.body.classList.remove('kanban-detail-open');
    }
  }
  updateOrderActionButtons();
}

function updateOrderActionButtons() {
  if (!deleteOrderButton) {
    return;
  }
  const isAdmin = state.user?.role === 'administrador';
  const hasSelection = typeof state.selectedOrderId === 'number';
  deleteOrderButton.disabled = !isAdmin || !hasSelection;
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

function createStatusBadge(status) {
  const badge = document.createElement('span');
  badge.className = 'status-badge';
  const text = status && status.toString().trim() ? status : 'Sin estado';
  badge.textContent = text;
  badge.classList.add(`status-${getStatusBadgeVariant(status)}`);
  return badge;
}


function getValidPageSize(value) {
  const numericValue = Number(value);
  if (PAGE_SIZE_OPTIONS.includes(numericValue)) {
    return numericValue;
  }
  return DEFAULT_PAGE_SIZE;
}

function updatePaginationControls({
  infoElement,
  prevButton,
  nextButton,
  pageSizeSelect,
  currentPage,
  totalItems,
  pageSize,
  emptyLabel,
}) {
  const totalPages = totalItems > 0 ? Math.ceil(totalItems / pageSize) : 1;
  const normalizedPage = totalItems > 0 ? Math.min(Math.max(currentPage, 1), totalPages) : 1;
  const startItem = totalItems === 0 ? 0 : (normalizedPage - 1) * pageSize + 1;
  const endItem = totalItems === 0 ? 0 : Math.min(normalizedPage * pageSize, totalItems);

  if (infoElement) {
    infoElement.textContent =
      totalItems === 0
        ? `Sin ${emptyLabel}`
        : `Mostrando ${startItem}-${endItem} de ${totalItems}`;
  }

  if (prevButton) {
    const isDisabled = totalItems === 0 || normalizedPage <= 1;
    prevButton.disabled = isDisabled;
    prevButton.setAttribute('aria-disabled', isDisabled ? 'true' : 'false');
  }

  if (nextButton) {
    const isDisabled = totalItems === 0 || normalizedPage >= totalPages;
    nextButton.disabled = isDisabled;
    nextButton.setAttribute('aria-disabled', isDisabled ? 'true' : 'false');
  }

  if (pageSizeSelect && pageSizeSelect.value !== String(pageSize)) {
    pageSizeSelect.value = String(pageSize);
  }

  return normalizedPage;
}


function matchesKanbanSearch(order, normalizedSearch) {
  if (!normalizedSearch) {
    return true;
  }
  const searchableValues = [
    order?.order_number,
    order?.customer_name,
    order?.customer_document,
    order?.customer_contact,
    order?.invoice_number,
    order?.assigned_tailor?.full_name,
    order?.assigned_vendor?.full_name,
  ];
  return searchableValues.some((value) => {
    if (!value) return false;
    return normalizeText(value).includes(normalizedSearch);
  });
}

function createKanbanMetaItem(label, value) {
  const item = document.createElement('div');
  item.className = 'kanban-card-meta-item';
  const labelElement = document.createElement('span');
  labelElement.className = 'kanban-card-meta-label';
  labelElement.textContent = `${label}:`;
  const valueElement = document.createElement('span');
  valueElement.className = 'kanban-card-meta-value';
  valueElement.textContent = value || '—';
  item.appendChild(labelElement);
  item.appendChild(valueElement);
  return item;
}

async function openOrderDetailFromKanban(order) {
  if (!order || order.id === undefined || order.id === null) {
    showToast('No se pudo abrir el detalle de la orden seleccionada.', 'error');
    return;
  }

  if (!lastKanbanFocusedOrderId) {
    lastKanbanFocusedOrderId = String(order.id);
  }
  if (!(lastKanbanFocusedElement instanceof HTMLElement)) {
    lastKanbanFocusedElement =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
  }

  const orderIdKey = String(order.id);
  setActiveDashboardTab('ordersPanel');
  if (state.activeOrdersView !== 'kanban') {
    setActiveOrdersView('kanban');
  }

  let detail = state.orders.find((item) => String(item.id) === orderIdKey);
  if (!detail) {
    try {
      detail = await apiFetch(`/orders/${encodeURIComponent(orderIdKey)}`);
    } catch (error) {
      /* ignore fetch failure and fall back to cached data */
    }
  }

  if (!detail) {
    detail = order;
  }

  if (!detail || detail.id === undefined || detail.id === null) {
    showToast('No se pudo abrir el detalle de la orden seleccionada.', 'error');
    return;
  }

  const remainingOrders = state.orders.filter((item) => String(item.id) !== orderIdKey);
  state.orders = [...remainingOrders, detail];
  if (typeof state.orderTotal !== 'number' || state.orderTotal < state.orders.length) {
    state.orderTotal = state.orders.length;
  }

  populateOrderDetail(detail, { skipRender: true, focusOnDetail: false });
  attachOrderDetailToOverlay();
  renderOrderKanban();
}

function createKanbanCard(order) {
  const card = document.createElement('article');
  card.className = 'kanban-card';
  card.classList.add('is-clickable');
  card.setAttribute('role', 'button');
  card.tabIndex = 0;
  if (order?.id !== undefined && order?.id !== null) {
    card.dataset.orderId = String(order.id);
  }

  const isActive =
    state.selectedOrderId !== null &&
    order?.id !== undefined &&
    order?.id !== null &&
    String(state.selectedOrderId) === String(order.id);
  card.classList.toggle('is-active', Boolean(isActive));
  card.setAttribute('aria-pressed', isActive ? 'true' : 'false');

  const labelParts = [];
  if (order?.order_number) {
    labelParts.push(`Orden ${order.order_number}`);
  }
  if (order?.customer_name) {
    labelParts.push(order.customer_name);
  }
  if (labelParts.length) {
    card.setAttribute('aria-label', `Ver detalle de ${labelParts.join(' · ')}`);
  } else {
    card.setAttribute('aria-label', 'Ver detalle de la orden seleccionada');
  }
  card.title = 'Ver detalle de la orden';

  const handleCardActivation = (event) => {
    event.preventDefault();
    if (order?.id !== undefined && order?.id !== null) {
      lastKanbanFocusedOrderId = String(order.id);
    }
    lastKanbanFocusedElement = card;
    openOrderDetailFromKanban(order);
  };

  card.addEventListener('click', handleCardActivation);
  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleCardActivation(event);
    }
  });


  const header = document.createElement('div');
  header.className = 'kanban-card-header';
  const orderNumber = document.createElement('span');
  orderNumber.className = 'kanban-card-order';
  orderNumber.textContent = order?.order_number || 'Sin número';
  header.appendChild(orderNumber);
  if (order?.status) {
    header.appendChild(createStatusBadge(order.status));
  }
  card.appendChild(header);

  const body = document.createElement('div');
  body.className = 'kanban-card-body';
  body.appendChild(createKanbanMetaItem('Cliente', order?.customer_name || '—'));
  if (order?.customer_document) {
    body.appendChild(createKanbanMetaItem('Documento', order.customer_document));
  }
  if (order?.assigned_tailor?.full_name) {
    body.appendChild(createKanbanMetaItem('Sastre', order.assigned_tailor.full_name));
  }
  if (order?.assigned_vendor?.full_name) {
    body.appendChild(createKanbanMetaItem('Vendedor', order.assigned_vendor.full_name));
  }
  card.appendChild(body);

  const footer = document.createElement('div');
  footer.className = 'kanban-card-footer';
  const delivery = document.createElement('span');
  delivery.className = 'kanban-card-delivery';
  if (order?.delivery_date) {
    delivery.textContent = formatDeliveryDateDisplay(order);
    if (isDeliveryDateOverdue(order.delivery_date, order.status)) {
      delivery.classList.add('overdue');
    } else if (isDeliveryDateClose(order.delivery_date, order.status)) {
      delivery.classList.add('due-soon');
    }
  } else {
    delivery.textContent = 'Sin fecha de entrega';
  }
  footer.appendChild(delivery);

  if (order?.updated_at) {
    const updated = document.createElement('span');
    updated.className = 'kanban-card-updated';
    const time = document.createElement('time');
    time.dateTime = order.updated_at;
    time.textContent = formatDate(order.updated_at);
    updated.textContent = 'Actualizado:';
    updated.appendChild(document.createTextNode(' '));
    updated.appendChild(time);
    footer.appendChild(updated);
  }

  card.appendChild(footer);
  return card;
}

function renderOrderKanban() {
  if (!orderKanbanColumns) {
    return;
  }

  updateOrderDetailOverlayVisibility();

  if (orderKanbanSearchInput && orderKanbanSearchInput.value !== state.kanbanSearchTerm) {
    orderKanbanSearchInput.value = state.kanbanSearchTerm;
  }

  orderKanbanColumns.innerHTML = '';
  if (orderKanbanStatus) {
    orderKanbanStatus.textContent = '';
    orderKanbanStatus.classList.add('hidden');
  }

  if (!state.token) {
    if (orderKanbanStatus) {
      orderKanbanStatus.textContent = 'Inicia sesión para ver el tablero de órdenes.';
      orderKanbanStatus.classList.remove('hidden');
    }
    updateOrderDetailOverlayVisibility();
    return;
  }

  if (state.kanbanLoading) {
    if (orderKanbanStatus) {
      orderKanbanStatus.textContent = 'Cargando tablero Kanban...';
      orderKanbanStatus.classList.remove('hidden');
    }
    updateOrderDetailOverlayVisibility();
    return;
  }

  if (state.kanbanError) {
    if (orderKanbanStatus) {
      orderKanbanStatus.textContent = state.kanbanError;
      orderKanbanStatus.classList.remove('hidden');
    }
    updateOrderDetailOverlayVisibility();
    return;
  }

  const orders = Array.isArray(state.kanbanOrders) ? state.kanbanOrders : [];
  if (!orders.length) {
    if (orderKanbanStatus) {
      orderKanbanStatus.textContent = state.kanbanNeedsRefresh
        ? 'Carga el tablero para ver las órdenes registradas.'
        : 'No hay órdenes registradas.';
      orderKanbanStatus.classList.remove('hidden');
    }
    updateOrderDetailOverlayVisibility();
    return;
  }

  const normalizedSearch = normalizeText(state.kanbanSearchTerm);
  const filteredOrders = normalizedSearch
    ? orders.filter((order) => matchesKanbanSearch(order, normalizedSearch))
    : orders;

  if (!filteredOrders.length) {
    if (orderKanbanStatus) {
      orderKanbanStatus.textContent = 'No se encontraron órdenes que coincidan con la búsqueda actual.';
      orderKanbanStatus.classList.remove('hidden');
    }
    updateOrderDetailOverlayVisibility();
    return;
  }

  const orderedStatuses = [];
  const seenStatuses = new Set();

  const appendStatus = (status) => {
    const label = status && status.toString().trim() ? status : KANBAN_FALLBACK_STATUS;
    if (!seenStatuses.has(label)) {
      seenStatuses.add(label);
      orderedStatuses.push(label);
    }
  };

  if (Array.isArray(state.statuses) && state.statuses.length) {
    state.statuses.forEach(appendStatus);
  }
  filteredOrders.forEach((order) => appendStatus(order?.status));

  if (!seenStatuses.size) {
    orderedStatuses.push(KANBAN_FALLBACK_STATUS);
  }

  const groupedByStatus = new Map();
  orderedStatuses.forEach((status) => {
    groupedByStatus.set(status, []);
  });

  filteredOrders.forEach((order) => {
    const label = order?.status && order.status.toString().trim()
      ? order.status
      : KANBAN_FALLBACK_STATUS;
    if (!groupedByStatus.has(label)) {
      groupedByStatus.set(label, []);
      orderedStatuses.push(label);
    }
    groupedByStatus.get(label).push(order);
  });

  orderedStatuses.forEach((status) => {
    const column = document.createElement('section');
    column.className = 'kanban-column';
    column.dataset.status = status || KANBAN_FALLBACK_STATUS;

    const header = document.createElement('div');
    header.className = 'kanban-column-header';
    const title = document.createElement('h4');
    title.className = 'kanban-column-title';
    title.textContent = status || KANBAN_FALLBACK_STATUS;
    header.appendChild(title);

    const count = document.createElement('span');
    count.className = 'kanban-column-count';
    const ordersForStatus = groupedByStatus.get(status) || [];
    count.textContent = String(ordersForStatus.length);
    header.appendChild(count);

    column.appendChild(header);

    const body = document.createElement('div');
    body.className = 'kanban-column-body';

    if (!ordersForStatus.length) {
      body.classList.add('is-empty');
      const emptyMessage = document.createElement('p');
      emptyMessage.textContent = 'Sin órdenes en este estado.';
      body.appendChild(emptyMessage);
    } else {
      ordersForStatus.sort(compareOrdersForDisplay).forEach((order) => {
        body.appendChild(createKanbanCard(order));
      });
    }

    column.appendChild(body);
    orderKanbanColumns.appendChild(column);
  });

  if (orderKanbanStatus) {
    const messages = [];
    if (state.kanbanNeedsRefresh) {
      messages.push('El tablero contiene información en caché. Actualízalo para ver los últimos cambios.');
    }
    if (state.kanbanLastUpdated) {
      messages.push(`Última actualización: ${formatDate(state.kanbanLastUpdated)}.`);
    }
    if (messages.length) {
      orderKanbanStatus.textContent = messages.join(' ');
      orderKanbanStatus.classList.remove('hidden');
    } else {
      orderKanbanStatus.classList.add('hidden');
    }
  }

  updateOrderDetailOverlayVisibility();
}

function renderOrders() {
  if (!ordersTableBody) return;

  const pageSize = getValidPageSize(state.orderPageSize);
  if (state.orderPageSize !== pageSize) {
    state.orderPageSize = pageSize;
  }

  removeOrderDetailRow();
  if (orderDetail) {
    orderDetail.classList.add('hidden');
  }

  ordersTableBody.innerHTML = '';
  if (orderSearchInput && orderSearchInput.value !== state.orderSearchTerm) {
    orderSearchInput.value = state.orderSearchTerm;
  }

  const totalItems =
    typeof state.orderTotal === 'number' ? state.orderTotal : state.orders.length;

  const normalizedPage =
    updatePaginationControls({
      infoElement: orderPaginationInfo,
      prevButton: orderPrevPageButton,
      nextButton: orderNextPageButton,
      pageSizeSelect: orderPageSizeSelect,
      currentPage: state.orderPage || 1,
      totalItems,
      pageSize,
      emptyLabel: 'órdenes',
    }) || (state.orderPage || 1);

  if (state.orderPage !== normalizedPage) {
    state.orderPage = normalizedPage;
  }

  if (!state.orders.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = ORDER_TABLE_COLUMN_COUNT;
    const hasSearch = Boolean(state.orderSearchTerm.trim());
    cell.textContent = totalItems === 0
      ? hasSearch
        ? 'No se encontraron órdenes que coincidan con la búsqueda.'
        : 'No hay órdenes registradas todavía.'
      : 'No hay órdenes para la página seleccionada.';
    cell.className = 'muted';
    row.appendChild(cell);
    ordersTableBody.appendChild(row);
    clearOrderDetail({ skipRender: true });
    return;
  }

  if (
    state.selectedOrderId !== null &&
    state.orders.every((order) => order.id !== state.selectedOrderId)
  ) {
    clearOrderDetail({ skipRender: true });
  }

  const sortedOrders = [...state.orders].sort(compareOrdersForDisplay);

  let hasActiveDetail = false;

  sortedOrders.forEach((order) => {
    const row = document.createElement('tr');
    row.classList.add('order-row');
    row.dataset.orderId = String(order.id);

    const isSelected = state.selectedOrderId === order.id;
    if (isSelected) {
      row.classList.add('is-selected');
    }

    const orderCell = document.createElement('td');
    orderCell.dataset.label = 'Orden';
    orderCell.innerHTML = `<strong>${order.order_number}</strong>`;

    const customerCell = document.createElement('td');
    customerCell.dataset.label = 'Cliente';
    customerCell.textContent = order.customer_name || '—';

    const statusCell = document.createElement('td');
    statusCell.dataset.label = 'Estado';
    statusCell.appendChild(createStatusBadge(order.status));

    const createdCell = document.createElement('td');
    createdCell.dataset.label = 'Fecha de ingreso';
    createdCell.textContent = formatDate(order.created_at);

    const deliveryCell = document.createElement('td');
    deliveryCell.dataset.label = 'Fecha de entrega';
    if (order.delivery_date) {
      deliveryCell.textContent = formatDeliveryDateDisplay(order);
      if (isDeliveryDateOverdue(order.delivery_date, order.status)) {
        deliveryCell.classList.add('overdue');
      } else if (isDeliveryDateClose(order.delivery_date, order.status)) {
        deliveryCell.classList.add('due-soon');
      }
    } else {
      deliveryCell.innerHTML = '<span class="muted">Sin definir</span>';
    }

    const actionsCell = document.createElement('td');
    actionsCell.dataset.label = 'Acciones';
    const detailButton = document.createElement('button');
    detailButton.type = 'button';
    detailButton.className = 'secondary';
    detailButton.textContent = isSelected ? 'Ocultar detalle' : 'Ver detalle';
    detailButton.setAttribute('aria-controls', 'orderDetail');
    detailButton.setAttribute('aria-expanded', isSelected ? 'true' : 'false');
    detailButton.addEventListener('click', () => {
      if (state.selectedOrderId === order.id) {
        clearOrderDetail();
      } else {
        populateOrderDetail(order, { focusOnDetail: false });
        attachOrderDetailToOverlay();
      }
    });
    actionsCell.appendChild(detailButton);

    row.appendChild(orderCell);
    row.appendChild(customerCell);
    row.appendChild(statusCell);
    row.appendChild(createdCell);
    row.appendChild(deliveryCell);
    row.appendChild(actionsCell);

    ordersTableBody.appendChild(row);

    if (isSelected) {
      hasActiveDetail = true;
      detailButton.textContent = 'Ocultar detalle';
      detailButton.setAttribute('aria-expanded', 'true');
      if (currentOrderDetailHost !== 'overlay') {
        attachOrderDetailToOverlay();
      }
    }
  });

  if (!hasActiveDetail && orderDetail) {
    orderDetail.classList.add('hidden');
    if (currentOrderDetailHost !== 'overlay') {
      currentOrderDetailHost = null;
    }
    updateOrderDetailOverlayVisibility();
  }
}


function renderUsers() {
  if (!usersTableBody) return;
  usersTableBody.innerHTML = '';

  const appendMessageRow = (message) => {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 4;
    cell.className = 'muted';
    cell.textContent = message;
    row.appendChild(cell);
    usersTableBody.appendChild(row);
  };

  if (!state.user || state.user.role !== 'administrador') {
    appendMessageRow('Inicia sesión como administrador para ver los usuarios.');
    updateUserEditForm();
    return;
  }

  if (state.usersLoadError) {
    appendMessageRow(state.usersLoadError);
    updateUserEditForm();
    return;
  }

  if (!state.usersLoaded) {
    appendMessageRow('Cargando usuarios...');
    updateUserEditForm();
    return;
  }

  if (!state.users.length) {
    appendMessageRow('No hay usuarios registrados.');
    updateUserEditForm();
    return;
  }

  state.users.forEach((user) => {
    const row = document.createElement('tr');
    row.classList.add('user-row');
    const isEditing = state.editingUserId === user.id;
    if (isEditing) {
      row.classList.add('is-editing');
    }

    const usernameCell = document.createElement('td');
    usernameCell.dataset.label = 'Usuario';
    usernameCell.textContent = user.username;

    const nameCell = document.createElement('td');
    nameCell.dataset.label = 'Nombre completo';
    nameCell.textContent = user.full_name;

    const roleCell = document.createElement('td');
    roleCell.dataset.label = 'Rol';
    roleCell.textContent = ROLE_LABELS[user.role] || user.role;

    const actionsCell = document.createElement('td');
    actionsCell.dataset.label = 'Acciones';
    const editButton = document.createElement('button');
    editButton.type = 'button';
    editButton.className = 'secondary';
    editButton.textContent = isEditing ? 'Cerrar formulario' : 'Editar';
    editButton.addEventListener('click', () => {
      if (state.editingUserId === user.id) {
        cancelUserEdit();
      } else {
        startUserEdit(user.id);
      }
    });
    actionsCell.appendChild(editButton);

    row.appendChild(usernameCell);
    row.appendChild(nameCell);
    row.appendChild(roleCell);
    row.appendChild(actionsCell);

    usersTableBody.appendChild(row);
  });

  updateUserEditForm();
}

function populateUserRoleSelect(selectElement, selectedValue = DEFAULT_NEW_USER_ROLE) {
  if (!selectElement) return;
  const normalized = (selectedValue || '').trim();
  const fallbackIndex = Math.max(
    USER_ROLE_OPTIONS.findIndex((option) => option.value === DEFAULT_NEW_USER_ROLE),
    0,
  );
  let selectedIndex = -1;
  selectElement.innerHTML = '';
  USER_ROLE_OPTIONS.forEach(({ value, label }, index) => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    if (normalized === value) {
      option.selected = true;
      selectedIndex = index;
    }
    selectElement.appendChild(option);
  });
  if (selectedIndex === -1) {
    selectElement.selectedIndex = fallbackIndex;
  }
}

function resetCreateUserForm() {
  if (newUserUsernameInput) {
    newUserUsernameInput.value = '';
  }
  if (newUserFullNameInput) {
    newUserFullNameInput.value = '';
  }
  if (newUserPasswordInput) {
    newUserPasswordInput.value = '';
  }
  populateUserRoleSelect(newUserRoleSelect, DEFAULT_NEW_USER_ROLE);
}

function setCreateUserVisible(visible) {
  const isAdmin = state.user?.role === 'administrador';
  const shouldShow = Boolean(visible) && isAdmin;
  state.isCreateUserVisible = shouldShow;
  updateUserCreationForm();
  if (shouldShow) {
    if (userCreateContainer && typeof userCreateContainer.scrollIntoView === 'function') {
      userCreateContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    const firstField = createUserForm?.querySelector('input, select, textarea');
    firstField?.focus();
  } else if (isAdmin) {
    resetCreateUserForm();
  }
}

function populateUserEditForm(user) {
  if (!user || state.user?.role !== 'administrador') {
    clearUserEditForm();
    return;
  }
  if (editUserUsernameInput) {
    editUserUsernameInput.value = user.username || '';
  }
  if (editUserFullNameInput) {
    editUserFullNameInput.value = user.full_name || '';
  }
  populateUserRoleSelect(editUserRoleSelect, user.role || DEFAULT_NEW_USER_ROLE);
  if (editUserPasswordInput) {
    editUserPasswordInput.value = '';
  }
  if (editUserTitle) {
    const displayName = (user.full_name || '').trim() || user.username || 'Editar usuario';
    editUserTitle.textContent = `Editar usuario: ${displayName}`;
  }
  if (userEditContainer) {
    userEditContainer.classList.remove('hidden');
    userEditContainer.setAttribute('aria-hidden', 'false');
  }
}

function clearUserEditForm() {
  if (editUserUsernameInput) {
    editUserUsernameInput.value = '';
  }
  if (editUserFullNameInput) {
    editUserFullNameInput.value = '';
  }
  if (editUserPasswordInput) {
    editUserPasswordInput.value = '';
  }
  populateUserRoleSelect(editUserRoleSelect, DEFAULT_NEW_USER_ROLE);
  if (editUserTitle) {
    editUserTitle.textContent = 'Editar usuario';
  }
  if (userEditContainer) {
    userEditContainer.classList.add('hidden');
    userEditContainer.setAttribute('aria-hidden', 'true');
  }
}

function updateUserEditForm() {
  const isAdmin = state.user?.role === 'administrador';
  if (!isAdmin) {
    state.editingUserId = null;
    clearUserEditForm();
    return;
  }
  const editingId = state.editingUserId;
  if (!editingId) {
    clearUserEditForm();
    return;
  }
  const editingUser = state.users.find((user) => user.id === editingId);
  if (!editingUser) {
    state.editingUserId = null;
    clearUserEditForm();
    return;
  }
  const currentUsername = editUserUsernameInput?.value || '';
  if (!currentUsername || currentUsername !== (editingUser.username || '')) {
    populateUserEditForm(editingUser);
  } else {
    if (editUserTitle) {
      const displayName = (editingUser.full_name || '').trim() || editingUser.username || 'Editar usuario';
      editUserTitle.textContent = `Editar usuario: ${displayName}`;
    }
    if (userEditContainer) {
      userEditContainer.classList.remove('hidden');
      userEditContainer.setAttribute('aria-hidden', 'false');
    }
  }
}

function startUserEdit(userId) {
  if (!state.user || state.user.role !== 'administrador') {
    showToast('Solo los administradores pueden editar usuarios.', 'error');
    return;
  }
  const numericId = Number(userId);
  if (!Number.isFinite(numericId)) {
    showToast('Selecciona un usuario válido para editar.', 'error');
    return;
  }
  const user = state.users.find((entry) => entry.id === numericId);
  if (!user) {
    showToast('No se encontró el usuario seleccionado.', 'error');
    return;
  }
  state.editingUserId = numericId;
  populateUserEditForm(user);
  renderUsers();
  if (editUserFullNameInput) {
    editUserFullNameInput.focus();
    editUserFullNameInput.select?.();
  }
}

function cancelUserEdit({ focusTable = false } = {}) {
  state.editingUserId = null;
  clearUserEditForm();
  renderUsers();
  if (focusTable && usersTableBody) {
    const firstButton = usersTableBody.querySelector('button');
    firstButton?.focus();
  }
}

function updateUserCreationForm() {
  const isAdmin = state.user?.role === 'administrador';
  if (!isAdmin && state.isCreateUserVisible) {
    state.isCreateUserVisible = false;
  }
  const shouldShow = isAdmin && state.isCreateUserVisible;
  if (userCreateContainer) {
    userCreateContainer.classList.toggle('hidden', !shouldShow);
    userCreateContainer.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');
  }
  if (toggleCreateUserButton) {
    toggleCreateUserButton.classList.toggle('hidden', !isAdmin);
    toggleCreateUserButton.disabled = !isAdmin;
    toggleCreateUserButton.setAttribute('aria-expanded', shouldShow ? 'true' : 'false');
    toggleCreateUserButton.textContent = shouldShow ? 'Ocultar formulario' : 'Registrar usuario';
  }
  if (createUserForm) {
    const elements = createUserForm.querySelectorAll('input, select, button, textarea');
    elements.forEach((element) => {
      if (element.tagName === 'BUTTON') {
        const isLoading = element.dataset.loading === 'true';
        element.disabled = !isAdmin || isLoading;
      } else {
        element.disabled = !isAdmin;
      }
    });
  }
  if (!isAdmin) {
    resetCreateUserForm();
  }
}

async function handleCreateUser(event) {
  event.preventDefault();
  if (!state.user || state.user.role !== 'administrador') {
    showToast('Solo los administradores pueden crear usuarios.', 'error');
    return;
  }
  const username = newUserUsernameInput?.value?.trim() || '';
  if (!username) {
    showToast('Ingresa un nombre de usuario.', 'error');
    if (newUserUsernameInput) {
      newUserUsernameInput.focus();
    }
    return;
  }
  const fullName = newUserFullNameInput?.value?.trim() || '';
  if (!fullName) {
    showToast('Ingresa el nombre completo.', 'error');
    if (newUserFullNameInput) {
      newUserFullNameInput.focus();
    }
    return;
  }
  const passwordRaw = newUserPasswordInput?.value || '';
  const password = passwordRaw.trim();
  if (!password) {
    showToast('Ingresa una contraseña temporal.', 'error');
    if (newUserPasswordInput) {
      newUserPasswordInput.focus();
    }
    return;
  }
  const selectedRole = newUserRoleSelect?.value || DEFAULT_NEW_USER_ROLE;
  const role = USER_ROLE_OPTIONS.some((option) => option.value === selectedRole)
    ? selectedRole
    : DEFAULT_NEW_USER_ROLE;
  const submitButton = createUserForm?.querySelector('button[type="submit"]');
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.dataset.loading = 'true';
  }
  try {
    await apiFetch('/users', {
      method: 'POST',
      body: {
        username,
        full_name: fullName,
        password,
        role,
      },
    });
    showToast('Usuario creado correctamente.', 'success');
    resetCreateUserForm();
    if (newUserUsernameInput) {
      newUserUsernameInput.focus();
    }
    await loadUsers();
    if (role === 'sastre') {
      await loadTailors();
    } else if (role === 'vendedor') {
      await loadVendors();
    }
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    if (submitButton) {
      delete submitButton.dataset.loading;
      submitButton.disabled = state.user?.role !== 'administrador';
    }
    updateUserCreationForm();
  }
}

async function handleEditUserSubmit(event) {
  event.preventDefault();
  if (!state.user || state.user.role !== 'administrador') {
    showToast('Solo los administradores pueden editar usuarios.', 'error');
    return;
  }
  const editingId = state.editingUserId;
  if (!editingId) {
    showToast('Selecciona un usuario para editar.', 'error');
    return;
  }
  const editingUser = state.users.find((user) => user.id === editingId);
  if (!editingUser) {
    showToast('El usuario seleccionado ya no está disponible.', 'error');
    cancelUserEdit();
    return;
  }
  const fullName = editUserFullNameInput?.value?.trim() || '';
  if (!fullName) {
    showToast('Ingresa el nombre completo.', 'error');
    editUserFullNameInput?.focus();
    return;
  }
  const selectedRole = editUserRoleSelect?.value || editingUser.role;
  const normalizedRole = USER_ROLE_OPTIONS.some((option) => option.value === selectedRole)
    ? selectedRole
    : editingUser.role;
  const passwordRaw = editUserPasswordInput?.value || '';
  const password = passwordRaw.trim();
  const payload = {};
  if (fullName !== (editingUser.full_name || '')) {
    payload.full_name = fullName;
  }
  if (normalizedRole && normalizedRole !== editingUser.role) {
    payload.role = normalizedRole;
  }
  if (password) {
    payload.password = password;
  }
  if (!Object.keys(payload).length) {
    showToast('No hay cambios para guardar.', 'info');
    return;
  }
  const submitButton = editUserForm?.querySelector('button[type="submit"]');
  if (submitButton) {
    submitButton.disabled = true;
    submitButton.dataset.loading = 'true';
  }
  const previousRole = editingUser.role;
  try {
    await apiFetch(`/users/${editingUser.id}`, {
      method: 'PATCH',
      body: payload,
    });
    showToast('Usuario actualizado correctamente.', 'success');
    cancelUserEdit({ focusTable: false });
    await loadUsers();
    const updatedUser = state.users.find((user) => user.id === editingUser.id);
    const updatedRole = updatedUser?.role || payload.role || previousRole;
    if (previousRole !== updatedRole) {
      if (previousRole === 'sastre' || updatedRole === 'sastre') {
        await loadTailors();
      }
      if (previousRole === 'vendedor' || updatedRole === 'vendedor') {
        await loadVendors();
      }
    }
  } catch (error) {
    showToast(error.message, 'error');
    updateUserEditForm();
  } finally {
    if (submitButton) {
      delete submitButton.dataset.loading;
      submitButton.disabled = state.user?.role !== 'administrador';
    }
    if (editUserPasswordInput) {
      editUserPasswordInput.value = '';
    }
  }
}


function updateContificoStatus(element, { text = '', tone = 'info' } = {}) {
  if (!element) return;
  element.textContent = text;
  element.classList.remove('loading', 'error', 'success');
  if (tone === 'loading') {
    element.classList.add('loading');
    element.setAttribute('aria-live', 'polite');
  } else if (tone === 'error') {
    element.classList.add('error');
    element.setAttribute('aria-live', 'assertive');
  } else if (tone === 'success') {
    element.classList.add('success');
    element.setAttribute('aria-live', 'polite');
  } else {
    element.setAttribute('aria-live', 'polite');
  }
}

function resetContificoPreviewState() {
  state.contificoPreviewProducts = [];
  state.contificoPreviewProductsPage = 1;
  state.contificoPreviewProductsPageSize = CONTIFICO_DEFAULT_PAGE_SIZE;
  state.contificoPreviewProductsLoading = false;
  state.contificoPreviewProductsError = null;
  state.contificoPreviewProductsFetched = false;
  state.contificoPreviewWarehouses = [];
  state.contificoPreviewWarehousesLoading = false;
  state.contificoPreviewWarehousesError = null;
  state.contificoPreviewWarehousesFetched = false;
  state.contificoPreviewCustomerInvoices = [];
  state.contificoPreviewCustomerInvoicesPage = 1;
  state.contificoPreviewCustomerInvoicesPageSize = CONTIFICO_DEFAULT_PAGE_SIZE;
  state.contificoPreviewCustomerInvoicesLoading = false;
  state.contificoPreviewCustomerInvoicesError = null;
  state.contificoPreviewCustomerInvoicesFetched = false;
  state.contificoPreviewCustomerInvoicesDocument = '';
  state.contificoPreviewCustomerInvoiceLookup = null;
  state.contificoPreviewCustomerInvoiceLookupLoading = false;
  state.contificoPreviewCustomerInvoiceLookupError = null;
  state.contificoPreviewCustomerInvoiceLookupFetched = false;
  state.contificoPreviewCustomerInvoiceLookupDocument = '';
  state.contificoPreviewCustomerInvoiceLookupNumber = '';
  state.contificoPreviewInvoiceLookup = null;
  state.contificoPreviewInvoiceLookupLoading = false;
  state.contificoPreviewInvoiceLookupError = null;
  state.contificoPreviewInvoiceLookupFetched = false;
  state.contificoPreviewInvoiceLookupNumber = '';
  state.contificoPreviewInvoiceLookupCustomerDocument = '';
  state.contificoPreviewInvoiceLookupProgress = 0;
  state.contificoPreviewInvoiceLookupStage = '';
  state.contificoPreviewInvoiceLookupMetadata = {};
  state.contificoPreviewInvoiceLookupJobId = null;
  if (state.contificoPreviewInvoiceLookupPollTimer !== null) {
    clearTimeout(state.contificoPreviewInvoiceLookupPollTimer);
    state.contificoPreviewInvoiceLookupPollTimer = null;
  }
  setContificoCustomerInvoicesVisible(false);
  setContificoInvoiceLookupVisible(false);
  renderContificoPreview();
}

function renderContificoPreviewProducts() {
  const isAdmin = state.token && state.user?.role === 'administrador';
  if (!isAdmin) {
    if (contificoPreviewProductsForm) {
      const elements = contificoPreviewProductsForm.querySelectorAll('input, button');
      elements.forEach((element) => {
        element.disabled = true;
      });
    }
    if (contificoPreviewProductsTableBody) {
      contificoPreviewProductsTableBody.innerHTML = '';
    }
    updateContificoStatus(contificoPreviewProductsStatus, {
      text: 'Inicia sesión como administrador para consultar productos en Contífico.',
      tone: 'info',
    });
    return;
  }

  if (contificoPreviewProductsForm) {
    const elements = contificoPreviewProductsForm.querySelectorAll('input, button');
    elements.forEach((element) => {
      element.disabled = state.contificoPreviewProductsLoading;
    });
  }

  if (contificoPreviewPageInput) {
    contificoPreviewPageInput.value = String(state.contificoPreviewProductsPage || 1);
  }
  if (contificoPreviewPageSizeInput) {
    contificoPreviewPageSizeInput.value = String(
      state.contificoPreviewProductsPageSize || CONTIFICO_DEFAULT_PAGE_SIZE
    );
  }

  if (contificoPreviewProductsTableBody) {
    contificoPreviewProductsTableBody.innerHTML = '';
    const products = Array.isArray(state.contificoPreviewProducts)
      ? state.contificoPreviewProducts
      : [];

    if (products.length) {
      products.forEach((product) => {
        const row = document.createElement('tr');

        const idCell = document.createElement('td');
        const productId = product?.id;
        idCell.textContent =
          productId === null || productId === undefined || productId === ''
            ? '—'
            : String(productId);
        idCell.dataset.label = 'ID';

        const codeCell = document.createElement('td');
        const productCode = product?.codigo;
        codeCell.textContent =
          productCode === null || productCode === undefined || productCode === ''
            ? '—'
            : String(productCode);
        codeCell.dataset.label = 'Código';

        const nameCell = document.createElement('td');
        const productName = product?.nombre || product?.descripcion;
        nameCell.textContent =
          productName === null || productName === undefined || productName === ''
            ? '—'
            : String(productName);
        nameCell.dataset.label = 'Nombre';

        const priceCell = document.createElement('td');
        priceCell.textContent = formatCurrencyUSD(product?.pvp1);
        priceCell.dataset.label = 'Precio base';

        row.appendChild(idCell);
        row.appendChild(codeCell);
        row.appendChild(nameCell);
        row.appendChild(priceCell);
        contificoPreviewProductsTableBody.appendChild(row);
      });
    } else if (
      state.contificoPreviewProductsFetched &&
      !state.contificoPreviewProductsLoading &&
      !state.contificoPreviewProductsError
    ) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 4;
      cell.className = 'muted';
      cell.textContent = 'No se recibieron productos para la página consultada.';
      row.appendChild(cell);
      contificoPreviewProductsTableBody.appendChild(row);
    }
  }

  let statusMessage = '';
  let tone = 'info';
  if (state.contificoPreviewProductsLoading) {
    statusMessage = 'Consultando productos en Contífico...';
    tone = 'loading';
  } else if (state.contificoPreviewProductsError) {
    statusMessage = state.contificoPreviewProductsError;
    tone = 'error';
  } else if (state.contificoPreviewProductsFetched) {
    if (state.contificoPreviewProducts.length) {
      statusMessage = `Se muestran ${state.contificoPreviewProducts.length} productos (página ${state.contificoPreviewProductsPage}).`;
      tone = 'success';
    } else {
      statusMessage = 'No se recibieron productos para la página consultada.';
    }
  } else {
    statusMessage = 'Define la página y presiona “Consultar productos” para obtener datos desde Contífico.';
  }
  updateContificoStatus(contificoPreviewProductsStatus, { text: statusMessage, tone });
}

function renderContificoPreviewWarehouses() {
  const isAdmin = state.token && state.user?.role === 'administrador';
  if (!isAdmin) {
    if (contificoPreviewWarehousesButton) {
      contificoPreviewWarehousesButton.disabled = true;
      contificoPreviewWarehousesButton.removeAttribute('aria-busy');
      contificoPreviewWarehousesButton.textContent = 'Cargar bodegas';
    }
    if (contificoPreviewWarehousesTableBody) {
      contificoPreviewWarehousesTableBody.innerHTML = '';
    }
    updateContificoStatus(contificoPreviewWarehousesStatus, {
      text: 'Inicia sesión como administrador para consultar bodegas en Contífico.',
      tone: 'info',
    });
    return;
  }

  if (contificoPreviewWarehousesButton) {
    contificoPreviewWarehousesButton.disabled = state.contificoPreviewWarehousesLoading;
    if (state.contificoPreviewWarehousesLoading) {
      contificoPreviewWarehousesButton.setAttribute('aria-busy', 'true');
      contificoPreviewWarehousesButton.textContent = 'Consultando…';
    } else {
      contificoPreviewWarehousesButton.removeAttribute('aria-busy');
      contificoPreviewWarehousesButton.textContent = 'Cargar bodegas';
    }
  }

  if (contificoPreviewWarehousesTableBody) {
    contificoPreviewWarehousesTableBody.innerHTML = '';
    const warehouses = Array.isArray(state.contificoPreviewWarehouses)
      ? state.contificoPreviewWarehouses
      : [];

    if (warehouses.length) {
      warehouses.forEach((warehouse) => {
        const row = document.createElement('tr');

        const idCell = document.createElement('td');
        const warehouseId = warehouse?.id;
        idCell.textContent =
          warehouseId === null || warehouseId === undefined || warehouseId === ''
            ? '—'
            : String(warehouseId);
        idCell.dataset.label = 'ID';

        const codeCell = document.createElement('td');
        const warehouseCode = warehouse?.codigo;
        codeCell.textContent =
          warehouseCode === null || warehouseCode === undefined || warehouseCode === ''
            ? '—'
            : String(warehouseCode);
        codeCell.dataset.label = 'Código';

        const nameCell = document.createElement('td');
        const warehouseName = warehouse?.nombre || warehouse?.descripcion;
        nameCell.textContent =
          warehouseName === null || warehouseName === undefined || warehouseName === ''
            ? '—'
            : String(warehouseName);
        nameCell.dataset.label = 'Nombre';

        const addressCell = document.createElement('td');
        const warehouseAddress = warehouse?.direccion;
        addressCell.textContent =
          warehouseAddress === null || warehouseAddress === undefined || warehouseAddress === ''
            ? '—'
            : String(warehouseAddress);
        addressCell.dataset.label = 'Dirección';

        row.appendChild(idCell);
        row.appendChild(codeCell);
        row.appendChild(nameCell);
        row.appendChild(addressCell);
        contificoPreviewWarehousesTableBody.appendChild(row);
      });
    } else if (
      state.contificoPreviewWarehousesFetched &&
      !state.contificoPreviewWarehousesLoading &&
      !state.contificoPreviewWarehousesError
    ) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 4;
      cell.className = 'muted';
      cell.textContent = 'No se encontraron bodegas configuradas en Contífico.';
      row.appendChild(cell);
      contificoPreviewWarehousesTableBody.appendChild(row);
    }
  }

  let statusMessage = '';
  let tone = 'info';
  if (state.contificoPreviewWarehousesLoading) {
    statusMessage = 'Consultando bodegas en Contífico...';
    tone = 'loading';
  } else if (state.contificoPreviewWarehousesError) {
    statusMessage = state.contificoPreviewWarehousesError;
    tone = 'error';
  } else if (state.contificoPreviewWarehousesFetched) {
    if (state.contificoPreviewWarehouses.length) {
      statusMessage = `Se muestran ${state.contificoPreviewWarehouses.length} bodegas.`;
      tone = 'success';
    } else {
      statusMessage = 'No se encontraron bodegas configuradas en Contífico.';
    }
  } else {
    statusMessage = 'Haz clic en “Cargar bodegas” para consultar la API de Contífico.';
  }
  updateContificoStatus(contificoPreviewWarehousesStatus, { text: statusMessage, tone });
}

function renderContificoPreviewCustomerInvoices() {
  const isAdmin = state.token && state.user?.role === 'administrador';
  if (!isAdmin) {
    if (contificoCustomerInvoicesForm) {
      const elements = contificoCustomerInvoicesForm.querySelectorAll('input, button');
      elements.forEach((element) => {
        element.disabled = true;
      });
    }
    if (contificoCustomerInvoicesDocumentInput) {
      contificoCustomerInvoicesDocumentInput.value = '';
    }
    if (contificoCustomerInvoicesPageInput) {
      contificoCustomerInvoicesPageInput.value = '1';
    }
    if (contificoCustomerInvoicesPageSizeInput) {
      contificoCustomerInvoicesPageSizeInput.value = String(CONTIFICO_DEFAULT_PAGE_SIZE);
    }
    if (contificoCustomerInvoicesModalTableBody) {
      contificoCustomerInvoicesModalTableBody.innerHTML = '';
    }
    if (contificoCustomerInvoicesModalButton) {
      contificoCustomerInvoicesModalButton.classList.add('hidden');
      contificoCustomerInvoicesModalButton.setAttribute('aria-hidden', 'true');
    }
    setContificoCustomerInvoicesVisible(false);
    updateContificoStatus(contificoCustomerInvoicesStatus, {
      text: 'Inicia sesión como administrador para consultar facturas en Contífico.',
      tone: 'info',
    });
    updateContificoStatus(contificoCustomerInvoicesModalStatus, {
      text: 'Debes autenticarte como administrador para ver los resultados de Contífico.',
      tone: 'info',
    });
    return;
  }

  if (contificoCustomerInvoicesForm) {
    const elements = contificoCustomerInvoicesForm.querySelectorAll('input, button');
    elements.forEach((element) => {
      element.disabled = state.contificoPreviewCustomerInvoicesLoading;
    });
  }

  if (contificoCustomerInvoicesDocumentInput) {
    contificoCustomerInvoicesDocumentInput.value = state.contificoPreviewCustomerInvoicesDocument || '';
  }
  if (contificoCustomerInvoicesPageInput) {
    contificoCustomerInvoicesPageInput.value = String(
      state.contificoPreviewCustomerInvoicesPage || 1
    );
  }
  if (contificoCustomerInvoicesPageSizeInput) {
    contificoCustomerInvoicesPageSizeInput.value = String(
      state.contificoPreviewCustomerInvoicesPageSize || CONTIFICO_DEFAULT_PAGE_SIZE
    );
  }

  const invoices = Array.isArray(state.contificoPreviewCustomerInvoices)
    ? state.contificoPreviewCustomerInvoices
    : [];

  if (contificoCustomerInvoicesModalTableBody) {
    contificoCustomerInvoicesModalTableBody.innerHTML = '';
    if (invoices.length) {
      invoices.forEach((invoice) => {
        const row = document.createElement('tr');

        const numberCell = document.createElement('td');
        numberCell.textContent = invoice?.numero ? String(invoice.numero) : '—';
        numberCell.dataset.label = 'Número';

        const clientCell = document.createElement('td');
        clientCell.textContent = invoice?.cliente ? String(invoice.cliente) : '—';
        clientCell.dataset.label = 'Cliente';

        const idCell = document.createElement('td');
        idCell.textContent = invoice?.identificacion ? String(invoice.identificacion) : '—';
        idCell.dataset.label = 'Documento';

        const dateCell = document.createElement('td');
        dateCell.textContent = invoice?.fecha_emision ? String(invoice.fecha_emision) : '—';
        dateCell.dataset.label = 'Fecha';

        const statusCell = document.createElement('td');
        statusCell.textContent = invoice?.estado ? String(invoice.estado) : '—';
        statusCell.dataset.label = 'Estado';

        const totalCell = document.createElement('td');
        const totalValue =
          typeof invoice?.total === 'number' && Number.isFinite(invoice.total)
            ? invoice.total.toFixed(2)
            : null;
        totalCell.textContent = totalValue ?? '—';
        totalCell.dataset.label = 'Total';

        const rawCell = document.createElement('td');
        rawCell.dataset.label = 'Detalle';
        const detailsElement = document.createElement('details');
        detailsElement.className = 'contifico-invoice-raw';
        const summaryElement = document.createElement('summary');
        summaryElement.textContent = 'Ver JSON';
        const preElement = document.createElement('pre');
        preElement.textContent = JSON.stringify(invoice?.raw ?? invoice, null, 2);
        detailsElement.appendChild(summaryElement);
        detailsElement.appendChild(preElement);
        rawCell.appendChild(detailsElement);

        row.appendChild(numberCell);
        row.appendChild(clientCell);
        row.appendChild(idCell);
        row.appendChild(dateCell);
        row.appendChild(statusCell);
        row.appendChild(totalCell);
        row.appendChild(rawCell);

        contificoCustomerInvoicesModalTableBody.appendChild(row);
      });
    } else if (
      state.contificoPreviewCustomerInvoicesError &&
      !state.contificoPreviewCustomerInvoicesLoading
    ) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 7;
      cell.className = 'error';
      cell.textContent = state.contificoPreviewCustomerInvoicesError;
      row.appendChild(cell);
      contificoCustomerInvoicesModalTableBody.appendChild(row);
    } else if (
      state.contificoPreviewCustomerInvoicesFetched &&
      !state.contificoPreviewCustomerInvoicesLoading &&
      !state.contificoPreviewCustomerInvoicesError
    ) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 7;
      cell.textContent = 'No se encontraron facturas para el documento consultado.';
      cell.className = 'muted';
      row.appendChild(cell);
      contificoCustomerInvoicesModalTableBody.appendChild(row);
    }
  }

  if (contificoCustomerInvoicesModalButton) {
    const shouldShowModalButton =
      state.contificoPreviewCustomerInvoicesLoading ||
      state.contificoPreviewCustomerInvoicesError ||
      (state.contificoPreviewCustomerInvoicesFetched &&
        (invoices.length > 0 || state.contificoPreviewCustomerInvoicesDocument));
    contificoCustomerInvoicesModalButton.classList.toggle('hidden', !shouldShowModalButton);
    contificoCustomerInvoicesModalButton.setAttribute(
      'aria-hidden',
      shouldShowModalButton ? 'false' : 'true'
    );
  }

  let statusMessage = '';
  let tone = 'info';
  if (state.contificoPreviewCustomerInvoicesLoading) {
    statusMessage = 'Consultando facturas en Contífico. La ventana de resultados se abrirá automáticamente.';
    tone = 'loading';
  } else if (state.contificoPreviewCustomerInvoicesError) {
    statusMessage = state.contificoPreviewCustomerInvoicesError;
    tone = 'error';
  } else if (state.contificoPreviewCustomerInvoicesFetched) {
    if (state.contificoPreviewCustomerInvoices.length) {
      statusMessage = `Se cargaron ${state.contificoPreviewCustomerInvoices.length} facturas. Usa “Ver resultados” para revisarlas.`;
      tone = 'success';
    } else if (state.contificoPreviewCustomerInvoicesDocument) {
      statusMessage = `No se encontraron facturas para ${state.contificoPreviewCustomerInvoicesDocument}.`;
    } else {
      statusMessage = 'No se encontraron facturas con los filtros seleccionados.';
    }
  } else {
    statusMessage = 'Ingresa un número de documento para consultar facturas del cliente en Contífico.';
  }
  updateContificoStatus(contificoCustomerInvoicesStatus, { text: statusMessage, tone });

  let modalStatusMessage = '';
  let modalTone = 'info';
  if (state.contificoPreviewCustomerInvoicesLoading) {
    modalStatusMessage = 'Consultando facturas en Contífico...';
    modalTone = 'loading';
  } else if (state.contificoPreviewCustomerInvoicesError) {
    modalStatusMessage = state.contificoPreviewCustomerInvoicesError;
    modalTone = 'error';
  } else if (state.contificoPreviewCustomerInvoicesFetched) {
    if (invoices.length) {
      modalStatusMessage = `Se muestran ${invoices.length} facturas.`;
      modalTone = 'success';
    } else if (state.contificoPreviewCustomerInvoicesDocument) {
      modalStatusMessage = `No se encontraron facturas para ${state.contificoPreviewCustomerInvoicesDocument}.`;
    } else {
      modalStatusMessage = 'No se encontraron facturas con los filtros seleccionados.';
    }
  } else {
    modalStatusMessage = 'Usa el formulario para consultar las facturas del cliente.';
  }
  updateContificoStatus(contificoCustomerInvoicesModalStatus, {
    text: modalStatusMessage,
    tone: modalTone,
  });
}

function renderContificoPreviewCustomerInvoiceLookup() {
  const isAdmin = state.token && state.user?.role === 'administrador';
  if (contificoCustomerInvoiceLookupForm) {
    const elements = contificoCustomerInvoiceLookupForm.querySelectorAll('input, button');
    elements.forEach((element) => {
      element.disabled = !isAdmin || state.contificoPreviewCustomerInvoiceLookupLoading;
    });
  }

  if (!isAdmin) {
    if (contificoCustomerInvoiceLookupDocumentInput) {
      contificoCustomerInvoiceLookupDocumentInput.value = '';
    }
    if (contificoCustomerInvoiceLookupNumberInput) {
      contificoCustomerInvoiceLookupNumberInput.value = '';
    }
    if (contificoCustomerInvoiceLookupResult) {
      contificoCustomerInvoiceLookupResult.innerHTML = '';
      contificoCustomerInvoiceLookupResult.classList.add('empty');
    }
    updateContificoStatus(contificoCustomerInvoiceLookupStatus, {
      text: 'Autentícate como administrador para consultar facturas puntuales por cliente.',
      tone: 'info',
    });
    return;
  }

  if (contificoCustomerInvoiceLookupDocumentInput) {
    contificoCustomerInvoiceLookupDocumentInput.value =
      state.contificoPreviewCustomerInvoiceLookupDocument || '';
  }
  if (contificoCustomerInvoiceLookupNumberInput) {
    contificoCustomerInvoiceLookupNumberInput.value =
      state.contificoPreviewCustomerInvoiceLookupNumber || '';
  }

  const invoice = state.contificoPreviewCustomerInvoiceLookup;
  const loading = state.contificoPreviewCustomerInvoiceLookupLoading;
  const error = state.contificoPreviewCustomerInvoiceLookupError;
  const fetched = state.contificoPreviewCustomerInvoiceLookupFetched;

  let statusMessage = '';
  let tone = 'info';
  if (loading) {
    statusMessage = 'Buscando factura para el cliente en Contífico...';
    tone = 'loading';
  } else if (error) {
    statusMessage = error;
    tone = 'error';
  } else if (fetched) {
    if (invoice) {
      statusMessage = 'Factura encontrada. Revisa el detalle debajo.';
      tone = 'success';
    } else if (
      state.contificoPreviewCustomerInvoiceLookupDocument ||
      state.contificoPreviewCustomerInvoiceLookupNumber
    ) {
      statusMessage = 'No se encontraron resultados con los datos proporcionados.';
    } else {
      statusMessage = 'No se encontraron resultados con los datos proporcionados.';
    }
  } else {
    statusMessage =
      'Ingresa el documento del cliente y el número de factura para validar los datos en Contífico.';
  }
  updateContificoStatus(contificoCustomerInvoiceLookupStatus, { text: statusMessage, tone });

  if (contificoCustomerInvoiceLookupResult) {
    contificoCustomerInvoiceLookupResult.innerHTML = '';
    let hasContent = false;

    if (!loading && !error && invoice) {
      const list = document.createElement('dl');
      list.className = 'contifico-invoice-detail-list';

      const appendItem = (label, value) => {
        const term = document.createElement('dt');
        term.textContent = label;
        const description = document.createElement('dd');
        description.textContent = value ?? '—';
        list.appendChild(term);
        list.appendChild(description);
      };

      appendItem('Documento', invoice.numero ? String(invoice.numero) : '—');
      appendItem('Cliente', invoice.cliente ? String(invoice.cliente) : '—');
      appendItem(
        'Identificación',
        invoice.identificacion ? String(invoice.identificacion) : '—'
      );
      appendItem(
        'Fecha de emisión',
        invoice.fecha_emision ? String(invoice.fecha_emision) : '—'
      );
      appendItem('Estado', invoice.estado ? String(invoice.estado) : '—');
      appendItem(
        'Total',
        typeof invoice.total === 'number' && Number.isFinite(invoice.total)
          ? invoice.total.toFixed(2)
          : '—'
      );

      const rawDetails = document.createElement('details');
      rawDetails.className = 'contifico-invoice-raw';
      const summary = document.createElement('summary');
      summary.textContent = 'Ver respuesta completa';
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(invoice.raw ?? invoice, null, 2);
      rawDetails.appendChild(summary);
      rawDetails.appendChild(pre);

      contificoCustomerInvoiceLookupResult.appendChild(list);
      contificoCustomerInvoiceLookupResult.appendChild(rawDetails);
      hasContent = true;
    } else if (!loading && !error && fetched) {
      const emptyParagraph = document.createElement('p');
      emptyParagraph.className = 'muted';
      emptyParagraph.textContent =
        'No se encontró una factura que coincida con el cliente y número proporcionados.';
      contificoCustomerInvoiceLookupResult.appendChild(emptyParagraph);
      hasContent = true;
    }

    contificoCustomerInvoiceLookupResult.classList.toggle('empty', !hasContent);
  }
}

function renderContificoPreviewInvoiceLookup() {
  const isAdmin = state.token && state.user?.role === 'administrador';
  if (!isAdmin) {
    if (contificoInvoiceLookupForm) {
      const elements = contificoInvoiceLookupForm.querySelectorAll('input, button');
      elements.forEach((element) => {
        element.disabled = true;
      });
    }
    if (contificoInvoiceLookupDocumentInput) {
      contificoInvoiceLookupDocumentInput.value = '';
    }
    if (contificoInvoiceLookupNumberInput) {
      contificoInvoiceLookupNumberInput.value = '';
    }
    if (contificoInvoiceLookupModalButton) {
      contificoInvoiceLookupModalButton.classList.add('hidden');
      contificoInvoiceLookupModalButton.setAttribute('aria-hidden', 'true');
    }
    if (contificoInvoiceLookupModalDetails) {
      contificoInvoiceLookupModalDetails.innerHTML = '';
    }
    if (contificoInvoiceLookupProgress) {
      contificoInvoiceLookupProgress.classList.add('hidden');
      contificoInvoiceLookupProgress.setAttribute('aria-hidden', 'true');
    }
    if (contificoInvoiceLookupProgressBar) {
      contificoInvoiceLookupProgressBar.style.width = '0%';
      contificoInvoiceLookupProgressBar.setAttribute('aria-valuenow', '0');
    }
    if (contificoInvoiceLookupProgressLabel) {
      contificoInvoiceLookupProgressLabel.textContent = '';
    }
    setContificoInvoiceLookupVisible(false);
    updateContificoStatus(contificoInvoiceLookupStatus, {
      text: 'Inicia sesión como administrador para buscar facturas puntuales.',
      tone: 'info',
    });
    updateContificoStatus(contificoInvoiceLookupModalStatus, {
      text: 'Autentícate como administrador para revisar el detalle de Contífico.',
      tone: 'info',
    });
    return;
  }

  if (contificoInvoiceLookupForm) {
    const elements = contificoInvoiceLookupForm.querySelectorAll('input, button');
    elements.forEach((element) => {
      element.disabled = state.contificoPreviewInvoiceLookupLoading;
    });
  }

  if (contificoInvoiceLookupDocumentInput) {
    contificoInvoiceLookupDocumentInput.value =
      state.contificoPreviewInvoiceLookupCustomerDocument || '';
  }
  if (contificoInvoiceLookupNumberInput) {
    contificoInvoiceLookupNumberInput.value = state.contificoPreviewInvoiceLookupNumber || '';
  }

  const invoice = state.contificoPreviewInvoiceLookup;
  const stageDescription = describeInvoiceLookupStage(
    state.contificoPreviewInvoiceLookupStage,
    state.contificoPreviewInvoiceLookupMetadata
  );
  const progressValue = Number.isFinite(state.contificoPreviewInvoiceLookupProgress)
    ? Math.max(0, Math.min(100, Math.round(state.contificoPreviewInvoiceLookupProgress)))
    : 0;
  const shouldShowProgress =
    state.contificoPreviewInvoiceLookupLoading ||
    (progressValue > 0 &&
      (state.contificoPreviewInvoiceLookupFetched ||
        Boolean(stageDescription) ||
        Boolean(state.contificoPreviewInvoiceLookupStage)));

  if (contificoInvoiceLookupProgress) {
    contificoInvoiceLookupProgress.classList.toggle('hidden', !shouldShowProgress);
    contificoInvoiceLookupProgress.setAttribute('aria-hidden', shouldShowProgress ? 'false' : 'true');
  }
  if (contificoInvoiceLookupProgressBar) {
    contificoInvoiceLookupProgressBar.style.width = `${progressValue}%`;
    contificoInvoiceLookupProgressBar.setAttribute('aria-valuenow', String(progressValue));
  }
  if (contificoInvoiceLookupProgressLabel) {
    contificoInvoiceLookupProgressLabel.textContent = shouldShowProgress
      ? stageDescription || 'Procesando búsqueda en Contífico...'
      : '';
  }

  if (contificoInvoiceLookupModalDetails) {
    contificoInvoiceLookupModalDetails.innerHTML = '';
    if (state.contificoPreviewInvoiceLookupError) {
      const errorParagraph = document.createElement('p');
      errorParagraph.className = 'error';
      errorParagraph.textContent = state.contificoPreviewInvoiceLookupError;
      contificoInvoiceLookupModalDetails.appendChild(errorParagraph);
    } else if (
      invoice &&
      !state.contificoPreviewInvoiceLookupLoading &&
      !state.contificoPreviewInvoiceLookupError
    ) {
      const list = document.createElement('dl');
      list.className = 'contifico-invoice-detail-list';

      const appendItem = (label, value) => {
        const term = document.createElement('dt');
        term.textContent = label;
        const description = document.createElement('dd');
        description.textContent = value ?? '—';
        list.appendChild(term);
        list.appendChild(description);
      };

      appendItem('Documento', invoice.numero ? String(invoice.numero) : '—');
      appendItem('Cliente', invoice.cliente ? String(invoice.cliente) : '—');
      appendItem('Identificación', invoice.identificacion ? String(invoice.identificacion) : '—');
      appendItem('Fecha de emisión', invoice.fecha_emision ? String(invoice.fecha_emision) : '—');
      appendItem('Estado', invoice.estado ? String(invoice.estado) : '—');
      appendItem(
        'Total',
        typeof invoice.total === 'number' && Number.isFinite(invoice.total)
          ? invoice.total.toFixed(2)
          : '—'
      );

      const rawDetails = document.createElement('details');
      rawDetails.className = 'contifico-invoice-raw';
      const summary = document.createElement('summary');
      summary.textContent = 'Ver respuesta completa';
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(invoice.raw ?? invoice, null, 2);
      rawDetails.appendChild(summary);
      rawDetails.appendChild(pre);

      contificoInvoiceLookupModalDetails.appendChild(list);
      contificoInvoiceLookupModalDetails.appendChild(rawDetails);
    } else if (state.contificoPreviewInvoiceLookupFetched) {
      const emptyParagraph = document.createElement('p');
      emptyParagraph.className = 'muted';
      emptyParagraph.textContent = 'No se encontraron facturas con el número consultado.';
      contificoInvoiceLookupModalDetails.appendChild(emptyParagraph);
    } else {
      const promptParagraph = document.createElement('p');
      promptParagraph.className = 'muted';
      promptParagraph.textContent =
        'Completa el formulario con el documento del cliente y el número de factura para ver el detalle en esta ventana.';
      contificoInvoiceLookupModalDetails.appendChild(promptParagraph);
    }
  }

  if (contificoInvoiceLookupModalButton) {
    const shouldShowLookupButton =
      state.contificoPreviewInvoiceLookupLoading ||
      state.contificoPreviewInvoiceLookupError ||
      (state.contificoPreviewInvoiceLookupFetched &&
        (Boolean(invoice) || Boolean(state.contificoPreviewInvoiceLookupNumber)));
    contificoInvoiceLookupModalButton.classList.toggle('hidden', !shouldShowLookupButton);
    contificoInvoiceLookupModalButton.setAttribute(
      'aria-hidden',
      shouldShowLookupButton ? 'false' : 'true'
    );
  }

  let statusMessage = '';
  let tone = 'info';
  if (state.contificoPreviewInvoiceLookupLoading) {
    statusMessage =
      stageDescription ||
      'Buscando factura en Contífico. La ventana de detalle se abrirá automáticamente.';
    tone = 'loading';
  } else if (state.contificoPreviewInvoiceLookupError) {
    statusMessage = state.contificoPreviewInvoiceLookupError;
    tone = 'error';
  } else if (state.contificoPreviewInvoiceLookupFetched) {
    if (invoice) {
      statusMessage = 'Factura encontrada. Usa “Ver detalle” para revisarla.';
      tone = 'success';
    } else if (stageDescription) {
      statusMessage = stageDescription;
    } else {
      statusMessage = 'No se encontraron facturas con el número consultado.';
    }
  } else {
    statusMessage =
      'Ingresa el documento del cliente y el número exacto de la factura para iniciar la búsqueda.';
  }
  updateContificoStatus(contificoInvoiceLookupStatus, { text: statusMessage, tone });

  let modalStatusMessage = '';
  let modalTone = 'info';
  if (state.contificoPreviewInvoiceLookupLoading) {
    modalStatusMessage = stageDescription || 'Buscando factura en Contífico...';
    modalTone = 'loading';
  } else if (state.contificoPreviewInvoiceLookupError) {
    modalStatusMessage = state.contificoPreviewInvoiceLookupError;
    modalTone = 'error';
  } else if (state.contificoPreviewInvoiceLookupFetched) {
    if (invoice) {
      modalStatusMessage = 'Factura encontrada correctamente.';
      modalTone = 'success';
    } else if (stageDescription) {
      modalStatusMessage = stageDescription;
    } else {
      modalStatusMessage = 'No se encontraron facturas con el número consultado.';
    }
  } else {
    modalStatusMessage = 'Introduce un número de documento para iniciar la búsqueda.';
  }
  updateContificoStatus(contificoInvoiceLookupModalStatus, {
    text: modalStatusMessage,
    tone: modalTone,
  });
}
function renderContificoPreview() {
  renderContificoPreviewProducts();
  renderContificoPreviewWarehouses();
  renderContificoPreviewCustomerInvoices();
  renderContificoPreviewCustomerInvoiceLookup();
  renderContificoPreviewInvoiceLookup();
}

async function handleContificoPreviewProductsFetch(event) {
  if (event) {
    event.preventDefault();
  }
  if (!state.token || !state.user || state.user.role !== 'administrador') {
    showToast('Solo los administradores pueden consultar Contífico.', 'error');
    return;
  }
  if (state.contificoPreviewProductsLoading) {
    return;
  }

  const rawPage = Number(contificoPreviewPageInput?.value ?? state.contificoPreviewProductsPage ?? 1);
  const rawPageSize = Number(
    contificoPreviewPageSizeInput?.value ??
      state.contificoPreviewProductsPageSize ??
      CONTIFICO_DEFAULT_PAGE_SIZE
  );
  const normalizedPage = Number.isFinite(rawPage) && rawPage > 0 ? Math.floor(rawPage) : 1;
  const normalizedPageSize = Number.isFinite(rawPageSize) && rawPageSize > 0
    ? Math.min(Math.floor(rawPageSize), CONTIFICO_MAX_PAGE_SIZE)
    : CONTIFICO_DEFAULT_PAGE_SIZE;

  state.contificoPreviewProductsPage = normalizedPage;
  state.contificoPreviewProductsPageSize = normalizedPageSize;
  state.contificoPreviewProductsLoading = true;
  state.contificoPreviewProductsError = null;
  renderContificoPreviewProducts();

  try {
    const response = await apiFetch(
      `/temp/contifico/products?page=${normalizedPage}&page_size=${normalizedPageSize}`
    );
    const items = Array.isArray(response?.items) ? response.items : [];
    state.contificoPreviewProducts = items;
    state.contificoPreviewProductsPage = Number.isFinite(response?.page)
      ? response.page
      : normalizedPage;
    state.contificoPreviewProductsPageSize = Number.isFinite(response?.page_size)
      ? response.page_size
      : normalizedPageSize;
    state.contificoPreviewProductsFetched = true;
    renderContificoPreviewProducts();
  } catch (error) {
    state.contificoPreviewProductsError = error.message || 'No se pudieron consultar los productos.';
    state.contificoPreviewProducts = [];
    state.contificoPreviewProductsFetched = true;
    renderContificoPreviewProducts();
    showToast(state.contificoPreviewProductsError, 'error');
  } finally {
    state.contificoPreviewProductsLoading = false;
    renderContificoPreviewProducts();
  }
}

async function handleContificoPreviewWarehousesFetch() {
  if (!state.token || !state.user || state.user.role !== 'administrador') {
    showToast('Solo los administradores pueden consultar Contífico.', 'error');
    return;
  }
  if (state.contificoPreviewWarehousesLoading) {
    return;
  }

  state.contificoPreviewWarehousesLoading = true;
  state.contificoPreviewWarehousesError = null;
  renderContificoPreviewWarehouses();

  try {
    const response = await apiFetch('/temp/contifico/warehouses');
    state.contificoPreviewWarehouses = Array.isArray(response) ? response : [];
    state.contificoPreviewWarehousesFetched = true;
    renderContificoPreviewWarehouses();
  } catch (error) {
    state.contificoPreviewWarehousesError = error.message || 'No se pudieron consultar las bodegas.';
    state.contificoPreviewWarehouses = [];
    state.contificoPreviewWarehousesFetched = true;
    renderContificoPreviewWarehouses();
    showToast(state.contificoPreviewWarehousesError, 'error');
  } finally {
    state.contificoPreviewWarehousesLoading = false;
    renderContificoPreviewWarehouses();
  }
}

async function handleContificoCustomerInvoicesFetch(event) {
  if (event) {
    event.preventDefault();
  }
  if (!state.token || !state.user || state.user.role !== 'administrador') {
    showToast('Solo los administradores pueden consultar Contífico.', 'error');
    return;
  }
  if (state.contificoPreviewCustomerInvoicesLoading) {
    return;
  }

  const rawDocument =
    contificoCustomerInvoicesDocumentInput?.value ?? state.contificoPreviewCustomerInvoicesDocument ?? '';
  const normalizedDocument = String(rawDocument).trim();

  if (!normalizedDocument) {
    state.contificoPreviewCustomerInvoicesError = 'Ingresa un número de documento válido.';
    state.contificoPreviewCustomerInvoices = [];
    state.contificoPreviewCustomerInvoicesFetched = true;
    renderContificoPreviewCustomerInvoices();
    showToast(state.contificoPreviewCustomerInvoicesError, 'error');
    return;
  }

  const rawPage = Number(
    contificoCustomerInvoicesPageInput?.value ?? state.contificoPreviewCustomerInvoicesPage ?? 1
  );
  const rawPageSize = Number(
    contificoCustomerInvoicesPageSizeInput?.value ??
      state.contificoPreviewCustomerInvoicesPageSize ??
      CONTIFICO_DEFAULT_PAGE_SIZE
  );
  const normalizedPage = Number.isFinite(rawPage) && rawPage > 0 ? Math.floor(rawPage) : 1;
  const normalizedPageSize = Number.isFinite(rawPageSize) && rawPageSize > 0
    ? Math.min(Math.floor(rawPageSize), CONTIFICO_MAX_PAGE_SIZE)
    : CONTIFICO_DEFAULT_PAGE_SIZE;

  state.contificoPreviewCustomerInvoicesDocument = normalizedDocument;
  state.contificoPreviewCustomerInvoicesPage = normalizedPage;
  state.contificoPreviewCustomerInvoicesPageSize = normalizedPageSize;
  state.contificoPreviewCustomerInvoicesLoading = true;
  state.contificoPreviewCustomerInvoicesError = null;
  state.contificoPreviewCustomerInvoicesFetched = false;
  setContificoCustomerInvoicesVisible(true);
  renderContificoPreviewCustomerInvoices();

  try {
    const response = await apiFetch(
      `/temp/contifico/invoices/by-customer?document_id=${encodeURIComponent(
        normalizedDocument
      )}&page=${normalizedPage}&page_size=${normalizedPageSize}`
    );
    const items = Array.isArray(response?.items) ? response.items : [];
    state.contificoPreviewCustomerInvoices = items;
    state.contificoPreviewCustomerInvoicesPage = Number.isFinite(response?.page)
      ? response.page
      : normalizedPage;
    state.contificoPreviewCustomerInvoicesPageSize = Number.isFinite(response?.page_size)
      ? response.page_size
      : normalizedPageSize;
    state.contificoPreviewCustomerInvoicesFetched = true;
    renderContificoPreviewCustomerInvoices();
  } catch (error) {
    state.contificoPreviewCustomerInvoicesError =
      error.message || 'No se pudieron consultar las facturas.';
    state.contificoPreviewCustomerInvoices = [];
    state.contificoPreviewCustomerInvoicesFetched = true;
    renderContificoPreviewCustomerInvoices();
    showToast(state.contificoPreviewCustomerInvoicesError, 'error');
  } finally {
    state.contificoPreviewCustomerInvoicesLoading = false;
    renderContificoPreviewCustomerInvoices();
  }
}

async function handleContificoCustomerInvoiceLookup(event) {
  if (event) {
    event.preventDefault();
  }
  if (!state.token || !state.user || state.user.role !== 'administrador') {
    showToast('Solo los administradores pueden consultar Contífico.', 'error');
    return;
  }
  if (state.contificoPreviewCustomerInvoiceLookupLoading) {
    return;
  }

  const rawDocument =
    contificoCustomerInvoiceLookupDocumentInput?.value ??
    state.contificoPreviewCustomerInvoiceLookupDocument ??
    '';
  const normalizedDocument = String(rawDocument).trim();

  if (!normalizedDocument) {
    state.contificoPreviewCustomerInvoiceLookupError =
      'Ingresa un número de documento válido.';
    state.contificoPreviewCustomerInvoiceLookup = null;
    state.contificoPreviewCustomerInvoiceLookupFetched = true;
    renderContificoPreviewCustomerInvoiceLookup();
    showToast(state.contificoPreviewCustomerInvoiceLookupError, 'error');
    return;
  }

  const rawNumber =
    contificoCustomerInvoiceLookupNumberInput?.value ??
    state.contificoPreviewCustomerInvoiceLookupNumber ??
    '';
  const normalizedNumber = String(rawNumber).trim();

  if (!normalizedNumber) {
    state.contificoPreviewCustomerInvoiceLookupError =
      'Ingresa un número de factura válido.';
    state.contificoPreviewCustomerInvoiceLookup = null;
    state.contificoPreviewCustomerInvoiceLookupFetched = true;
    renderContificoPreviewCustomerInvoiceLookup();
    showToast(state.contificoPreviewCustomerInvoiceLookupError, 'error');
    return;
  }

  state.contificoPreviewCustomerInvoiceLookupDocument = normalizedDocument;
  state.contificoPreviewCustomerInvoiceLookupNumber = normalizedNumber;
  state.contificoPreviewCustomerInvoiceLookupLoading = true;
  state.contificoPreviewCustomerInvoiceLookupError = null;
  state.contificoPreviewCustomerInvoiceLookupFetched = false;
  state.contificoPreviewCustomerInvoiceLookup = null;
  renderContificoPreviewCustomerInvoiceLookup();

  try {
    const response = await apiFetch(
      `/temp/contifico/invoices/by-customer-and-number?customer_document=${encodeURIComponent(
        normalizedDocument
      )}&document_number=${encodeURIComponent(normalizedNumber)}`
    );
    state.contificoPreviewCustomerInvoiceLookup = response || null;
    state.contificoPreviewCustomerInvoiceLookupFetched = true;
    renderContificoPreviewCustomerInvoiceLookup();
    if (state.contificoPreviewCustomerInvoiceLookup) {
      showToast('Factura encontrada correctamente.', 'success');
    } else {
      showToast('No se encontraron resultados.', 'info');
    }
  } catch (error) {
    state.contificoPreviewCustomerInvoiceLookupError =
      error?.message || 'No se pudo consultar la factura solicitada.';
    state.contificoPreviewCustomerInvoiceLookup = null;
    state.contificoPreviewCustomerInvoiceLookupFetched = true;
    renderContificoPreviewCustomerInvoiceLookup();
    showToast(state.contificoPreviewCustomerInvoiceLookupError, 'error');
  } finally {
    state.contificoPreviewCustomerInvoiceLookupLoading = false;
    renderContificoPreviewCustomerInvoiceLookup();
  }
}

function cancelContificoInvoiceLookupPolling() {
  if (state.contificoPreviewInvoiceLookupPollTimer !== null) {
    clearTimeout(state.contificoPreviewInvoiceLookupPollTimer);
    state.contificoPreviewInvoiceLookupPollTimer = null;
  }
}

function scheduleContificoInvoiceLookupPoll(jobId, requestId, delay = 1000) {
  if (!jobId) {
    return;
  }
  cancelContificoInvoiceLookupPolling();
  state.contificoPreviewInvoiceLookupPollTimer = window.setTimeout(() => {
    pollContificoInvoiceLookupJob(jobId, requestId).catch((error) => {
      logInvoiceLookupError('Error inesperado al continuar con el sondeo de la factura puntual.', {
        requestId,
        jobId,
        message: error?.message || null,
      });
    });
  }, Math.max(250, delay));
}

function applyContificoInvoiceLookupJobUpdate(job, requestId) {
  if (!job || requestId !== state.contificoPreviewInvoiceLookupRequestId) {
    return job?.status || null;
  }

  state.contificoPreviewInvoiceLookupJobId = job.id || null;
  if (job.document_number) {
    state.contificoPreviewInvoiceLookupNumber = job.document_number;
  }
  if (job.customer_document) {
    state.contificoPreviewInvoiceLookupCustomerDocument = job.customer_document;
  }

  const progressValue = Number(job.progress);
  if (Number.isFinite(progressValue)) {
    const normalizedProgress = Math.max(0, Math.min(100, Math.round(progressValue)));
    state.contificoPreviewInvoiceLookupProgress = Math.max(
      state.contificoPreviewInvoiceLookupProgress || 0,
      normalizedProgress,
    );
  }

  state.contificoPreviewInvoiceLookupStage = job.stage || state.contificoPreviewInvoiceLookupStage || '';
  state.contificoPreviewInvoiceLookupMetadata =
    job.metadata && typeof job.metadata === 'object' ? { ...job.metadata } : {};

  const status = job.status || 'pending';
  if (status === 'completed') {
    state.contificoPreviewInvoiceLookup = job.result || null;
    state.contificoPreviewInvoiceLookupError = job.error || null;
    state.contificoPreviewInvoiceLookupLoading = false;
    state.contificoPreviewInvoiceLookupFetched = true;
  } else if (status === 'failed') {
    state.contificoPreviewInvoiceLookup = null;
    state.contificoPreviewInvoiceLookupError =
      job.error || 'No se pudo consultar la factura solicitada.';
    state.contificoPreviewInvoiceLookupLoading = false;
    state.contificoPreviewInvoiceLookupFetched = true;
  } else {
    if (job.result) {
      state.contificoPreviewInvoiceLookup = job.result;
    }
    state.contificoPreviewInvoiceLookupError = null;
    state.contificoPreviewInvoiceLookupLoading = true;
    state.contificoPreviewInvoiceLookupFetched = false;
  }

  return status;
}

async function pollContificoInvoiceLookupJob(jobId, requestId) {
  if (!jobId || requestId !== state.contificoPreviewInvoiceLookupRequestId) {
    return;
  }

  logInvoiceLookupInfo('Sondeando el estado de la búsqueda de factura puntual.', {
    requestId,
    jobId,
  });

  try {
    const job = await apiFetch(
      `/temp/contifico/invoices/by-number/jobs/${encodeURIComponent(jobId)}`
    );
    const status = applyContificoInvoiceLookupJobUpdate(job, requestId);
    renderContificoPreviewInvoiceLookup();

    if (status === 'pending' || status === 'running') {
      scheduleContificoInvoiceLookupPoll(jobId, requestId);
      return;
    }

    cancelContificoInvoiceLookupPolling();

    if (status === 'failed') {
      if (state.contificoPreviewInvoiceLookupError) {
        showToast(state.contificoPreviewInvoiceLookupError, 'error');
      }
    } else if (status === 'completed') {
      if (state.contificoPreviewInvoiceLookup) {
        showToast('Factura encontrada correctamente.', 'success');
      } else if (!state.contificoPreviewInvoiceLookupError) {
        showToast('La búsqueda finalizó sin resultados.', 'info');
      }
    }
  } catch (error) {
    if (requestId !== state.contificoPreviewInvoiceLookupRequestId) {
      return;
    }
    cancelContificoInvoiceLookupPolling();
    state.contificoPreviewInvoiceLookupLoading = false;
    state.contificoPreviewInvoiceLookupFetched = true;
    state.contificoPreviewInvoiceLookupError =
      error?.message || 'No se pudo obtener el estado de la búsqueda en Contífico.';
    logInvoiceLookupError('Error al sondear la búsqueda puntual en Contífico.', {
      requestId,
      jobId,
      message: error?.message || null,
    });
    renderContificoPreviewInvoiceLookup();
    showToast(state.contificoPreviewInvoiceLookupError, 'error');
  }
}

async function handleContificoInvoiceLookup(event) {
  if (event) {
    event.preventDefault();
  }
  logInvoiceLookupInfo('Formulario de búsqueda enviado.', { timestamp: Date.now() });
  if (!state.token || !state.user || state.user.role !== 'administrador') {
    logInvoiceLookupWarn('Búsqueda cancelada: el usuario no tiene permisos de administrador.', {
      hasToken: Boolean(state.token),
      role: state.user?.role || null,
    });
    showToast('Solo los administradores pueden consultar Contífico.', 'error');
    return;
  }
  if (state.contificoPreviewInvoiceLookupLoading) {
    logInvoiceLookupWarn('Se ignoró la búsqueda porque ya existe una consulta en curso.', {
      activeRequestId: state.contificoPreviewInvoiceLookupRequestId || null,
    });
    return;
  }

  const rawDocument =
    contificoInvoiceLookupDocumentInput?.value ??
    state.contificoPreviewInvoiceLookupCustomerDocument ??
    '';
  const normalizedDocument = String(rawDocument).trim();

  logInvoiceLookupInfo('Documento del cliente capturado del formulario.', {
    raw: rawDocument,
    normalized: normalizedDocument,
  });

  if (!normalizedDocument) {
    logInvoiceLookupWarn('Búsqueda cancelada por documento de cliente vacío.', {
      raw: rawDocument,
    });
    state.contificoPreviewInvoiceLookupError = 'Ingresa un documento de cliente válido.';
    state.contificoPreviewInvoiceLookup = null;
    state.contificoPreviewInvoiceLookupFetched = true;
    renderContificoPreviewInvoiceLookup();
    showToast(state.contificoPreviewInvoiceLookupError, 'error');
    return;
  }

  const rawNumber =
    contificoInvoiceLookupNumberInput?.value ?? state.contificoPreviewInvoiceLookupNumber ?? '';
  const normalizedNumber = String(rawNumber).trim();

  logInvoiceLookupInfo('Número capturado del formulario.', {
    raw: rawNumber,
    normalized: normalizedNumber,
  });

  if (!normalizedNumber) {
    logInvoiceLookupWarn('Búsqueda cancelada por número de documento vacío.', {
      raw: rawNumber,
    });
    state.contificoPreviewInvoiceLookupError = 'Ingresa un número de documento válido.';
    state.contificoPreviewInvoiceLookup = null;
    state.contificoPreviewInvoiceLookupFetched = true;
    renderContificoPreviewInvoiceLookup();
    showToast(state.contificoPreviewInvoiceLookupError, 'error');
    return;
  }

  const requestId = (state.contificoPreviewInvoiceLookupRequestId || 0) + 1;
  state.contificoPreviewInvoiceLookupRequestId = requestId;

  logInvoiceLookupInfo('Preparando consulta puntual en Contífico.', {
    requestId,
    documentNumber: normalizedNumber,
    customerDocument: normalizedDocument,
  });

  state.contificoPreviewInvoiceLookupNumber = normalizedNumber;
  state.contificoPreviewInvoiceLookupCustomerDocument = normalizedDocument;
  state.contificoPreviewInvoiceLookupLoading = true;
  state.contificoPreviewInvoiceLookupError = null;
  state.contificoPreviewInvoiceLookupFetched = false;
  state.contificoPreviewInvoiceLookupProgress = 0;
  state.contificoPreviewInvoiceLookupStage = 'pending';
  state.contificoPreviewInvoiceLookupMetadata = {};
  state.contificoPreviewInvoiceLookupJobId = null;
  state.contificoPreviewInvoiceLookup = null;
  cancelContificoInvoiceLookupPolling();
  setContificoInvoiceLookupVisible(true);
  logInvoiceLookupInfo('Modal de detalle listo para la consulta.', {
    requestId,
    modalVisible: true,
  });
  renderContificoPreviewInvoiceLookup();
  logInvoiceLookupInfo('Estado de la interfaz actualizado a "cargando".', { requestId });

  try {
    logInvoiceLookupInfo('Solicitando creación de trabajo de búsqueda asíncrona.', {
      requestId,
      documentNumber: normalizedNumber,
      customerDocument: normalizedDocument,
    });
    const job = await apiFetch('/temp/contifico/invoices/by-number/jobs', {
      method: 'POST',
      body: {
        document_number: normalizedNumber,
        customer_document: normalizedDocument,
      },
    });
    logInvoiceLookupInfo('Trabajo de búsqueda creado.', {
      requestId,
      jobId: job?.id || null,
      status: job?.status || null,
      progress: job?.progress ?? null,
    });
    const status = applyContificoInvoiceLookupJobUpdate(job, requestId);
    renderContificoPreviewInvoiceLookup();

    if (status === 'pending' || status === 'running') {
      logInvoiceLookupInfo('Trabajo pendiente; se programará un sondeo.', {
        requestId,
        jobId: job?.id || null,
      });
      scheduleContificoInvoiceLookupPoll(job?.id, requestId);
    } else if (status === 'failed') {
      cancelContificoInvoiceLookupPolling();
      if (state.contificoPreviewInvoiceLookupError) {
        showToast(state.contificoPreviewInvoiceLookupError, 'error');
      }
    } else if (status === 'completed') {
      cancelContificoInvoiceLookupPolling();
      if (state.contificoPreviewInvoiceLookup) {
        showToast('Factura encontrada correctamente.', 'success');
      } else if (!state.contificoPreviewInvoiceLookupError) {
        showToast('La búsqueda finalizó sin resultados.', 'info');
      }
    }
  } catch (error) {
    logInvoiceLookupError('Error al consultar la factura puntual en Contífico.', {
      requestId,
      message: error?.message || null,
    });
    cancelContificoInvoiceLookupPolling();
    state.contificoPreviewInvoiceLookupError =
      error?.message || 'No se pudo consultar la factura solicitada.';
    state.contificoPreviewInvoiceLookup = null;
    state.contificoPreviewInvoiceLookupFetched = true;
    state.contificoPreviewInvoiceLookupLoading = false;
    renderContificoPreviewInvoiceLookup();
    showToast(state.contificoPreviewInvoiceLookupError, 'error');
  } finally {
    logInvoiceLookupInfo('Consulta puntual despachada.', {
      requestId,
      jobId: state.contificoPreviewInvoiceLookupJobId || null,
      loading: state.contificoPreviewInvoiceLookupLoading,
      progress: state.contificoPreviewInvoiceLookupProgress,
      error: state.contificoPreviewInvoiceLookupError || null,
      customerDocument: state.contificoPreviewInvoiceLookupCustomerDocument || null,
    });
  }
}

function renderAuditLogs() {
  if (!auditLogTableBody) return;
  auditLogTableBody.innerHTML = '';
  if (!state.auditLogs.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 6;
    cell.textContent = 'No hay registros disponibles aún.';
    cell.className = 'muted';
    row.appendChild(cell);
    auditLogTableBody.appendChild(row);
    return;
  }

  state.auditLogs.forEach((entry) => {
    const row = document.createElement('tr');

    const dateCell = document.createElement('td');
    dateCell.textContent = formatDate(entry.timestamp);
    dateCell.dataset.label = 'Fecha';

    const actorCell = document.createElement('td');
    actorCell.textContent = entry.actor ? entry.actor.full_name : 'Sistema';
    actorCell.dataset.label = 'Usuario';

    const actionCell = document.createElement('td');
    actionCell.textContent = entry.action;
    actionCell.dataset.label = 'Acción';

    const entityCell = document.createElement('td');
    entityCell.textContent = entry.entity_id ? `${entry.entity_type} (#${entry.entity_id})` : entry.entity_type;
    entityCell.dataset.label = 'Entidad';

    const beforeCell = document.createElement('td');
    beforeCell.dataset.label = 'Antes';
    if (entry.before && Object.keys(entry.before).length) {
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(entry.before, null, 2);
      beforeCell.appendChild(pre);
    } else {
      beforeCell.innerHTML = '<span class="muted">Sin datos</span>';
    }

    const afterCell = document.createElement('td');
    afterCell.dataset.label = 'Después';
    if (entry.after && Object.keys(entry.after).length) {
      const pre = document.createElement('pre');
      pre.textContent = JSON.stringify(entry.after, null, 2);
      afterCell.appendChild(pre);
    } else {
      afterCell.innerHTML = '<span class="muted">Sin datos</span>';
    }

    row.appendChild(dateCell);
    row.appendChild(actorCell);
    row.appendChild(actionCell);
    row.appendChild(entityCell);
    row.appendChild(beforeCell);
    row.appendChild(afterCell);

    auditLogTableBody.appendChild(row);
  });
}

async function restoreSessionFromStorage() {
  const storedToken = readStoredToken();
  if (!storedToken) {
    updateNavigationForAuth();
    return;
  }

  state.token = storedToken;
  updateNavigationForAuth();

  try {
    await bootstrapAuthenticatedSession();
  } catch (error) {
    clearStoredToken();
    if (state.token) {
      handleLogout(false);
      showToast('No se pudo restaurar la sesión. Inicia sesión nuevamente.', 'error');
    }
  } finally {
    updateNavigationForAuth();
  }
}

function initialise() {
  ensureMeasurementRow();
  if (customerMeasurementsContainer && !customerMeasurementsContainer.children.length) {
    createMeasurementSetBlock(customerMeasurementsContainer);
  }
  resetCreateUserForm();
  updateUserCreationForm();
}

initialise();
restoreSessionFromStorage();
