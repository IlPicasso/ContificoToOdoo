from app.migration.product_mapper import map_contifico_product, parse_sku


def test_parse_suit_sku():
    madre, talla, manga = parse_sku("210001/46")
    assert madre == "Terno 210001"
    assert talla == "46"
    assert manga == ""


def test_parse_shirt_sku():
    madre, talla, manga = parse_sku("17601-15.5-S1")
    assert madre == "Camisa 17601"
    assert talla == "15.5"
    assert manga == "S1 - 32/33"


def test_map_contifico_product_stocks_and_defaults():
    row = map_contifico_product(
        {
            "sku": "17601-15.5-S2",
            "codigo_barras": "1234567890",
            "precio_venta": 39.99,
            "costo": 20,
            "stock_por_bodega": {"BPU": 5, "TUR": 2, "BAT": 1},
        }
    )

    assert row.producto_madre == "Camisa 17601"
    assert row.manga == "S2 - 34/35"
    assert row.marca == "Bruno Cassini"
    assert row.stock_bpu == 5
    assert row.stock_tur == 2
    assert row.stock_bat == 1
