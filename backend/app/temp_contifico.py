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


__all__ = [
    "router",
    "build_product_page",
    "build_warehouse_list",
]
