"""Endpoints temporales para validar la integración con Contífico."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool

from . import schemas
from .contifico import ContificoAPIError, ContificoClient, ContificoTransportError
from .dependencies import admin_required, get_contifico_client
from .invoice_jobs import get_invoice_lookup_job_manager


DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200


router = APIRouter(
    prefix="/temp/contifico",
    tags=["Contífico (temporal)"],
)


def build_product_page(
    contifico_client: ContificoClient,
    *,
    page: int,
    page_size: int,
    category_id: str | None = None,
) -> schemas.ContificoProductPage:
    try:
        products = contifico_client.list_products(
            page=page, page_size=page_size, category_id=category_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ContificoTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    except ContificoAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    items = [schemas.ContificoProduct.from_api(product) for product in products]
    return schemas.ContificoProductPage(page=page, page_size=page_size, items=items)


def fetch_product_detail(
    contifico_client: ContificoClient,
    *,
    product_id: str,
) -> schemas.ContificoProduct:
    try:
        product = contifico_client.get_product(product_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ContificoTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    except ContificoAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if not isinstance(product, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El formato de respuesta para el producto no es el esperado.",
        )

    return schemas.ContificoProduct.from_api(product)


def build_product_category_list(
    contifico_client: ContificoClient,
) -> list[schemas.ContificoProductCategory]:
    try:
        categories = contifico_client.list_product_categories()
    except ContificoTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    except ContificoAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return [
        schemas.ContificoProductCategory.from_api(category)
        for category in categories
    ]


def build_warehouse_list(contifico_client: ContificoClient) -> list[schemas.ContificoWarehouse]:
    try:
        warehouses = contifico_client.list_warehouses()
    except ContificoTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    except ContificoAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return [schemas.ContificoWarehouse.from_api(warehouse) for warehouse in warehouses]


def build_invoice_page(
    contifico_client: ContificoClient,
    *,
    page: int,
    page_size: int,
    document_id: str,
) -> schemas.ContificoInvoicePage:
    try:
        invoices = contifico_client.list_invoices_by_customer_document(
            document_id, page=page, page_size=page_size
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ContificoTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    except ContificoAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    items = [schemas.ContificoInvoice.from_api(invoice) for invoice in invoices]
    return schemas.ContificoInvoicePage(page=page, page_size=page_size, items=items)


def fetch_invoice_by_document_number(
    contifico_client: ContificoClient,
    *,
    document_number: str,
    customer_document: str,
) -> schemas.ContificoInvoice:
    invoice = None
    normalized_customer = customer_document.strip()
    if not normalized_customer:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="El número de documento del cliente es obligatorio.",
        )
    try:
        invoice = contifico_client.find_invoice_by_document_number(
            document_number,
            customer_document=normalized_customer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ContificoTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    except ContificoAPIError as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            invoice = None
        else:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró una factura con ese número de documento.",
        )
    return schemas.ContificoInvoice.from_api(invoice)


def fetch_invoice_by_customer_and_document(
    contifico_client: ContificoClient,
    *,
    customer_document: str,
    document_number: str,
) -> schemas.ContificoInvoice:
    invoice = None
    try:
        invoice = contifico_client.find_invoice_by_document_number(
            document_number,
            customer_document=customer_document,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ContificoTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    except ContificoAPIError as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            invoice = None
        else:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    if invoice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontró una factura con ese número de documento.",
        )
    return schemas.ContificoInvoice.from_api(invoice)


def serialize_invoice_lookup_job(job) -> schemas.ContificoInvoiceLookupJob:
    invoice = job.result
    invoice_schema = (
        schemas.ContificoInvoice.from_api(invoice)
        if isinstance(invoice, dict)
        else invoice
    )
    return schemas.ContificoInvoiceLookupJob(
        id=job.id,
        document_number=job.document_number,
        customer_document=job.customer_document,
        status=schemas.ContificoInvoiceLookupJobStatus(job.status.value),
        progress=job.progress,
        stage=job.stage,
        error=job.error,
        result=invoice_schema,
        metadata=dict(job.metadata),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/products", response_model=schemas.ContificoProductPage)
def preview_contifico_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    category_id: str | None = Query(default=None),
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Vista temporal de productos obtenidos desde Contífico."""

    _ = current_user
    return build_product_page(
        contifico_client,
        page=page,
        page_size=page_size,
        category_id=category_id,
    )


@router.get("/products/{product_id}", response_model=schemas.ContificoProduct)
def preview_contifico_product_detail(
    product_id: str,
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Detalle temporal de un producto obtenido desde Contífico."""

    _ = current_user
    return fetch_product_detail(contifico_client, product_id=product_id)


@router.get(
    "/product-categories",
    response_model=list[schemas.ContificoProductCategory],
)
def preview_contifico_product_categories(
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Lista temporal de categorías de productos desde Contífico."""

    _ = current_user
    return build_product_category_list(contifico_client)


@router.get("/warehouses", response_model=list[schemas.ContificoWarehouse])
def preview_contifico_warehouses(
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Vista temporal de bodegas configuradas en Contífico."""

    _ = current_user
    return build_warehouse_list(contifico_client)


@router.get("/invoices/by-customer", response_model=schemas.ContificoInvoicePage)
def preview_contifico_invoices_by_customer(
    document_id: str = Query(..., min_length=3, max_length=30),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Consulta facturas filtrando por la cédula o RUC del cliente."""

    _ = current_user
    normalized_document = document_id.strip()
    return build_invoice_page(
        contifico_client,
        page=page,
        page_size=page_size,
        document_id=normalized_document,
    )


@router.get("/invoices/by-number", response_model=schemas.ContificoInvoice)
async def preview_contifico_invoice_by_number(
    document_number: str = Query(..., min_length=3, max_length=40),
    customer_document: str = Query(..., min_length=3, max_length=30),
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Busca una factura por su número de documento validando el cliente."""

    _ = current_user
    normalized_number = document_number.strip()
    normalized_customer = customer_document.strip()
    return await run_in_threadpool(
        fetch_invoice_by_document_number,
        contifico_client,
        document_number=normalized_number,
        customer_document=normalized_customer,
    )


@router.get(
    "/invoices/by-customer-and-number",
    response_model=schemas.ContificoInvoice,
)
async def preview_contifico_invoice_by_customer_and_number(
    customer_document: str = Query(..., min_length=3, max_length=30),
    document_number: str = Query(..., min_length=3, max_length=40),
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Busca una factura específica combinando cliente y número de documento."""

    _ = current_user
    normalized_customer = customer_document.strip()
    normalized_number = document_number.strip()
    return await run_in_threadpool(
        fetch_invoice_by_customer_and_document,
        contifico_client,
        customer_document=normalized_customer,
        document_number=normalized_number,
    )


@router.post(
    "/invoices/by-number/jobs",
    response_model=schemas.ContificoInvoiceLookupJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_contifico_invoice_lookup_job(
    payload: schemas.ContificoInvoiceLookupRequest,
    job_manager=Depends(get_invoice_lookup_job_manager),
    current_user=Depends(admin_required()),
):
    """Inicia una búsqueda asíncrona de factura en Contífico."""

    _ = current_user
    try:
        job = await job_manager.start_job(
            payload.document_number, customer_document=payload.customer_document
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return serialize_invoice_lookup_job(job)


@router.get(
    "/invoices/by-number/jobs/{job_id}",
    response_model=schemas.ContificoInvoiceLookupJob,
)
async def get_contifico_invoice_lookup_job(
    job_id: str,
    job_manager=Depends(get_invoice_lookup_job_manager),
    current_user=Depends(admin_required()),
):
    """Recupera el estado actual de un trabajo de búsqueda de factura."""

    _ = current_user
    job = await job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe un trabajo con el identificador proporcionado.",
        )
    return serialize_invoice_lookup_job(job)


__all__ = [
    "router",
    "build_product_page",
    "build_warehouse_list",
    "build_invoice_page",
    "fetch_invoice_by_document_number",
    "fetch_invoice_by_customer_and_document",
]
