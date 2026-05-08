import csv
from pathlib import Path
from app.odoo_migration.service import OdooMigrationService


def _write_csv(path: Path, fieldnames: list, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def _read_csv(path: Path) -> list:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


ODOO_EXPORT_COLS = ["id", "is_favorite", "default_code", "barcode", "name",
                    "product_template_variant_value_ids", "lst_price", "standard_price", "qty_available"]
SIMPLE_COLS = ["External ID", "Name", "Internal Reference", "Barcode", "Product Type"]
VARIANT_COLS = ["product_tmpl_id/id", "Internal Reference", "Barcode", "Name", "Variant Values", "Sales Price", "Cost"]


def _setup_run(tmp_path: Path, simple_skus: list[str], variant_skus: list[str]) -> Path:
    run_folder = tmp_path / "run"
    run_folder.mkdir()
    _write_csv(run_folder / "odoo_product_templates_simple.csv", SIMPLE_COLS, [
        {"External ID": f"tmpl_{s}", "Name": f"Prod {s}", "Internal Reference": s, "Barcode": "", "Product Type": "storable"}
        for s in simple_skus
    ])
    _write_csv(run_folder / "odoo_product_variant_internal_references.csv", VARIANT_COLS, [
        {"product_tmpl_id/id": f"__import__.tmpl_{v}", "Internal Reference": v, "Barcode": "", "Name": f"Variante {v}", "Variant Values": "Talla: M", "Sales Price": "10.00", "Cost": "5.00"}
        for v in variant_skus
    ])
    return run_folder


def _make_odoo_export(tmp_path: Path, skus: list[str]) -> Path:
    path = tmp_path / "odoo_export.csv"
    _write_csv(path, ODOO_EXPORT_COLS, [
        {"id": f"__export__.pp_{s}", "is_favorite": "False", "default_code": s, "barcode": "",
         "name": f"Producto {s}", "product_template_variant_value_ids": "", "lst_price": "10.00",
         "standard_price": "5.00", "qty_available": "3.0"}
        for s in skus
    ])
    return path


def test_compare_basic_sets(tmp_path: Path):
    run_folder = _setup_run(tmp_path, simple_skus=["SIMPLE-1", "SIMPLE-2"], variant_skus=["VAR-A", "VAR-B"])
    odoo_export = _make_odoo_export(tmp_path, ["SIMPLE-1", "VAR-A", "ODOO-ONLY-1"])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.compare_inventory_with_odoo_export(
        run_folder=run_folder,
        odoo_export_csv=odoo_export,
        output_folder=tmp_path,
    )

    assert result["contifico_total"] == 4  # SIMPLE-1, SIMPLE-2, VAR-A, VAR-B
    assert result["odoo_total"] == 3       # SIMPLE-1, VAR-A, ODOO-ONLY-1
    assert result["in_both"] == 2          # SIMPLE-1, VAR-A
    assert result["only_in_contifico"] == 2  # SIMPLE-2, VAR-B
    assert result["only_in_odoo"] == 1      # ODOO-ONLY-1


def test_compare_only_in_contifico_csv(tmp_path: Path):
    run_folder = _setup_run(tmp_path, simple_skus=["S1", "S2"], variant_skus=[])
    odoo_export = _make_odoo_export(tmp_path, ["S1"])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    service.compare_inventory_with_odoo_export(
        run_folder=run_folder, odoo_export_csv=odoo_export, output_folder=tmp_path,
    )

    rows = _read_csv(tmp_path / "odoo_compare_only_in_contifico.csv")
    skus = {r["Internal Reference"] for r in rows}
    assert "S2" in skus
    assert "S1" not in skus


def test_compare_only_in_odoo_csv(tmp_path: Path):
    run_folder = _setup_run(tmp_path, simple_skus=["S1"], variant_skus=[])
    odoo_export = _make_odoo_export(tmp_path, ["S1", "ODOO-X", "ODOO-Y"])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    service.compare_inventory_with_odoo_export(
        run_folder=run_folder, odoo_export_csv=odoo_export, output_folder=tmp_path,
    )

    rows = _read_csv(tmp_path / "odoo_compare_only_in_odoo.csv")
    skus = {r["default_code"] for r in rows}
    assert "ODOO-X" in skus
    assert "ODOO-Y" in skus
    assert "S1" not in skus


def test_compare_in_both_csv(tmp_path: Path):
    run_folder = _setup_run(tmp_path, simple_skus=["S1", "S2"], variant_skus=["V1"])
    odoo_export = _make_odoo_export(tmp_path, ["S1", "V1", "EXTRA"])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    service.compare_inventory_with_odoo_export(
        run_folder=run_folder, odoo_export_csv=odoo_export, output_folder=tmp_path,
    )

    rows = _read_csv(tmp_path / "odoo_compare_in_both.csv")
    skus = {r["Internal Reference"] for r in rows}
    assert "S1" in skus
    assert "V1" in skus
    assert "S2" not in skus
    assert "EXTRA" not in skus


def test_compare_skips_empty_default_code(tmp_path: Path):
    """Odoo rows with empty default_code must be ignored."""
    run_folder = _setup_run(tmp_path, simple_skus=["S1"], variant_skus=[])
    path = tmp_path / "odoo_export.csv"
    _write_csv(path, ODOO_EXPORT_COLS, [
        {"id": "__export__.pp_1", "is_favorite": "False", "default_code": "S1",
         "barcode": "", "name": "Prod S1", "product_template_variant_value_ids": "",
         "lst_price": "10.00", "standard_price": "5.00", "qty_available": "1.0"},
        {"id": "__export__.pp_2", "is_favorite": "False", "default_code": "",
         "barcode": "", "name": "Sin referencia", "product_template_variant_value_ids": "",
         "lst_price": "10.00", "standard_price": "5.00", "qty_available": "0.0"},
    ])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.compare_inventory_with_odoo_export(
        run_folder=run_folder, odoo_export_csv=path, output_folder=tmp_path,
    )

    assert result["odoo_total"] == 1  # Only S1, not the empty-code row


def test_compare_case_insensitive(tmp_path: Path):
    """SKU matching must be case-insensitive."""
    run_folder = _setup_run(tmp_path, simple_skus=["sku-ABC"], variant_skus=[])
    odoo_export = _make_odoo_export(tmp_path, ["SKU-ABC"])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.compare_inventory_with_odoo_export(
        run_folder=run_folder, odoo_export_csv=odoo_export, output_folder=tmp_path,
    )

    assert result["in_both"] == 1
    assert result["only_in_contifico"] == 0
    assert result["only_in_odoo"] == 0


def test_compare_preview_capped_at_30(tmp_path: Path):
    """Preview lists must be capped at 30 items each."""
    skus = [f"SKU-{i:03d}" for i in range(50)]
    run_folder = _setup_run(tmp_path, simple_skus=skus, variant_skus=[])
    odoo_export = _make_odoo_export(tmp_path, [])

    service = OdooMigrationService(client=None)  # type: ignore[arg-type]
    result = service.compare_inventory_with_odoo_export(
        run_folder=run_folder, odoo_export_csv=odoo_export, output_folder=tmp_path,
    )

    assert len(result["preview_only_contifico"]) == 30
    assert result["only_in_contifico"] == 50
