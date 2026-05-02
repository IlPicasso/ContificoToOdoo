from app.odoo_migration.rules import (
    parse_shirt_sku, parse_suit_sku, parse_blazer_sku, parse_tie_sku,
    parse_bowtie_sku, parse_fajin_sku, parse_generic_size,
    should_exclude_zero_stock, build_product_values
)


def test_real_patterns():
    assert parse_shirt_sku('17601-15.5-S1')['manga'] == 'S1 - 32/33'
    assert parse_shirt_sku('17601-15.5-S2')['manga'] == 'S2 - 34/35'
    assert parse_suit_sku('210001/46')['talla'] == '46'
    assert parse_suit_sku('007-13BC-2/46')['talla'] == '46'
    assert parse_blazer_sku('007-51/68')['talla'] == '68'
    assert parse_tie_sku('MF11812/4-6')['ancho_corbata'] == '6'
    assert parse_tie_sku('MF11887/20-7.5')['ancho_corbata'] == '7.5'
    assert parse_tie_sku('#0050/23-7.5')['ancho_corbata'] == '7.5'
    assert parse_bowtie_sku('MF11829/1-CO')['product_name'].startswith('Corbatín')
    assert parse_fajin_sku('MF11829/1-FJ')['product_name'].startswith('Set Corbatín + Faja')
    assert parse_generic_size('006-ZOLEY-PANT/L') == 'L'
    assert parse_generic_size('002-T29') == '29'


def test_zero_stock_rule_and_values():
    assert should_exclude_zero_stock(0)
    assert not should_exclude_zero_stock(0.01)
    assert build_product_values(talla='46', marca='BRUNO CASSINI', color='Azul') == 'Talla:46,Marca:BRUNO CASSINI,Color:Azul'


def test_group_stock_rule_base_key():
    from app.odoo_migration.service import OdooMigrationService
    assert OdooMigrationService._base_group_key('MF11829/1-CO', '') == 'MF11829/1'
    assert OdooMigrationService._base_group_key('MF11829/1-FJ', '') == 'MF11829/1'


def test_stock_fallback_from_cantidad_stock():
    from app.odoo_migration.service import OdooMigrationService
    stock = OdooMigrationService._extract_stock_by_warehouse({'cantidad_stock':'1.0'})
    assert stock['BPU'] == 1.0
