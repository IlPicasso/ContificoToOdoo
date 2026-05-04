from app.odoo_migration.odoo19_variants import build_attributes_values, build_products_with_variants, build_stock_quant


def _sample():
    base = {
        "nombre": "TERNO 2 BOTONES BRUNO CASSINI",
        "pvp1": "165.130000",
        "cantidad_stock": 0,
        "marca_nombre": "CASSINI TERNOS - CABALLEROS",
        "estado": "A",
        "tipo": "PRO",
        "para_pos": True,
        "porcentaje_iva": 15,
    }
    return [{**base, "codigo": f"007-51BC-2/{s}", "codigo_barra": f"007-51BC-2/O{s}"} for s in ["54", "56", "58", "60", "62"]]


def test_variant_csv_builders():
    products = _sample()
    attrs = build_attributes_values(products)
    assert [r["Values / Value"] for r in attrs if r["Attribute"] == "Talla"] == ["54", "56", "58", "60", "62"]
    assert any(r["Attribute"] == "Marca" and r["Variant Creation Mode"] == "Never" for r in attrs)

    rows = build_products_with_variants(products)
    templates = [r for r in rows if r["Product Attributes / Attribute"] == "Talla"]
    assert len(templates) == 1
    assert templates[0]["External ID"] == "product_template_007_51bc_2"
    assert templates[0]["Product Attributes / Values"] == "54,56,58,60,62"
    assert templates[0]["Barcode"] == ""

    stock = build_stock_quant(products, scheduled_date="2026-05-04")
    assert len(stock) == 5
