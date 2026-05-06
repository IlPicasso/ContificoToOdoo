from app.odoo_migration.service import (
    OdooMigrationService,
    PRODUCT_COLUMNS,
    STOCK_COLUMNS,
    STOCK_QUANT_COLUMNS,
    TEMPLATE_PRODUCT_PATH,
    TEMPLATE_STOCK_PATH,
)


def test_product_template_columns_match_service_columns():
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    header = service._read_header(TEMPLATE_PRODUCT_PATH)
    assert header == PRODUCT_COLUMNS


def test_stock_template_columns_match_service_columns():
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    header = service._read_header(TEMPLATE_STOCK_PATH)
    assert header == STOCK_QUANT_COLUMNS
