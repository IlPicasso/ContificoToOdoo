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


def test_collect_template_external_id_conflicts():
    rows = [
        {"External ID": "product_template_ok", "Name": "Producto", "Sales Price": "10.00", "Product Category": "Ropa"},
        {"External ID": "product_template_ok", "Name": "Producto", "Sales Price": "10.00", "Product Category": "Ropa"},
    ]
    conflicts, out_rows = OdooMigrationService._collect_template_external_id_conflicts(rows)
    assert conflicts == set()
    assert out_rows == []


def test_collect_template_external_id_conflicts_detects():
    rows = [
        {"External ID": "product_template_conflict", "Name": "Producto A", "Sales Price": "10.00", "Product Category": "Ropa"},
        {"External ID": "product_template_conflict", "Name": "Producto B", "Sales Price": "11.00", "Product Category": "Ropa"},
    ]
    conflicts, out_rows = OdooMigrationService._collect_template_external_id_conflicts(rows)
    assert "product_template_conflict" in conflicts
    assert len(out_rows) == 2


def test_filter_template_attributes_with_master_catalog(tmp_path, monkeypatch):
    catalog = tmp_path / "Product Attribute (product.attribute).csv"
    catalog.write_text(
        "Attribute,Values / Value\n"
        "Talla,S\n"
        "Talla,M\n"
        "Color,Azul\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(OdooMigrationService, "_attribute_catalog_paths", staticmethod(lambda: [catalog]))
    simple_rows = [{"External ID": "product_template_1", "Name": "Simple"}]
    with_attr_rows = [
        {"External ID": "product_template_2", "Name": "Camisa", "Product Attributes / Attribute": "Talla", "Product Attributes / Values": "S,M,9002"},
        {"External ID": "product_template_2", "Name": "Camisa", "Product Attributes / Attribute": "Color", "Product Attributes / Values": "Azul"},
        {"External ID": "product_template_3", "Name": "Otro", "Product Attributes / Attribute": "Marca", "Product Attributes / Values": "X"},
    ]
    out_simple, out_with_attrs, rejects = OdooMigrationService._filter_template_attributes_with_master_catalog(
        simple_rows=simple_rows,
        with_attr_rows=with_attr_rows,
    )
    assert {r["External ID"] for r in out_simple} == {"product_template_1", "product_template_3"}
    assert {r["External ID"] for r in out_with_attrs} == {"product_template_2"}
    assert any(r["attempted_value"] == "9002" for r in rejects)
    assert any(r["attempted_attribute"] == "Marca" and "Attribute not found" in r["reason"] for r in rejects)
