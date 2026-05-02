from fastapi import APIRouter, Depends, Query

from ..dependencies import get_contifico_client
from ..contifico import ContificoClient
from .service import OdooMigrationService

router = APIRouter(prefix="/odoo-migration", tags=["Odoo Migration"])

@router.post("/products-stock/export")
def export_products_stock(
    page_size: int = Query(default=200, ge=1, le=500),
    max_pages: int = Query(default=50, ge=1, le=500),
    contifico_client: ContificoClient = Depends(get_contifico_client),
):
    service = OdooMigrationService(contifico_client)
    output = service.generate_products_and_stock_csv(page_size=page_size, max_pages=max_pages)
    return {
        "folder": str(output.folder),
        "product_product_csv": str(output.product_csv),
        "initial_stock_csv": str(output.stock_csv),
        "migration_errors_csv": str(output.errors_csv),
        "mapping_report_csv": str(output.mapping_csv),
        "total_products": output.total_products,
        "total_errors": output.total_errors,
    }
