from app.odoo_migration.odoo19_variants import (
    build_attributes_values,
    build_products_with_variants_from_variant_rows,
    build_stock_quant,
)


def _sample():
    base = {
        "name": "CAMISA M/L MODERNA",
        "price": "55.00",
        "cost": "25.00",
        "stock_map": {"BPU": 0},
        "category": "Ropa / Camisas",
        "attrs": {"Marca": "ADAMS", "Color": "Azul", "Manga de Camisa": "L"},
    }
    return [
        {**base, "sku": "007-51BC-2/54", "barcode": "007-51BC-2/O54", "attrs": {"Marca": "ADAMS", "Talla": "54", "Color": "Azul", "Manga de Camisa": "L", "Ancho Corbata": "7 cm"}},
        {**base, "sku": "007-51BC-2/56", "barcode": "007-51BC-2/O56", "attrs": {"Marca": "ADAMS", "Talla": "56", "Color": "Azul", "Manga de Camisa": "L", "Ancho Corbata": "7 cm"}},
    ]


def test_variant_csv_builders():
    products_raw = [{"codigo": f"007-51BC-2/{s}", "marca_nombre": "ADAMS", "cantidad_stock": 0, "estado": "A", "nombre": "CAMISA M/L MODERNA"} for s in ["54", "56"]]
    attrs = build_attributes_values(products_raw)
    assert [r["Values / Value"] for r in attrs if r["Attribute"] == "Talla"] == ["54", "56"]
    assert any(r["Attribute"] == "Marca" and r["Variant Creation Mode"] == "Never" for r in attrs)

    rows = build_products_with_variants_from_variant_rows(_sample())
    by_attr = {r["Product Attributes / Attribute"]: r for r in rows}
    assert by_attr["Talla"]["Product Attributes / Values"] == "54,56"
    assert by_attr["Marca"]["Product Attributes / Values"] == "ADAMS"
    assert by_attr["Color"]["Product Attributes / Values"] == "Azul"
    assert by_attr["Manga de Camisa"]["Product Attributes / Values"] == "L"
    assert by_attr["Ancho Corbata"]["Product Attributes / Values"] == "7 cm"
    assert by_attr["Talla"]["Product Category"] == "Ropa / Camisas"

    stock = build_stock_quant(products_raw, scheduled_date="2026-05-04")
    assert len(stock) == 2
