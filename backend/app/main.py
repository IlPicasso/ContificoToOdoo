import math
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Generator, Iterable, List, Optional, Sequence, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import auth, crud, models, schemas
from .config import get_settings
from .database import Base, engine, get_db
from .dependencies import (
    admin_required,
    staff_required,
    tailor_or_admin_required,
    vendor_or_admin_required,
)
from .migrations import apply_schema_upgrades
from .integrations import ContificoClient, ContificoError

settings = get_settings()

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    apply_schema_upgrades(engine)
    yield


def resolve_pagination(
    *,
    skip: Optional[int],
    limit: Optional[int],
    page: int,
    page_size: int,
    default_size: int = DEFAULT_PAGE_SIZE,
) -> Tuple[int, int, int]:
    effective_page_size = limit if limit is not None else page_size
    if effective_page_size is None or effective_page_size <= 0:
        effective_page_size = default_size
    skip_value = skip if skip is not None else (page - 1) * effective_page_size
    if skip_value < 0:
        skip_value = 0
    current_page = (skip_value // effective_page_size) + 1 if effective_page_size else 1
    return skip_value, effective_page_size, current_page

app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _validate_assigned_tailor(
    db: Session, assigned_tailor_id: Optional[int]
) -> Optional[models.User]:
    """Ensure the provided tailor id exists and belongs to a tailor user."""

    if assigned_tailor_id is None:
        return None
    tailor = crud.get_user(db, assigned_tailor_id)
    if not tailor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El sastre asignado no existe",
        )
    if tailor.role != models.UserRole.SASTRE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario asignado no es un sastre",
        )
    return tailor


def _validate_assigned_vendor(
    db: Session, assigned_vendor_id: Optional[int]
) -> Optional[models.User]:
    """Ensure the provided vendor id exists and belongs to a vendor user."""

    if assigned_vendor_id is None:
        return None
    vendor = crud.get_user(db, assigned_vendor_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El vendedor asignado no existe",
        )
    if vendor.role != models.UserRole.VENDEDOR:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El usuario asignado no es un vendedor",
        )
    return vendor


def _get_order_or_404(db: Session, order_id: int) -> models.Order:
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden no encontrada")
    return order


def get_contifico_client_dependency() -> Generator[ContificoClient, None, None]:
    if not settings.contifico_api_key or not settings.contifico_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La integración con Contifico no está configurada.",
        )

    client = ContificoClient(
        base_url=settings.contifico_base_url,
        api_key=settings.contifico_api_key,
        api_token=settings.contifico_api_token,
        timeout=settings.contifico_timeout_seconds,
        rate_limit_per_minute=settings.contifico_rate_limit_per_minute,
        max_retries=settings.contifico_max_retries,
        retry_backoff_seconds=settings.contifico_retry_backoff_seconds,
        company_id=settings.contifico_company_id,
    )
    try:
        yield client
    finally:
        client.close()


def _flatten_invoice_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    for key in ("documento", "data", "detalle"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            merged: Dict[str, Any] = {**nested}
            for extra_key, value in payload.items():
                if extra_key not in merged:
                    merged[extra_key] = value
            return merged
    return dict(payload)


def _get_nested_value(data: Any, path: Sequence[str]) -> Any:
    current = data
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _extract_value(data: Dict[str, Any], candidates: Iterable[Sequence[str]]) -> Any:
    for path in candidates:
        value = _get_nested_value(data, path)
        if isinstance(value, str):
            if value.strip():
                return value
        elif value not in (None, "", []):
            return value
    return None


def _extract_text(data: Dict[str, Any], candidates: Iterable[Sequence[str]]) -> Optional[str]:
    value = _extract_value(data, candidates)
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    if value is not None:
        text = str(value).strip()
        return text or None
    return None


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        normalized = stripped.replace(" ", "")
        if normalized.count(",") > 1 and "." not in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        elif normalized.count(",") == 1 and normalized.count(".") == 0:
            normalized = normalized.replace(",", ".")
        else:
            normalized = normalized.replace(",", "")
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None
    return None


def _extract_decimal(data: Dict[str, Any], candidates: Iterable[Sequence[str]]) -> Optional[Decimal]:
    raw_value = _extract_value(data, candidates)
    return _to_decimal(raw_value)


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    if value is None:
        return None
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    result = float(quantized)
    if abs(result) < 0.0005:
        return 0.0
    return result


def _extract_payment_date(invoice: Dict[str, Any]) -> Optional[str]:
    direct = _extract_text(
        invoice,
        [
            ("fecha_pago",),
            ("fechaPago",),
            ("fecha_cobro",),
            ("fechaCobro",),
            ("fecha_cancelacion",),
            ("fechaCancelacion",),
        ],
    )
    if direct:
        return direct

    payments = invoice.get("pagos")
    if isinstance(payments, list):
        candidates: List[str] = []
        for item in payments:
            if isinstance(item, dict):
                candidate = _extract_text(
                    item,
                    [
                        ("fecha",),
                        ("fecha_pago",),
                        ("fechaPago",),
                        ("fecha_registro",),
                        ("fechaRegistro",),
                    ],
                )
                if candidate:
                    candidates.append(candidate)
        if candidates:
            candidates.sort()
            return candidates[-1]
    return None


def _extract_currency(invoice: Dict[str, Any]) -> Optional[str]:
    value = _extract_value(
        invoice,
        [
            ("moneda",),
            ("divisa",),
            ("currency",),
            ("totales", "moneda"),
            ("totales", "currency"),
            ("totals", "moneda"),
            ("totals", "currency"),
        ],
    )
    if isinstance(value, dict):
        nested = _extract_text(value, [("codigo",), ("code",)])
        return nested.upper() if nested else None
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed.upper() if trimmed else None
    return None


def _build_invoice_summary(invoice_number: str, payload: Any) -> schemas.InvoiceSummary:
    if isinstance(payload, list):
        payload = next((item for item in payload if isinstance(item, dict)), {})
    elif not isinstance(payload, dict):
        payload = {}

    invoice = _flatten_invoice_payload(payload)
    subtotal_decimal = _extract_decimal(
        invoice,
        [
            ("subtotal",),
            ("subtotal_sin_impuestos",),
            ("subtotalSinImpuestos",),
            ("totales", "subtotal"),
            ("totales", "subtotal_sin_impuestos"),
            ("totales", "subtotalSinImpuestos"),
            ("totals", "subtotal"),
            ("totals", "subtotalSinImpuestos"),
        ],
    )
    tax_decimal = _extract_decimal(
        invoice,
        [
            ("total_impuestos",),
            ("totalImpuestos",),
            ("impuestos",),
            ("iva",),
            ("totales", "impuestos"),
            ("totales", "iva"),
            ("totals", "impuestos"),
            ("totals", "taxes"),
        ],
    )
    total_decimal = _extract_decimal(
        invoice,
        [
            ("total",),
            ("total_final",),
            ("totalFinal",),
            ("total_con_impuestos",),
            ("totalConImpuestos",),
            ("totales", "total"),
            ("totals", "total"),
        ],
    )
    paid_decimal = _extract_decimal(
        invoice,
        [
            ("total_pagado",),
            ("totalPagado",),
            ("pagado",),
            ("totales", "pagado"),
            ("totals", "paid"),
        ],
    )
    pending_decimal = _extract_decimal(
        invoice,
        [
            ("saldo",),
            ("saldo_pendiente",),
            ("saldoPendiente",),
            ("pendiente",),
            ("totales", "saldo"),
            ("totales", "pendiente"),
            ("totals", "pending"),
        ],
    )

    if pending_decimal is None and total_decimal is not None and paid_decimal is not None:
        pending_decimal = total_decimal - paid_decimal
    if paid_decimal is None and total_decimal is not None and pending_decimal is not None:
        paid_decimal = total_decimal - pending_decimal

    if pending_decimal is not None and pending_decimal < Decimal("0"):
        pending_decimal = max(pending_decimal, Decimal("0"))

    subtotal = _decimal_to_float(subtotal_decimal)
    tax_total = _decimal_to_float(tax_decimal)
    total = _decimal_to_float(total_decimal)
    paid_total = _decimal_to_float(paid_decimal)
    pending_total = _decimal_to_float(pending_decimal)

    status = _extract_text(
        invoice,
        [
            ("estado",),
            ("estado_documento",),
            ("estadoDocumento",),
            ("estado_autorizacion",),
            ("estadoAutorizacion",),
        ],
    )
    payment_status = _extract_text(
        invoice,
        [
            ("estado_pago",),
            ("estadoPago",),
            ("estado_cobro",),
            ("estadoCobro",),
            ("estado_pago_actual",),
            ("estadoPagoActual",),
        ],
    )
    if not payment_status:
        payment_status = status

    payment_date = _extract_payment_date(invoice)
    currency = _extract_currency(invoice)
    download_url = _extract_text(
        invoice,
        [
            ("url_pdf",),
            ("urlPdf",),
            ("enlace_pdf",),
            ("link_descarga",),
            ("linkDescarga",),
            ("links", "pdf"),
            ("links", "descarga"),
            ("links", "download"),
            ("links", "pdf_url"),
            ("links", "pdfUrl"),
        ],
    )
    share_url = _extract_text(
        invoice,
        [
            ("url_compartir",),
            ("urlCompartir",),
            ("enlace_publico",),
            ("enlacePublico",),
            ("link_publico",),
            ("linkPublico",),
            ("links", "publico"),
            ("links", "public"),
            ("links", "share"),
        ],
    )

    has_pending_balance = bool(pending_total is not None and pending_total > 0.009)

    return schemas.InvoiceSummary(
        invoice_number=invoice_number,
        status=status,
        payment_status=payment_status,
        subtotal=subtotal,
        tax_total=tax_total,
        total=total,
        paid_total=paid_total,
        pending_total=pending_total,
        has_pending_balance=has_pending_balance,
        currency=currency,
        payment_date=payment_date,
        download_url=download_url,
        share_url=share_url,
    )


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.post("/auth/login", response_model=schemas.Token)
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = auth.authenticate_user(db, request.username, request.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    access_token = auth.create_access_token({"sub": user.username})
    return schemas.Token(access_token=access_token)


@app.get("/statuses", response_model=List[str])
def list_statuses() -> List[str]:
    return [status.value for status in models.OrderStatus]


@app.post(
    "/users",
    response_model=schemas.UserOut,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    user_in: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required()),
):
    existing = crud.get_user_by_username(db, user_in.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario ya existe")
    user = crud.create_user(db, user_in)
    crud.create_audit_log(
        db,
        actor=current_user,
        action="create",
        entity_type="user",
        entity_id=user.id,
        after=crud.serialize_user(user),
    )
    return user


@app.get("/users/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(auth.get_current_user)):
    return current_user


@app.get("/users", response_model=List[schemas.UserOut])
def read_users(
    role: Optional[models.UserRole] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required()),
):
    _ = current_user
    return crud.get_users(db, role=role)


@app.get("/users/tailors", response_model=List[schemas.UserOut])
def read_tailors(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    _ = current_user
    return crud.get_users(db, role=models.UserRole.SASTRE)


@app.get("/users/vendors", response_model=List[schemas.UserOut])
def read_vendors(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(vendor_or_admin_required()),
):
    _ = current_user
    return crud.get_users(db, role=models.UserRole.VENDEDOR)


@app.patch("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required()),
):
    db_user = crud.get_user(db, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")
    before = crud.serialize_user(db_user)
    updated_user = crud.update_user(db, db_user, user_update)
    crud.create_audit_log(
        db,
        actor=current_user,
        action="update",
        entity_type="user",
        entity_id=updated_user.id,
        before=before,
        after=crud.serialize_user(updated_user),
    )
    return updated_user


@app.get("/public/orders", response_model=List[schemas.OrderPublic])
def search_public_orders(
    order_number: Optional[str] = Query(default=None),
    customer_document: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    if not order_number and not customer_document:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar el número de orden o la cédula del cliente",
        )
    return crud.search_orders(db, order_number=order_number, customer_document=customer_document)


@app.get("/customers", response_model=schemas.PaginatedCustomers)
def list_customers(
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=MAX_PAGE_SIZE),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    _ = current_user
    trimmed_search = search.strip() if search else None
    skip_value, limit_value, page_value = resolve_pagination(
        skip=skip, limit=limit, page=page, page_size=page_size
    )
    customers, total = crud.get_customers(
        db,
        skip=skip_value,
        limit=limit_value,
        search=trimmed_search,
    )
    if total and skip_value >= total and page_value > 1:
        max_page = max(math.ceil(total / limit_value), 1)
        skip_value = (max_page - 1) * limit_value
        customers, total = crud.get_customers(
            db,
            skip=skip_value,
            limit=limit_value,
            search=trimmed_search,
        )
        page_value = max_page
    if total == 0:
        page_value = 1
    return {
        "items": customers,
        "total": total,
        "page": page_value,
        "page_size": limit_value,
    }


@app.post("/customers", response_model=schemas.CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer_endpoint(
    customer_in: schemas.CustomerCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    if crud.get_customer_by_document(db, customer_in.document_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un cliente con esa identificación")
    customer = crud.create_customer(db, customer_in)
    crud.create_audit_log(
        db,
        actor=current_user,
        action="create",
        entity_type="customer",
        entity_id=customer.id,
        after=crud.serialize_customer(customer),
    )
    return customer


@app.get("/customers/{customer_id}", response_model=schemas.CustomerRead)
def get_customer_endpoint(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    _ = current_user
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    return customer


@app.patch("/customers/{customer_id}", response_model=schemas.CustomerRead)
def update_customer_endpoint(
    customer_id: int,
    customer_update: schemas.CustomerUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if (
        customer_update.document_id
        and customer_update.document_id != customer.document_id
        and (existing := crud.get_customer_by_document(db, customer_update.document_id))
        and existing.id != customer.id
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe un cliente con esa identificación")
    before = crud.serialize_customer(customer)
    updated_customer = crud.update_customer(db, customer, customer_update)
    crud.create_audit_log(
        db,
        actor=current_user,
        action="update",
        entity_type="customer",
        entity_id=updated_customer.id,
        before=before,
        after=crud.serialize_customer(updated_customer),
    )
    return updated_customer


@app.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_endpoint(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required()),
):
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
    if crud.customer_has_orders(db, customer.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se puede eliminar el cliente porque tiene órdenes registradas.",
        )
    before = crud.serialize_customer(customer)
    crud.delete_customer(db, customer)
    crud.create_audit_log(
        db,
        actor=current_user,
        action="delete",
        entity_type="customer",
        entity_id=customer_id,
        before=before,
    )
    return None


@app.get("/orders", response_model=schemas.PaginatedOrders)
def list_orders(
    skip: Optional[int] = Query(default=None, ge=0),
    limit: Optional[int] = Query(default=None, ge=1, le=MAX_PAGE_SIZE),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    search: Optional[str] = Query(default=None),
    customer_id: Optional[int] = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    _ = current_user
    trimmed_search = search.strip() if search else None
    skip_value, limit_value, page_value = resolve_pagination(
        skip=skip, limit=limit, page=page, page_size=page_size
    )
    orders, total = crud.get_orders(
        db,
        skip=skip_value,
        limit=limit_value,
        search=trimmed_search,
        customer_id=customer_id,
    )
    if total and skip_value >= total and page_value > 1:
        max_page = max(math.ceil(total / limit_value), 1)
        skip_value = (max_page - 1) * limit_value
        orders, total = crud.get_orders(
            db,
            skip=skip_value,
            limit=limit_value,
            search=trimmed_search,
            customer_id=customer_id,
        )
        page_value = max_page
    if total == 0:
        page_value = 1
    return {
        "items": orders,
        "total": total,
        "page": page_value,
        "page_size": limit_value,
    }


@app.post("/orders", response_model=schemas.OrderRead, status_code=status.HTTP_201_CREATED)
def create_order_endpoint(
    order_in: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(vendor_or_admin_required()),
):
    if current_user.role not in {models.UserRole.ADMIN, models.UserRole.VENDEDOR}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos para realizar esta acción",
        )
    if crud.get_order_by_number(db, order_in.order_number):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ya existe una orden con ese número")
    customer = crud.get_customer(db, order_in.customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")

    normalized_tasks: List[schemas.OrderTaskCreate] = []
    incoming_tasks = getattr(order_in, "tasks", []) or []
    for task in incoming_tasks:
        if task.responsible_id is not None:
            _validate_assigned_tailor(db, task.responsible_id)
        normalized_tasks.append(
            schemas.OrderTaskCreate(
                description=task.description,
                status=task.status,
                responsible_id=task.responsible_id,
            )
        )
    if not normalized_tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes registrar al menos un trabajo para la orden",
        )


    order_data = order_in.model_dump()
    order_data["tasks"] = [task.model_dump() for task in normalized_tasks]
    if not order_data.get("customer_name"):
        order_data["customer_name"] = customer.full_name
    if not order_data.get("customer_document"):
        order_data["customer_document"] = customer.document_id
    if order_data.get("customer_contact") in (None, ""):
        order_data["customer_contact"] = customer.phone
    _validate_assigned_tailor(db, order_data.get("assigned_tailor_id"))
    assigned_vendor_id = order_data.get("assigned_vendor_id")
    if assigned_vendor_id is None and current_user.role == models.UserRole.VENDEDOR:
        assigned_vendor_id = current_user.id
        order_data["assigned_vendor_id"] = assigned_vendor_id
    else:
        order_data["assigned_vendor_id"] = assigned_vendor_id
    if order_data.get("assigned_vendor_id") is not None:
        _validate_assigned_vendor(db, order_data["assigned_vendor_id"])
    order = crud.create_order(db, schemas.OrderCreate(**order_data))
    crud.create_audit_log(
        db,
        actor=current_user,
        action="create",
        entity_type="order",
        entity_id=order.id,
        after=crud.serialize_order(order),
    )
    return order


@app.get("/orders/{order_id}", response_model=schemas.OrderRead)
def get_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    _ = current_user
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden no encontrada")
    return order


@app.get("/orders/{order_id}/invoice", response_model=schemas.InvoiceSummary)
def get_order_invoice_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
    contifico_client: ContificoClient = Depends(get_contifico_client_dependency),
):
    _ = current_user
    order = _get_order_or_404(db, order_id)
    invoice_number = (order.invoice_number or "").strip()
    if not invoice_number:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La orden no tiene número de factura registrado.",
        )

    try:
        invoice_payload = contifico_client.get_invoice(invoice_number)
    except ContificoError as exc:  # pragma: no cover - integration error path
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo consultar la factura en Contifico. Inténtalo más tarde.",
        ) from exc

    return _build_invoice_summary(invoice_number, invoice_payload)


@app.patch("/orders/{order_id}", response_model=schemas.OrderRead)
def update_order_endpoint(
    order_id: int,
    order_update: schemas.OrderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden no encontrada")
    update_data = order_update.model_dump(exclude_unset=True)
    if "customer_id" in update_data and update_data["customer_id"] != order.customer_id:
        new_customer = crud.get_customer(db, update_data["customer_id"])
        if not new_customer:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cliente no encontrado")
        if not update_data.get("customer_name"):
            update_data["customer_name"] = new_customer.full_name
        if not update_data.get("customer_document"):
            update_data["customer_document"] = new_customer.document_id
        if update_data.get("customer_contact") in (None, ""):
            update_data["customer_contact"] = new_customer.phone
    if "assigned_tailor_id" in update_data:
        _validate_assigned_tailor(db, update_data["assigned_tailor_id"])
    if "assigned_vendor_id" in update_data:
        _validate_assigned_vendor(db, update_data["assigned_vendor_id"])
    before = crud.serialize_order(order)
    updated_order = crud.update_order(db, order, schemas.OrderUpdate(**update_data))
    crud.create_audit_log(
        db,
        actor=current_user,
        action="update",
        entity_type="order",
        entity_id=updated_order.id,
        before=before,
        after=crud.serialize_order(updated_order),
    )
    return updated_order


@app.get("/orders/{order_id}/tasks", response_model=List[schemas.OrderTaskRead])
def list_order_tasks_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(staff_required()),
):
    _ = current_user
    order = _get_order_or_404(db, order_id)
    return crud.list_order_tasks(db, order_id=order.id)


@app.post(
    "/orders/{order_id}/tasks",
    response_model=schemas.OrderTaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_order_task_endpoint(
    order_id: int,
    task_in: schemas.OrderTaskCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(tailor_or_admin_required()),
):
    order = _get_order_or_404(db, order_id)
    task_data = task_in.model_dump()
    responsible_id = task_data.get("responsible_id")
    if responsible_id is not None:
        _validate_assigned_tailor(db, responsible_id)
    description_value = task_data.get("description")
    if isinstance(description_value, str):
        task_data["description"] = description_value.strip()
    task = crud.create_order_task(
        db,
        order_id=order.id,
        task_in=schemas.OrderTaskCreate(**task_data),
    )
    crud.create_audit_log(
        db,
        actor=current_user,
        action="create",
        entity_type="order_task",
        entity_id=task.id,
        after=crud.serialize_order_task(task),
    )
    return task


@app.patch(
    "/orders/{order_id}/tasks/{task_id}",
    response_model=schemas.OrderTaskRead,
)
def update_order_task_endpoint(
    order_id: int,
    task_id: int,
    task_update: schemas.OrderTaskUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(tailor_or_admin_required()),
):
    order = _get_order_or_404(db, order_id)
    db_task = crud.get_order_task(db, order_id=order.id, task_id=task_id)
    if not db_task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tarea no encontrada")
    update_fields = task_update.model_dump(exclude_unset=True)
    if "responsible_id" in task_update.model_fields_set and update_fields.get("responsible_id") is not None:
        _validate_assigned_tailor(db, update_fields["responsible_id"])
    before_status = db_task.status
    updated_task = crud.update_order_task(db, db_task, task_update)
    if "status" in update_fields and before_status != updated_task.status:
        crud.create_audit_log(
            db,
            actor=current_user,
            action="update_status",
            entity_type="order_task",
            entity_id=updated_task.id,
            before={"status": before_status.value},
            after={"status": updated_task.status.value},
        )
    return updated_task


@app.delete("/orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order_endpoint(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required()),
):
    order = crud.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Orden no encontrada")
    before = crud.serialize_order(order)
    crud.delete_order(db, order)
    crud.create_audit_log(
        db,
        actor=current_user,
        action="delete",
        entity_type="order",
        entity_id=order_id,
        before=before,
    )
    return None


@app.get("/audit-logs", response_model=List[schemas.AuditLogRead])
def list_audit_logs_endpoint(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(admin_required()),
):
    _ = current_user
    return crud.list_audit_logs(db, limit=limit)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )
