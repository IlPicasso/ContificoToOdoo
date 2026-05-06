from pathlib import Path
from app.odoo_migration.service import OdooMigrationService


def _read_csv(path: Path):
    lines = path.read_text(encoding='utf-8').splitlines()
    header = lines[0].split(',')
    rows = []
    for ln in lines[1:]:
        parts = ln.split(',')
        rows.append(dict(zip(header, parts)))
    return rows


def test_phase2_variant_outputs_are_generated(tmp_path: Path):
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    variant_map_rows = [
        {
            "Product Template External ID": "product_template_camisa",
            "Product Template Name": "CAMISA BRUNO CASSINI",
            "Internal Reference": "17601-17.5-S2",
            "Barcode": "",
            "Talla": "17.5",
            "Color": "Blanco",
            "Manga de Camisa": "S2 - 34/35",
            "Ancho Corbata": "",
            "Marca": "Bruno Cassini",
            "Sales Price": "198.17",
            "Cost": "0.00",
        }
    ]
    with_attr_rows = [{"Name": "CAMISA BRUNO CASSINI"}]
    simple_rows = [{"Internal Reference": "SIMPLE-1"}]
    stock_rows = [
        {"Product / Internal Reference": "17601-17.5-S2", "Location": "BPU/Existencias", "Inventory Quantity": "1.00"},
        {"Product / Internal Reference": "MISSING-SKU", "Location": "BPU/Existencias", "Inventory Quantity": "1.00"},
    ]

    service._write_phase2_variant_internal_reference_outputs(
        folder=tmp_path,
        variant_map_rows=variant_map_rows,
        with_attr_rows=with_attr_rows,
        simple_rows=simple_rows,
        stock_rows=stock_rows,
    )

    out = _read_csv(tmp_path / "odoo_product_variant_internal_references.csv")
    assert out[0]["Internal Reference"] == "17601-17.5-S2"
    assert out[0]["Barcode"] == "17601-17.5-S2"
    assert out[0]["Name"] == "CAMISA BRUNO CASSINI"
    assert "Talla: 17.5" in out[0]["Variant Values"]

    missing = _read_csv(tmp_path / "odoo_phase2_missing_stock_references.csv")
    assert missing[0]["stock_internal_reference"] == "MISSING-SKU"
