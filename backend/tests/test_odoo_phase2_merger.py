import csv
from pathlib import Path
import pytest
from app.odoo_migration.service import OdooMigrationService


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _read_csv(path: Path) -> list[dict]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


ODOO_EXPORT_COLS = ["id", "product_tmpl_id/id", "product_tmpl_id/name", "product_template_variant_value_ids"]
PHASE2_COLS = ["product_tmpl_id/id", "Internal Reference", "Barcode", "Name", "Variant Values", "Sales Price", "Cost"]


def _make_odoo_export(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "odoo_export.csv"
    _write_csv(path, ODOO_EXPORT_COLS, rows)
    return path


def _make_phase2_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "odoo_product_variant_internal_references.csv"
    _write_csv(path, PHASE2_COLS, rows)
    return path


def test_merger_basic_match(tmp_path: Path):
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_16_be6c1774",
            "product_tmpl_id/id": "__export__.product_template_9_90baf1a5",
            "product_tmpl_id/name": "H. CAMISA D/P BLACK, BRUNO CASSINI",
            "product_template_variant_value_ids": "Talla: 16.5,Manga de Camisa: S1 - 32/33",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_17605dc",
            "Internal Reference": "17605DC-16.5-S1",
            "Barcode": "17605DC-16.5-S1",
            "Name": "H. CAMISA D/P BLACK, BRUNO CASSINI",
            "Variant Values": "Talla: 16.5, Manga de Camisa: S1 - 32/33",
            "Sales Price": "82.52",
            "Cost": "0.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["matched"] == 1
    assert result["unmatched"] == 0
    assert result["unused_odoo_rows"] == 0

    out = _read_csv(tmp_path / "odoo_phase2_with_odoo_ids.csv")
    assert len(out) == 1
    assert out[0]["id"] == "__export__.product_product_16_be6c1774"
    assert out[0]["Internal Reference"] == "17605DC-16.5-S1"
    assert out[0]["product_tmpl_id/id"] == "__import__.product_template_17605dc"


def test_merger_normalizes_whitespace_around_commas(tmp_path: Path):
    """Odoo export has no space after comma; Phase 2 CSV has space — must still match."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_19_eb949bfb",
            "product_tmpl_id/id": "__export__.product_template_9_90baf1a5",
            "product_tmpl_id/name": "CAMISA TEST",
            "product_template_variant_value_ids": "Talla: 15,Manga de Camisa: S2 - 34/35",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_camisa_test",
            "Internal Reference": "CT-15-S2",
            "Barcode": "",
            "Name": "CAMISA TEST",
            "Variant Values": "Talla: 15, Manga de Camisa: S2 - 34/35",
            "Sales Price": "50.00",
            "Cost": "20.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["matched"] == 1
    out = _read_csv(tmp_path / "odoo_phase2_with_odoo_ids.csv")
    assert out[0]["id"] == "__export__.product_product_19_eb949bfb"


def test_merger_unmatched_phase2_row_reported(tmp_path: Path):
    """Phase 2 rows with no matching Odoo variant go to the unmatched report."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_1",
            "product_tmpl_id/id": "__export__.product_template_1",
            "product_tmpl_id/name": "CAMISA A",
            "product_template_variant_value_ids": "Talla: 15",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_a",
            "Internal Reference": "CA-15",
            "Barcode": "",
            "Name": "CAMISA A",
            "Variant Values": "Talla: 15",
            "Sales Price": "50.00",
            "Cost": "20.00",
        },
        {
            "product_tmpl_id/id": "__import__.product_template_b",
            "Internal Reference": "CB-M",
            "Barcode": "",
            "Name": "CAMISA B",
            "Variant Values": "Talla: M",
            "Sales Price": "50.00",
            "Cost": "20.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["matched"] == 1
    assert result["unmatched"] == 1

    unmatched = _read_csv(tmp_path / "odoo_phase2_merger_unmatched.csv")
    assert len(unmatched) == 1
    assert unmatched[0]["Internal Reference"] == "CB-M"
    assert "No matching" in unmatched[0]["match_failure_reason"]


def test_merger_unused_odoo_rows_reported(tmp_path: Path):
    """Odoo variants not present in Phase 2 are reported as unused."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_1",
            "product_tmpl_id/id": "__export__.product_template_1",
            "product_tmpl_id/name": "CAMISA X",
            "product_template_variant_value_ids": "Talla: 15",
        },
        {
            "id": "__export__.product_product_2",
            "product_tmpl_id/id": "__export__.product_template_1",
            "product_tmpl_id/name": "CAMISA X",
            "product_template_variant_value_ids": "Talla: 16",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_x",
            "Internal Reference": "CX-15",
            "Barcode": "",
            "Name": "CAMISA X",
            "Variant Values": "Talla: 15",
            "Sales Price": "50.00",
            "Cost": "20.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["matched"] == 1
    assert result["unused_odoo_rows"] == 1

    unused = _read_csv(tmp_path / "odoo_phase2_merger_unused_odoo.csv")
    assert len(unused) == 1
    assert unused[0]["odoo_ext_id"] == "__export__.product_product_2"
    assert "Talla: 16" in unused[0]["variant_values"]


def test_merger_output_has_id_as_first_column(tmp_path: Path):
    """The merged CSV must have 'id' as the first column for Odoo to treat it as an update."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_99",
            "product_tmpl_id/id": "__export__.product_template_99",
            "product_tmpl_id/name": "CORBATA NAVY",
            "product_template_variant_value_ids": "Ancho Corbata: 7 cm",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_navy",
            "Internal Reference": "NAV-007",
            "Barcode": "NAV-007",
            "Name": "CORBATA NAVY",
            "Variant Values": "Ancho Corbata: 7 cm",
            "Sales Price": "21.65",
            "Cost": "8.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    merged_path = tmp_path / "odoo_phase2_with_odoo_ids.csv"
    with merged_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header[0] == "id", f"First column must be 'id', got: {header[0]}"


def test_merger_minimal_csv_has_no_relational_columns(tmp_path: Path):
    """The minimal CSV must only have id, Internal Reference, Barcode, Sales Price, Cost.
    No Name or Variant Values — those trigger Odoo relational field validation errors."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_99",
            "product_tmpl_id/id": "__export__.product_template_99",
            "product_tmpl_id/name": "CORBATA NAVY",
            "product_template_variant_value_ids": "Ancho Corbata: 7 cm",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_navy",
            "Internal Reference": "NAV-007",
            "Barcode": "NAV-007",
            "Name": "CORBATA NAVY",
            "Variant Values": "Ancho Corbata: 7 cm",
            "Sales Price": "21.65",
            "Cost": "8.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    minimal_path = tmp_path / "odoo_phase2_with_odoo_ids_minimal.csv"
    assert minimal_path.exists(), "Minimal CSV must be generated"
    rows = _read_csv(minimal_path)
    assert len(rows) == 1
    assert rows[0]["id"] == "__export__.product_product_99"
    assert rows[0]["Internal Reference"] == "NAV-007"
    assert rows[0]["Barcode"] == "NAV-007"
    assert "Name" not in rows[0], "Minimal CSV must not have Name column"
    assert "Variant Values" not in rows[0], "Minimal CSV must not have Variant Values column"
    assert "product_tmpl_id/id" not in rows[0], "Minimal CSV must not have product_tmpl_id/id column"


def test_merger_case_insensitive_name_match(tmp_path: Path):
    """Template name matching is case-insensitive."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_5",
            "product_tmpl_id/id": "__export__.product_template_5",
            "product_tmpl_id/name": "h. camisa d/p black, bruno cassini",
            "product_template_variant_value_ids": "Talla: 16.5,Manga de Camisa: S1 - 32/33",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_17605dc",
            "Internal Reference": "17605DC-16.5-S1",
            "Barcode": "",
            "Name": "H. CAMISA D/P BLACK, BRUNO CASSINI",
            "Variant Values": "Talla: 16.5, Manga de Camisa: S1 - 32/33",
            "Sales Price": "82.52",
            "Cost": "0.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["matched"] == 1


SIMPLE_COLS = ["External ID", "Name", "Internal Reference", "Barcode", "Product Type"]


def _make_simple_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "odoo_product_templates_simple.csv"
    _write_csv(path, SIMPLE_COLS, rows)
    return path


def test_merger_simple_products_matched(tmp_path: Path):
    """Simple products (no variant values) are matched via product_tmpl_id/id."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_95867",
            "product_tmpl_id/id": "__import__.product_template_ykltb_sq10_2w_wht",
            "product_tmpl_id/name": "3 STEP GLASS DOWN LIGHT",
            "product_template_variant_value_ids": "",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [])
    simple_csv = _make_simple_csv(tmp_path, [
        {"External ID": "product_template_ykltb_sq10_2w_wht", "Name": "3 STEP GLASS DOWN LIGHT",
         "Internal Reference": "ykltb_sq10_2w_wht", "Barcode": "", "Product Type": "storable"},
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
        simple_csv=simple_csv,
    )

    assert result["simple_matched"] == 1
    assert result["simple_unmatched"] == 0
    assert result["matched"] == 0  # no variants

    rows = _read_csv(tmp_path / "odoo_phase2_simples_minimal.csv")
    assert len(rows) == 1
    assert rows[0]["id"] == "__export__.product_product_95867"
    assert rows[0]["Internal Reference"] == "ykltb_sq10_2w_wht"
    assert "Name" not in rows[0]
    assert "Variant Values" not in rows[0]


def test_merger_simple_unmatched_reported(tmp_path: Path):
    """Simple products not found in Odoo export go to simples_unmatched."""
    odoo_export = _make_odoo_export(tmp_path, [])
    phase2_csv = _make_phase2_csv(tmp_path, [])
    simple_csv = _make_simple_csv(tmp_path, [
        {"External ID": "product_template_xyz", "Name": "PROD XYZ",
         "Internal Reference": "XYZ-001", "Barcode": "", "Product Type": "storable"},
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
        simple_csv=simple_csv,
    )

    assert result["simple_matched"] == 0
    assert result["simple_unmatched"] == 1

    rows = _read_csv(tmp_path / "odoo_phase2_simples_unmatched.csv")
    assert rows[0]["Internal Reference"] == "XYZ-001"


def test_merger_without_simple_csv_returns_zero_simple_counts(tmp_path: Path):
    """When no simple_csv is passed, simple counts are zero and no error is raised."""
    odoo_export = _make_odoo_export(tmp_path, [
        {"id": "__export__.pp_1", "product_tmpl_id/id": "__export__.tmpl_1",
         "product_tmpl_id/name": "PROD", "product_template_variant_value_ids": "Talla: M"},
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["simple_matched"] == 0
    assert result["simple_unmatched"] == 0


def test_merger_primary_key_by_tmpl_id(tmp_path: Path):
    """When Phase 2 CSV and Odoo export share __import__.* template IDs, match by that key."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_9511",
            "product_tmpl_id/id": "__import__.product_template_9511tw",
            "product_tmpl_id/name": "BLUSA CQ BY CQ",
            "product_template_variant_value_ids": "Talla: S",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_9511tw",
            "Internal Reference": "9511TW-S",
            "Barcode": "",
            "Name": "BLUSA CQ BY CQ",
            "Variant Values": "Talla: S",
            "Sales Price": "46.88",
            "Cost": "0.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["matched"] == 1
    assert result["matched_by_tmpl_id"] == 1
    assert result["matched_by_name"] == 0
    out = _read_csv(tmp_path / "odoo_phase2_with_odoo_ids.csv")
    assert out[0]["id"] == "__export__.product_product_9511"
    assert out[0]["match_method"] == "tmpl_id"


def test_merger_fallback_to_name_when_tmpl_id_differs(tmp_path: Path):
    """Falls back to name matching when template IDs don't match (__export__ vs __import__)."""
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_42",
            "product_tmpl_id/id": "__export__.product_template_42_abc123",
            "product_tmpl_id/name": "CORBATA TEST",
            "product_template_variant_value_ids": "Talla: 7 cm",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [
        {
            "product_tmpl_id/id": "__import__.product_template_corb_test",
            "Internal Reference": "CORB-7",
            "Barcode": "",
            "Name": "CORBATA TEST",
            "Variant Values": "Talla: 7 cm",
            "Sales Price": "21.65",
            "Cost": "8.00",
        },
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["matched"] == 1
    assert result["matched_by_tmpl_id"] == 0
    assert result["matched_by_name"] == 1
    out = _read_csv(tmp_path / "odoo_phase2_with_odoo_ids.csv")
    assert out[0]["match_method"] == "name"


def test_merger_empty_phase2_produces_empty_output(tmp_path: Path):
    odoo_export = _make_odoo_export(tmp_path, [
        {
            "id": "__export__.product_product_1",
            "product_tmpl_id/id": "__export__.product_template_1",
            "product_tmpl_id/name": "CAMISA X",
            "product_template_variant_value_ids": "Talla: 15",
        },
    ])
    phase2_csv = _make_phase2_csv(tmp_path, [])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.merge_phase2_with_odoo_export(
        odoo_export_csv=odoo_export,
        phase2_csv=phase2_csv,
        output_folder=tmp_path,
    )

    assert result["matched"] == 0
    assert result["unmatched"] == 0
    assert result["unused_odoo_rows"] == 1
    assert _read_csv(tmp_path / "odoo_phase2_with_odoo_ids.csv") == []
