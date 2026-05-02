from app.odoo_migration.service import OdooMigrationService, PRODUCT_COLUMNS, TEMPLATE_PRODUCT_PATH


def test_product_template_columns_match_service_columns():
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    header = service._read_header(TEMPLATE_PRODUCT_PATH)
    assert header == PRODUCT_COLUMNS
