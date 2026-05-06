import pytest

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


def test_split_template_rows_for_odoo_import():
    rows = [
        {"External ID": "product_template_100", "Name": "Camisa 100", "Sales Price": "10.00", "Product Category": "Ropa", "Product Attributes / Attribute": "", "Product Attributes / Values": ""},
        {"External ID": "product_template_200", "Name": "Camisa 200", "Sales Price": "20.00", "Product Category": "Ropa", "Product Attributes / Attribute": "Talla", "Product Attributes / Values": "M"},
        {"External ID": "product_template_200", "Name": "Camisa 200", "Sales Price": "20.00", "Product Category": "Ropa", "Product Attributes / Attribute": "Talla", "Product Attributes / Values": "L,M"},
        {"External ID": "product_template_200", "Name": "Camisa 200", "Sales Price": "20.00", "Product Category": "Ropa", "Product Attributes / Attribute": "Color", "Product Attributes / Values": "Azul"},
    ]
    simple_rows, with_attr_rows = OdooMigrationService._split_template_rows_for_odoo_import(rows)
    assert len(simple_rows) == 1
    assert simple_rows[0]["External ID"] == "product_template_100"
    talla_rows = [r for r in with_attr_rows if r["Product Attributes / Attribute"] == "Talla"]
    assert len(talla_rows) == 1
    assert talla_rows[0]["Product Attributes / Values"] == "L,M"
    assert all(r["Product Attributes / Attribute"] and r["Product Attributes / Values"] for r in with_attr_rows)


def test_validate_template_external_id_conflicts():
    rows = [
        {"External ID": "product_template_ok", "Name": "Producto", "Sales Price": "10.00", "Product Category": "Ropa"},
        {"External ID": "product_template_ok", "Name": "Producto", "Sales Price": "10.00", "Product Category": "Ropa"},
    ]
    OdooMigrationService._validate_template_external_id_conflicts(rows)


def test_validate_template_external_id_conflicts_raises():
    rows = [
        {"External ID": "product_template_conflict", "Name": "Producto A", "Sales Price": "10.00", "Product Category": "Ropa"},
        {"External ID": "product_template_conflict", "Name": "Producto B", "Sales Price": "11.00", "Product Category": "Ropa"},
    ]
    with pytest.raises(ValueError):
        OdooMigrationService._validate_template_external_id_conflicts(rows)
