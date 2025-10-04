"""Endpoints temporales para validar la integración con Contífico."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from . import schemas
from .contifico import ContificoAPIError, ContificoClient, ContificoTransportError
from .dependencies import admin_required, get_contifico_client


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
) -> schemas.ContificoProductPage:
    try:
        products = contifico_client.list_products(page=page, page_size=page_size)
    except ContificoTransportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.detail,
        ) from exc
    except ContificoAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    items = [schemas.ContificoProduct.from_api(product) for product in products]
    return schemas.ContificoProductPage(page=page, page_size=page_size, items=items)


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
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            invoices = []
        else:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    items = [schemas.ContificoInvoice.from_api(invoice) for invoice in invoices]
    return schemas.ContificoInvoicePage(page=page, page_size=page_size, items=items)


def fetch_invoice_by_document_number(
    contifico_client: ContificoClient, *, document_number: str
) -> schemas.ContificoInvoice:
    invoice = None
    try:
        invoice = contifico_client.find_invoice_by_document_number(document_number)
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


@router.get("/products", response_model=schemas.ContificoProductPage)
def preview_contifico_products(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Vista temporal de productos obtenidos desde Contífico."""

    _ = current_user
    return build_product_page(contifico_client, page=page, page_size=page_size)


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
def preview_contifico_invoice_by_number(
    document_number: str = Query(..., min_length=3, max_length=40),
    contifico_client: ContificoClient = Depends(get_contifico_client),
    current_user=Depends(admin_required()),
):
    """Busca una factura por su número de documento."""

    _ = current_user
    normalized_number = document_number.strip()
    return fetch_invoice_by_document_number(
        contifico_client, document_number=normalized_number
    )


__all__ = [
    "router",
    "build_product_page",
    "build_warehouse_list",
    "build_invoice_page",
    "fetch_invoice_by_document_number",
]
