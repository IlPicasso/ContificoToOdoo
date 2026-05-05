from app.odoo_migration.odoo19_variants import (
    parse_base_code_and_variant,
    build_products_with_variants_from_variant_rows,
    build_variant_sku_mapping,
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
        {**base, "sku": "007-51BC-2/54", "barcode": "007-51BC-2/O54", "attrs": {"Marca": "ADAMS", "Talla": "54", "Color": "Azul", "Manga de Camisa": "L", "Ancho Corbata": "7"}},
        {**base, "sku": "007-51BC-2/56", "barcode": "007-51BC-2/O56", "attrs": {"Marca": "ADAMS", "Talla": "56", "Color": "Azul", "Manga de Camisa": "L", "Ancho Corbata": "7"}},
    ]


def test_variant_csv_builders():
    products_raw = [{"codigo": f"007-51BC-2/{s}", "marca_nombre": "ADAMS", "cantidad_stock": 0, "estado": "A", "nombre": "CAMISA M/L MODERNA"} for s in ["54", "56"]]
    rows = build_products_with_variants_from_variant_rows(_sample())
    by_attr = {r["Product Attributes / Attribute"]: r for r in rows}
    assert by_attr["Talla"]["Product Attributes / Values"] == "54,56"
    assert by_attr["Marca"]["Product Attributes / Values"] == "ADAMS"
    assert by_attr["Color"]["Product Attributes / Values"] == "Azul"
    assert by_attr["Manga de Camisa"]["Product Attributes / Values"] == "L"
    assert by_attr["Ancho Corbata"]["Product Attributes / Values"] == "7"

    mapping = build_variant_sku_mapping(_sample())
    assert mapping[0]["Ancho Corbata"] == "7 cm"
    assert by_attr["Talla"]["Product Category"] == "Ropa / Camisas"


def test_parent_base_code_extraction_rules():
    assert parse_base_code_and_variant("VE-MICAELA-AZ-XL") == ("VE-MICAELA-AZ", "XL")
    assert parse_base_code_and_variant("17605DC-16.5-S1") == ("17605DC", "16.5-S1")
    assert parse_base_code_and_variant("ZP-0907-BRW/10") == ("ZP-0907-BRW", "10")
    assert parse_base_code_and_variant("BW4624/641-7") == ("BW4624/641", "7")
