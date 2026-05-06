import csv
from pathlib import Path
from app.odoo_migration.service import OdooMigrationService


def _read_csv(path: Path):
    with path.open('r', newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f, delimiter=','))


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



def test_phase2_variant_csv_format_validation_has_no_errors_for_valid_output(tmp_path: Path):
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    variant_map_rows = [{
        "Product Template External ID": "product_template_camisa",
        "Product Template Name": "H. CAMISA D/P BLACK, BRUNO CASSINI",
        "Internal Reference": "17605DC-16.5-S1",
        "Barcode": "17605DC202591651",
        "Talla": "16.5",
        "Color": "Negro",
        "Manga de Camisa": "S1 - 32/33",
        "Marca": "Bruno Cassini",
        "Sales Price": "82.52",
        "Cost": "0.00",
    }]

    service._write_phase2_variant_internal_reference_outputs(
        folder=tmp_path,
        variant_map_rows=variant_map_rows,
        with_attr_rows=[{"Name": "H. CAMISA D/P BLACK, BRUNO CASSINI"}],
        simple_rows=[],
        stock_rows=[],
    )

    errors = _read_csv(tmp_path / "odoo_phase2_csv_format_errors.csv")
    assert errors == []


def test_phase2_variant_values_dedupe_and_internal_reference_fallback(tmp_path: Path):
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    variant_map_rows = [{
        "Product Template External ID": "product_template_blusa",
        "Product Template Name": "BLUSA M/3/4 P/DAMA BLANCA AZUL",
        "Internal Reference": "",
        "source_sku": "BLU-34-AZ-XS",
        "Barcode": "",
        "Talla": "XS,Talla: XS",
        "Color": "Azul",
        "Sales Price": "19.90",
        "Cost": "9.50",
    }]

    service._write_phase2_variant_internal_reference_outputs(
        folder=tmp_path,
        variant_map_rows=variant_map_rows,
        with_attr_rows=[{"Name": "BLUSA M/3/4 P/DAMA BLANCA AZUL"}],
        simple_rows=[],
        stock_rows=[],
    )

    out = _read_csv(tmp_path / "odoo_product_variant_internal_references.csv")
    assert out[0]["Internal Reference"] == "BLU-34-AZ-XS"
    assert out[0]["Barcode"] == "BLU-34-AZ-XS"
    assert out[0]["Variant Values"] == "Talla: XS, Color: Azul"
