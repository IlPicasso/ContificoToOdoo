import csv
from pathlib import Path
from app.odoo_migration.service import OdooMigrationService


def _read_csv(path: Path):
    with path.open('r', newline='', encoding='utf-8-sig') as f:
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


def test_internal_reference_update_csv_simple_and_variant(tmp_path: Path):
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    simple_rows = [
        {
            "External ID": "product_template_terno_1234",
            "Name": "TERNO BRUNO CASSINI",
            "Internal Reference": "1234",
            "Barcode": "111222333",
            "available_in_pos": "True",
        }
    ]
    variant_map_rows = [
        {
            "Product Template External ID": "product_template_camisa",
            "Product Template Name": "CAMISA BRUNO CASSINI",
            "Internal Reference": "17601-17.5-S2",
            "Barcode": "444555666",
            "Talla": "17.5",
            "Color": "",
            "Manga de Camisa": "S2 - 34/35",
            "Ancho Corbata": "",
            "Marca": "Bruno Cassini",
        }
    ]
    variant_rows_raw = [{"sku": "17601-17.5-S2", "para_pos": True}]

    service._write_internal_reference_update_csv(
        folder=tmp_path,
        simple_rows=simple_rows,
        variant_map_rows=variant_map_rows,
        variant_rows_raw=variant_rows_raw,
    )

    out = _read_csv(tmp_path / "product_internal_reference_update.csv")
    assert len(out) == 2

    simple = next(r for r in out if r["record_type"] == "simple_product")
    assert simple["Internal Reference"] == "1234"
    assert simple["External ID"] == "product_template_terno_1234"
    assert simple["Barcode"] == "111222333"
    assert simple["available_in_pos"] == "True"
    assert simple["Variant Values"] == ""

    variant = next(r for r in out if r["record_type"] == "variant_product")
    assert variant["Internal Reference"] == "17601-17.5-S2"
    assert variant["External ID"] == "product_template_camisa"
    assert "Talla: 17.5" in variant["Variant Values"]
    assert "Manga de Camisa: S2 - 34/35" in variant["Variant Values"]
    assert variant["available_in_pos"] == "True"

    conflicts = _read_csv(tmp_path / "product_internal_reference_barcode_conflicts.csv")
    assert conflicts == []


def test_internal_reference_update_barcode_conflict_clears_barcode(tmp_path: Path):
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    simple_rows = [
        {
            "External ID": "tmpl_a",
            "Name": "PROD A",
            "Internal Reference": "SKU-A",
            "Barcode": "SHARED-BC",
            "available_in_pos": "False",
        }
    ]
    variant_map_rows = [
        {
            "Product Template External ID": "tmpl_b",
            "Product Template Name": "PROD B",
            "Internal Reference": "SKU-B",
            "Barcode": "SHARED-BC",
            "Talla": "",
            "Color": "",
            "Manga de Camisa": "",
            "Ancho Corbata": "",
            "Marca": "",
        }
    ]

    service._write_internal_reference_update_csv(
        folder=tmp_path,
        simple_rows=simple_rows,
        variant_map_rows=variant_map_rows,
        variant_rows_raw=[],
    )

    out = _read_csv(tmp_path / "product_internal_reference_update.csv")
    # Both rows still present but barcode cleared due to conflict
    assert len(out) == 2
    assert all(r["Barcode"] == "" for r in out)
    # Internal Reference is preserved regardless
    skus = {r["Internal Reference"] for r in out}
    assert skus == {"SKU-A", "SKU-B"}

    conflicts = _read_csv(tmp_path / "product_internal_reference_barcode_conflicts.csv")
    assert len(conflicts) == 1
    assert conflicts[0]["barcode"] == "SHARED-BC"
    assert "SKU-A" in conflicts[0]["conflicting_internal_references"]
    assert "SKU-B" in conflicts[0]["conflicting_internal_references"]
    assert conflicts[0]["reason"] == "BARCODE_DUPLICADO"


def test_internal_reference_update_deduplicates_skus(tmp_path: Path):
    # A SKU in both simple_rows and variant_map_rows should appear only once
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    simple_rows = [
        {"External ID": "tmpl_x", "Name": "PROD X", "Internal Reference": "SKU-X", "Barcode": "BC-X", "available_in_pos": "True"}
    ]
    variant_map_rows = [
        {"Product Template External ID": "tmpl_x", "Product Template Name": "PROD X", "Internal Reference": "SKU-X",
         "Barcode": "BC-X", "Talla": "M", "Color": "", "Manga de Camisa": "", "Ancho Corbata": "", "Marca": ""}
    ]

    service._write_internal_reference_update_csv(
        folder=tmp_path,
        simple_rows=simple_rows,
        variant_map_rows=variant_map_rows,
        variant_rows_raw=[],
    )

    out = _read_csv(tmp_path / "product_internal_reference_update.csv")
    assert len(out) == 1
    assert out[0]["Internal Reference"] == "SKU-X"


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
    assert out[0]["Variant Values"] == "Talla: XS"


def test_phase2_variant_with_junk_talla_excluded_from_import(tmp_path: Path):
    """SKUs with talla values that pass _looks_like_valid_size but fail catalog validation
    end up as simple products. They must NOT appear in the Phase 2 variant import CSV
    even though build_variant_sku_mapping gives them a non-empty Variant Values."""
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    variant_map_rows = [
        # Valid camisa variant — template IS in with_attr_rows
        {
            "Product Template External ID": "product_template_17605dc",
            "Product Template Name": "H. CAMISA D/P BLACK, BRUNO CASSINI",
            "Internal Reference": "17605DC-16.5-S1",
            "Barcode": "",
            "Talla": "16.5",
            "Manga de Camisa": "S1 - 32/33",
            "Ancho Corbata": "",
            "Sales Price": "82.52",
            "Cost": "0.00",
        },
        # Battery with junk talla "7568" — template NOT in with_attr_rows (went to simple_rows)
        {
            "Product Template External ID": "product_template_cebat",
            "Product Template Name": "BATERIA CEBAT 7568",
            "Internal Reference": "CEBAT-7568",
            "Barcode": "",
            "Talla": "7568",
            "Manga de Camisa": "",
            "Ancho Corbata": "",
            "Sales Price": "15.00",
            "Cost": "8.00",
        },
    ]
    with_attr_rows = [{"External ID": "product_template_17605dc", "Name": "H. CAMISA D/P BLACK, BRUNO CASSINI"}]
    simple_rows = [{"Internal Reference": "CEBAT-7568"}]

    service._write_phase2_variant_internal_reference_outputs(
        folder=tmp_path,
        variant_map_rows=variant_map_rows,
        with_attr_rows=with_attr_rows,
        simple_rows=simple_rows,
        stock_rows=[],
    )

    out = _read_csv(tmp_path / "odoo_product_variant_internal_references.csv")
    skus = [r["Internal Reference"] for r in out]
    assert "17605DC-16.5-S1" in skus, "Valid camisa should be in Phase 2 import"
    assert "CEBAT-7568" not in skus, "Battery with junk talla must be excluded from Phase 2 import"

    validation = _read_csv(tmp_path / "odoo_phase2_variant_internal_reference_validation.csv")
    battery_warnings = [r for r in validation if r["internal_reference"] == "CEBAT-7568"]
    assert any(r["issue_type"] == "Product Template Name not found in Fase 1 with attributes" for r in battery_warnings)


def test_phase2_variant_canonical_name_used_when_contifico_names_differ_by_sleeve(tmp_path: Path):
    """En Contifico, las variantes S1 y S2 de una misma camisa pueden tener nombres
    distintos (ej. 'CAMISA X 32-33' vs 'CAMISA X 34-35'). El seed del template usa
    el nombre S1, por lo que las variantes S2 no coinciden por nombre. El fix resuelve
    el nombre canónico via External ID y lo usa en el CSV de importación."""
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    variant_map_rows = [
        {
            "Product Template External ID": "product_template_17605dc",
            "Product Template Name": "H. CAMISA D/P BLACK BRUNO CASSINI 32-33",
            "Internal Reference": "17605DC-16.5-S1",
            "Barcode": "BC1",
            "Talla": "16.5",
            "Manga de Camisa": "S1 - 32/33",
            "Ancho Corbata": "",
            "Sales Price": "82.52",
            "Cost": "0.00",
        },
        {
            "Product Template External ID": "product_template_17605dc",
            "Product Template Name": "H. CAMISA D/P BLACK BRUNO CASSINI 34-35",
            "Internal Reference": "17605DC-16.5-S2",
            "Barcode": "BC2",
            "Talla": "16.5",
            "Manga de Camisa": "S2 - 34/35",
            "Ancho Corbata": "",
            "Sales Price": "82.52",
            "Cost": "0.00",
        },
    ]
    # with_attr_rows tiene el nombre del seed (S1), no el S2
    with_attr_rows = [{"External ID": "product_template_17605dc", "Name": "H. CAMISA D/P BLACK BRUNO CASSINI 32-33"}]

    service._write_phase2_variant_internal_reference_outputs(
        folder=tmp_path,
        variant_map_rows=variant_map_rows,
        with_attr_rows=with_attr_rows,
        simple_rows=[],
        stock_rows=[],
    )

    out = _read_csv(tmp_path / "odoo_product_variant_internal_references.csv")
    assert len(out) == 2, "Ambas variantes (S1 y S2) deben estar en el CSV"

    s1 = next(r for r in out if r["Internal Reference"] == "17605DC-16.5-S1")
    s2 = next(r for r in out if r["Internal Reference"] == "17605DC-16.5-S2")

    # Ambas deben usar el nombre canónico del seed (S1)
    assert s1["Name"] == "H. CAMISA D/P BLACK BRUNO CASSINI 32-33"
    assert s2["Name"] == "H. CAMISA D/P BLACK BRUNO CASSINI 32-33", \
        "La variante S2 debe usar el nombre canónico del template, no su nombre propio de Contifico"

    assert "Manga de Camisa: S1 - 32/33" in s1["Variant Values"]
    assert "Manga de Camisa: S2 - 34/35" in s2["Variant Values"]


def test_phase2_variant_deduplicates_sku_appearing_in_multiple_contifico_records(tmp_path: Path):
    """Cuando el mismo SKU aparece en dos registros Contifico distintos (ej. variante S1
    presente tanto en el producto '32-33' como en el '34-35'), debe aparecer UNA sola
    vez en el CSV de importación."""
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    variant_map_rows = [
        {
            "Product Template External ID": "product_template_ht8811_3",
            "Product Template Name": "H. CAMISA P/S BLUE BRUNO CASSINI 32-33",
            "Internal Reference": "HT8811-3-16-S1",
            "Barcode": "BC1",
            "Talla": "16",
            "Manga de Camisa": "S1 - 32/33",
            "Ancho Corbata": "",
            "Sales Price": "56.43",
            "Cost": "0.00",
        },
        # Same SKU from the S2 Contifico record
        {
            "Product Template External ID": "product_template_ht8811_3",
            "Product Template Name": "H. CAMISA P/S BLUE BRUNO CASSINI 34-35",
            "Internal Reference": "HT8811-3-16-S1",
            "Barcode": "BC1",
            "Talla": "16",
            "Manga de Camisa": "S1 - 32/33",
            "Ancho Corbata": "",
            "Sales Price": "56.43",
            "Cost": "0.00",
        },
    ]
    with_attr_rows = [{"External ID": "product_template_ht8811_3", "Name": "H. CAMISA P/S BLUE BRUNO CASSINI 32-33"}]

    service._write_phase2_variant_internal_reference_outputs(
        folder=tmp_path,
        variant_map_rows=variant_map_rows,
        with_attr_rows=with_attr_rows,
        simple_rows=[],
        stock_rows=[],
    )

    out = _read_csv(tmp_path / "odoo_product_variant_internal_references.csv")
    assert len(out) == 1, "SKU duplicado debe aparecer solo una vez en el CSV de importación"
    assert out[0]["Internal Reference"] == "HT8811-3-16-S1"

    validation = _read_csv(tmp_path / "odoo_phase2_variant_internal_reference_validation.csv")
    deduped_warnings = [r for r in validation if r["issue_type"] == "Duplicate SKU deduplicated"]
    assert len(deduped_warnings) == 1, "Debe haber un warning de deduplicación"
    assert deduped_warnings[0]["internal_reference"] == "HT8811-3-16-S1"


def test_phase2_duplicate_template_names_auto_suffixed(tmp_path: Path):
    """Cuando dos External IDs distintos comparten el mismo nombre canónico en Odoo,
    el segundo recibe un sufijo automático (ej. ' (ht2231_7)') para que Phase 2 pueda
    distinguirlos. Se genera odoo_phase1_template_renames.csv con los renames necesarios."""
    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    variant_map_rows = [
        {
            "Product Template External ID": "product_template_ht8811_1",
            "Product Template Name": "H. CAMISA P/S WHITE BRUNO CASSINI 32-33",
            "Internal Reference": "HT8811-1-16-S1",
            "Barcode": "BC1",
            "Talla": "16",
            "Manga de Camisa": "S1 - 32/33",
            "Ancho Corbata": "",
            "Sales Price": "56.43",
            "Cost": "0.00",
        },
        {
            "Product Template External ID": "product_template_ht2231_7",
            "Product Template Name": "H. CAMISA P/S WHITE BRUNO CASSINI 32-33",
            "Internal Reference": "HT2231-7-16-S1",
            "Barcode": "BC2",
            "Talla": "16",
            "Manga de Camisa": "S1 - 32/33",
            "Ancho Corbata": "",
            "Sales Price": "56.43",
            "Cost": "0.00",
        },
    ]
    with_attr_rows = [
        {"External ID": "product_template_ht8811_1", "Name": "H. CAMISA P/S WHITE BRUNO CASSINI 32-33"},
        {"External ID": "product_template_ht2231_7", "Name": "H. CAMISA P/S WHITE BRUNO CASSINI 32-33"},
    ]

    service._write_phase2_variant_internal_reference_outputs(
        folder=tmp_path,
        variant_map_rows=variant_map_rows,
        with_attr_rows=with_attr_rows,
        simple_rows=[],
        stock_rows=[],
    )

    out = _read_csv(tmp_path / "odoo_product_variant_internal_references.csv")
    assert len(out) == 2, "Ambos SKUs deben estar en el CSV"

    ht8811 = next(r for r in out if r["Internal Reference"] == "HT8811-1-16-S1")
    ht2231 = next(r for r in out if r["Internal Reference"] == "HT2231-7-16-S1")

    assert ht8811["Name"] == "H. CAMISA P/S WHITE BRUNO CASSINI 32-33"
    assert ht2231["Name"] == "H. CAMISA P/S WHITE BRUNO CASSINI 32-33 (ht2231_7)"

    renames = _read_csv(tmp_path / "odoo_phase1_template_renames.csv")
    assert len(renames) == 1
    assert renames[0]["external_id"] == "product_template_ht2231_7"
    assert renames[0]["old_name"] == "H. CAMISA P/S WHITE BRUNO CASSINI 32-33"
    assert renames[0]["new_name"] == "H. CAMISA P/S WHITE BRUNO CASSINI 32-33 (ht2231_7)"
