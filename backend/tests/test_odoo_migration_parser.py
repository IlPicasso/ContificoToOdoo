from app.odoo_migration.parser import parse_adams_sku, make_external_id


def test_parse_adams_suit():
    parsed = parse_adams_sku('210001/46')
    assert parsed.product_name == 'Terno 210001'
    assert parsed.category_odoo == 'Ropa / Ternos'
    assert parsed.talla == '46'


def test_parse_adams_shirt():
    parsed = parse_adams_sku('17601-15.5-S1')
    assert parsed.product_name == 'Camisa 17601'
    assert parsed.manga == 'S1 - 32/33'
    assert make_external_id(parsed) == 'adams_17601_155_s1'
