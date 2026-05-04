from app.odoo_migration.odoo19_variants import (
    build_attributes_values,
    build_products_with_variants_from_variant_rows,
    build_stock_quant,
)


def _sample():
    base = {
        "name": "TERNO 2 BOTONES BRUNO CASSINI",
        "price": "165.13",
        "cost": "0.00",
        "stock_map": {"BPU": 0},
        "category": "Ropa / Ternos",
        "attrs": {"Marca": "CASSINI TERNOS - CABALLEROS"},
    }
    return [{**base, "sku": f"007-51BC-2/{s}", "barcode": f"007-51BC-2/O{s}", "attrs": {"Marca": "CASSINI TERNOS - CABALLEROS", "Talla": s}} for s in ["54", "56", "58", "60", "62"]]


def test_variant_csv_builders():
    products_raw = [{"codigo": f"007-51BC-2/{s}", "marca_nombre": "CASSINI TERNOS - CABALLEROS", "cantidad_stock": 0, "estado": "A", "nombre": "TERNO 2 BOTONES BRUNO CASSINI"} for s in ["54", "56", "58", "60", "62"]]
    attrs = build_attributes_values(products_raw)
    assert [r["Values / Value"] for r in attrs if r["Attribute"] == "Talla"] == ["54", "56", "58", "60", "62"]
    assert any(r["Attribute"] == "Marca" and r["Variant Creation Mode"] == "Never" for r in attrs)

    rows = build_products_with_variants_from_variant_rows(_sample())
    templates = [r for r in rows if r["Product Attributes / Attribute"] == "Talla"]
    assert len(templates) == 1
    assert templates[0]["External ID"] == "product_template_007_51bc_2"
    assert templates[0]["Product Attributes / Values"] == "54,56,58,60,62"
    assert templates[0]["Barcode"] == ""
    assert templates[0]["Product Category"] == "Ropa / Ternos"

    stock = build_stock_quant(products_raw, scheduled_date="2026-05-04")
    assert len(stock) == 5
