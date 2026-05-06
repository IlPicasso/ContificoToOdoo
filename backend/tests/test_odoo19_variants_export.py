from app.odoo_migration.odoo19_variants import (
    parse_base_code_and_variant,
    derive_parent_and_attrs,
    build_products_with_variants_from_variant_rows,
    build_variant_sku_mapping,
    dedupe_variant_mapping_rows,
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
    assert by_attr["Ancho Corbata"]["Product Attributes / Values"] == "7 cm"

    mapping = build_variant_sku_mapping(_sample())
    assert mapping[0]["Ancho Corbata"] == "7 cm"
    assert by_attr["Talla"]["Product Category"] == "Ropa / Camisas"


def test_parent_base_code_extraction_rules():
    assert parse_base_code_and_variant("VE-MICAELA-AZ-XL") == ("VE-MICAELA-AZ", "XL")
    assert parse_base_code_and_variant("17605DC-16.5-S1") == ("17605DC", "16.5-S1")
    assert parse_base_code_and_variant("ZP-0907-BRW/10") == ("ZP-0907-BRW", "10")
    assert parse_base_code_and_variant("BW4624/641-7") == ("BW4624/641", "7")


def test_tie_rule_moves_talla_to_ancho_and_formats_cm():
    rows = build_variant_sku_mapping([{
        "sku": "BW4624/98-7",
        "name": "Corbata BW4624/98",
        "barcode": "",
        "price": "21.65",
        "cost": "8.00",
        "category": "Ropa / Hombres / Corbatas",
        "attrs": {"Talla": "7", "Ancho Corbata": "", "Color": "Azul", "Marca": "ADAMS"},
    }])
    assert rows[0]["Talla"] == ""
    assert rows[0]["Ancho Corbata"] == "7 cm"


def test_dedupe_variant_mapping_by_template_and_attributes():
    rows = build_variant_sku_mapping([
        {"sku": "210001/46", "name": "Terno X", "barcode": "", "price": "1", "cost": "1", "category": "TERNO / CABALLERO", "attrs": {"Color": "Azul", "Marca": "A"}},
        {"sku": "210001BG/46", "name": "Terno X", "barcode": "", "price": "1", "cost": "1", "category": "TERNO / CABALLERO", "attrs": {"Color": "Azul", "Marca": "A"}},
    ])
    deduped, duplicates = dedupe_variant_mapping_rows(rows)
    assert len(deduped) == 2
    assert duplicates and duplicates[0]["count"] == 2


def test_bg_dc_and_slash_and_tie_rules():
    p1 = derive_parent_and_attrs("17604BG-DC-18.5-S1", "CAMISA 17604", "CAMISA")
    assert p1["parent_key"] == "17604-DC"
    assert p1["attrs"]["Talla"] == "18.5"
    assert p1["attrs"]["Manga de Camisa"] == "S1 - 32/33"

    p2 = derive_parent_and_attrs("210001BG/54", "TERNO 210001", "TERNO / CABALLERO")
    assert p2["parent_key"] == "210001"
    assert p2["attrs"]["Talla"] == "54"

    p3 = derive_parent_and_attrs("TL-X25-502A.A/L", "TL", "OTROS")
    assert p3["parent_key"] == "TL-X25-502A.A"
    assert p3["attrs"]["Talla"] == "L"

    p4 = derive_parent_and_attrs("BW4624/641-7", "CORBATA BW", "ROPA / HOMBRES / CORBATAS")
    assert p4["parent_key"] == "BW4624/641"
    assert p4["attrs"]["Ancho Corbata"] == "7 cm"

    p5 = derive_parent_and_attrs("VE-MICAELA-AZ-XL", "VESTIDO MICAELA AZUL", "Ropa / Mujeres / Vestidos")
    assert p5["parent_key"] == "VE-MICAELA-AZ"
    assert p5["attrs"]["Talla"] == "XL"


def test_invalid_raw_attrs_do_not_pollute_talla_or_ancho():
    rows = build_variant_sku_mapping([
        {"sku": "MR-10845-1/7", "name": "MANCUERNILLA", "barcode": "", "price": "1", "cost": "1", "category": "ACCESORIOS", "attrs": {"Ancho Corbata": "MR-10845-1/7"}},
        {"sku": "CIN-C-ML", "name": "CINTURON", "barcode": "", "price": "1", "cost": "1", "category": "ACCESORIOS", "attrs": {"Talla": "CIN-C-ML"}},
    ])
    assert rows[0]["Ancho Corbata"] == ""
    assert rows[1]["Talla"] == ""


def test_tie_slash_non_width_is_not_forced_to_ancho():
    rows = build_variant_sku_mapping([
        {"sku": "CORBATA-BC/2013", "name": "CORBATA BC", "barcode": "", "price": "1", "cost": "1", "category": "ACCESORIOS", "attrs": {"Ancho Corbata": "CORBATA-BC/2013"}},
    ])
    assert rows[0]["Ancho Corbata"] == ""
    assert rows[0]["Talla"] == ""
    assert rows[0]["Parse Status"] == "UNPARSED"

