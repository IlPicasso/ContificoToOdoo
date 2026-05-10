"""Standalone inventory-quantity comparator.

Compares stock levels between an Odoo inventory export and a Contifico
inventory report (multiple source formats supported).

Supported Contifico sources:
  csv_simple   – ReporteSaldosInventario.csv       (semicolon, 5 header rows)
  csv_bodegas  – ReporteSaldosInventarioPorBodega.csv (semicolon, 5 header rows)
  raw_log      – raw.log (newline-delimited JSON pages, field: cantidad_stock)

Supported Odoo sources:
  auto-detected from column names:
    • Simple export : Internal Reference | name_odoo | qty_available | barcode
    • Full export   : id | default_code | name | qty_available | ...
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_qty(value: str) -> float:
    """Convert a Spanish-locale number string to float."""
    v = str(value or "0").strip().replace(",", ".").replace(" ", "")
    try:
        return float(v)
    except ValueError:
        return 0.0


def _open_csv(path: Path) -> io.TextIOWrapper:
    """Open a CSV that may be UTF-8, UTF-8-BOM, or Latin-1."""
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            f = path.open("r", newline="", encoding=enc)
            f.read(512)
            f.seek(0)
            return f
        except UnicodeDecodeError:
            pass
    return path.open("r", newline="", encoding="latin-1", errors="replace")


# ──────────────────────────────────────────────────────────────────────────────
# Odoo loader
# ──────────────────────────────────────────────────────────────────────────────

def load_odoo_stock(path: Path) -> dict[str, dict]:
    """Return {sku_lower: {sku, name, qty, barcode}} from an Odoo product export."""
    result: dict[str, dict] = {}
    with _open_csv(path) as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Detect format: simple vs full export
        if "Internal Reference" in headers:
            sku_col, qty_col, name_col, bc_col = (
                "Internal Reference", "qty_available", "name_odoo", "barcode"
            )
        elif "default_code" in headers:
            sku_col, qty_col, name_col, bc_col = (
                "default_code", "qty_available", "name", "barcode"
            )
        else:
            raise ValueError(
                f"Formato de exportación Odoo no reconocido. "
                f"Se esperaba 'Internal Reference' o 'default_code'. "
                f"Columnas encontradas: {headers}"
            )

        for row in reader:
            sku = str(row.get(sku_col) or "").strip()
            if not sku:
                continue
            key = sku.casefold()
            if key not in result:
                result[key] = {
                    "sku": sku,
                    "name": str(row.get(name_col) or "").strip(),
                    "qty": _parse_qty(row.get(qty_col) or "0"),
                    "barcode": str(row.get(bc_col) or "").strip(),
                }
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Contifico loaders
# ──────────────────────────────────────────────────────────────────────────────

_CONTIFICO_HEADER_ROWS = 5  # company, report title, date, blank, (optional group row)

_BODEGAS_WAREHOUSE_COLS = [
    "Almacenes",
    "Bodegas Principales",
    "Bodegas Showroom",
    "Oficina Adams",
    "Bodega Mercaderia en Transito",
    "Bodega 2",
    "Bodega Web",
    "BODEGAS BATAN",
    "Bodegas Muestras",
    "BODEGAS TEMPORALES LAVANDERIA",
]

_BODEGAS_WAREHOUSE_KEYS = [
    "almacenes",
    "bodegas_principales",
    "showroom",
    "oficina_adams",
    "en_transito",
    "bodega_2",
    "bodega_web",
    "batan",
    "muestras",
    "temporales_lavanderia",
]


def _skip_contifico_headers(f: io.TextIOWrapper, delimiter: str = ";") -> csv.DictReader:
    """Skip the Contifico multi-row file header and return a DictReader."""
    lines = []
    for _ in range(_CONTIFICO_HEADER_ROWS):
        lines.append(f.readline())
    return csv.DictReader(f, delimiter=delimiter)


def _normalize_header(h: str) -> str:
    """Strip BOM, whitespace, and common accent variations."""
    return (
        h.strip()
        .lstrip("﻿")
        .replace("\r", "")
        .replace("ó", "o")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ú", "u")
        .replace("Ó", "O")
        .replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ú", "U")
    )


def _find_col(row: dict, *candidates: str) -> str | None:
    """Case-insensitive lookup across normalized column names."""
    norm = {_normalize_header(k): k for k in row.keys()}
    for c in candidates:
        nc = _normalize_header(c)
        if nc in norm:
            return norm[nc]
    return None


def load_contifico_simple(path: Path) -> dict[str, dict]:
    """Load ReporteSaldosInventario.csv → {sku_lower: {sku, name, qty, categoria, marca}}."""
    result: dict[str, dict] = {}
    with _open_csv(path) as f:
        reader = _skip_contifico_headers(f)
        for row in reader:
            sku_col = _find_col(row, "Código", "Codigo", "Codigo Catalogo")
            stock_col = _find_col(row, "Stock")
            nombre_col = _find_col(row, "Nombre")
            cat_col = _find_col(row, "Categoría", "Categoria")
            marca_col = _find_col(row, "Marca")

            if not sku_col:
                continue
            sku = str(row.get(sku_col) or "").strip()
            if not sku:
                continue
            key = sku.casefold()
            if key not in result:
                result[key] = {
                    "sku": sku,
                    "name": str(row.get(nombre_col) or "").strip() if nombre_col else "",
                    "qty": _parse_qty(row.get(stock_col) or "0") if stock_col else 0.0,
                    "categoria": str(row.get(cat_col) or "").strip() if cat_col else "",
                    "marca": str(row.get(marca_col) or "").strip() if marca_col else "",
                }
    return result


def load_contifico_bodegas(path: Path) -> dict[str, dict]:
    """Load ReporteSaldosInventarioPorBodega.csv → {sku_lower: {sku, name, qty, warehouses...}}."""
    result: dict[str, dict] = {}
    with _open_csv(path) as f:
        reader = _skip_contifico_headers(f)
        for row in reader:
            sku_col = _find_col(row, "Código", "Codigo")
            total_col = _find_col(row, "Total General")
            nombre_col = _find_col(row, "Producto", "Nombre")
            cat_col = _find_col(row, "Categoría", "Categoria")
            marca_col = _find_col(row, "Marca")

            if not sku_col:
                continue
            sku = str(row.get(sku_col) or "").strip()
            if not sku:
                continue

            qty_total = _parse_qty(row.get(total_col) or "0") if total_col else 0.0

            warehouses: dict[str, float] = {}
            for col_name, key in zip(_BODEGAS_WAREHOUSE_COLS, _BODEGAS_WAREHOUSE_KEYS):
                found = _find_col(row, col_name)
                if found:
                    warehouses[key] = _parse_qty(row.get(found) or "0")

            key = sku.casefold()
            if key not in result:
                result[key] = {
                    "sku": sku,
                    "name": str(row.get(nombre_col) or "").strip() if nombre_col else "",
                    "qty": qty_total,
                    "categoria": str(row.get(cat_col) or "").strip() if cat_col else "",
                    "marca": str(row.get(marca_col) or "").strip() if marca_col else "",
                    **{f"wh_{k}": v for k, v in warehouses.items()},
                }
    return result


def load_contifico_raw_log(path: Path) -> dict[str, dict]:
    """Load raw.log (newline-delimited JSON pages) → {sku_lower: {sku, name, qty, ...}}."""
    result: dict[str, dict] = {}
    with _open_csv(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            products = obj.get("response", []) if isinstance(obj, dict) else []
            if isinstance(obj, list):
                products = obj
            for p in products:
                if not isinstance(p, dict):
                    continue
                sku = str(p.get("codigo") or "").strip()
                if not sku:
                    continue
                key = sku.casefold()
                if key not in result:
                    result[key] = {
                        "sku": sku,
                        "name": str(p.get("nombre") or "").strip(),
                        "qty": float(p.get("cantidad_stock") or 0),
                        "marca": str(p.get("marca_nombre") or "").strip(),
                        "categoria": "",
                        "barcode": str(p.get("codigo_barra") or "").strip(),
                        "precio": float(p.get("pvp1") or 0),
                    }
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Odoo SKU loader (no qty needed for presence comparison)
# ──────────────────────────────────────────────────────────────────────────────

def load_odoo_skus(path: Path) -> dict[str, dict]:
    """Return {sku_lower: {sku, name, barcode}} from an Odoo product export.

    Accepts the same formats as load_odoo_stock but ignores qty_available.
    Also accepts the minimal format: Internal Reference | name_odoo | barcode
    """
    result: dict[str, dict] = {}
    with _open_csv(path) as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        if "Internal Reference" in headers:
            sku_col, name_col, bc_col = "Internal Reference", "name_odoo", "barcode"
        elif "default_code" in headers:
            sku_col, name_col, bc_col = "default_code", "name", "barcode"
        else:
            raise ValueError(
                f"Formato Odoo no reconocido. "
                f"Se esperaba 'Internal Reference' o 'default_code'. "
                f"Columnas encontradas: {headers}"
            )

        for row in reader:
            sku = str(row.get(sku_col) or "").strip()
            if not sku:
                continue
            key = sku.casefold()
            if key not in result:
                result[key] = {
                    "sku": sku,
                    "name": str(row.get(name_col) or "").strip(),
                    "barcode": str(row.get(bc_col) or "").strip(),
                    "qty": _parse_qty(row.get("qty_available") or "0"),
                }
    return result


# ──────────────────────────────────────────────────────────────────────────────
# SKU presence comparator (Sección A)
# ──────────────────────────────────────────────────────────────────────────────

def compare_skus(
    *,
    odoo_path: Path,
    contifico_path: Path,
    source_type: str,
    output_folder: Path,
    filter_zero_stock: bool = False,
) -> dict[str, Any]:
    """Compare SKU presence between Odoo and Contifico (no qty comparison).

    Returns which SKUs are only in Contifico (missing from Odoo), only in Odoo,
    or in both. Writes three CSVs in output_folder.

    source_type: 'csv_simple' | 'csv_bodegas' | 'raw_log'
    filter_zero_stock: when True, Contifico SKUs with qty == 0 are excluded.
    """
    output_folder.mkdir(parents=True, exist_ok=True)

    loaders = {
        "csv_simple": load_contifico_simple,
        "csv_bodegas": load_contifico_bodegas,
        "raw_log": load_contifico_raw_log,
    }
    if source_type not in loaders:
        raise ValueError(f"source_type inválido: {source_type!r}. Usa: {list(loaders)}")

    odoo = load_odoo_skus(odoo_path)
    contifico = loaders[source_type](contifico_path)

    contifico_keys = set(contifico.keys())
    odoo_keys = set(odoo.keys())

    raw_only_contifico = contifico_keys - odoo_keys
    only_odoo_keys = sorted(odoo_keys - contifico_keys)
    both_keys = sorted(contifico_keys & odoo_keys)

    # Split "only in Contifico" into real gaps (stock > 0) vs zero-stock-both
    # (stock = 0 in Contifico and absent from Odoo → both sides agree on no stock)
    if filter_zero_stock:
        only_contifico_keys = sorted(
            k for k in raw_only_contifico if contifico[k].get("qty", 0) != 0
        )
        zero_both_keys = sorted(
            k for k in raw_only_contifico if contifico[k].get("qty", 0) == 0
        )
    else:
        only_contifico_keys = sorted(raw_only_contifico)
        zero_both_keys = []

    def _ctf_row(k: str) -> dict:
        return {
            "SKU": contifico[k]["sku"],
            "Nombre Contifico": contifico[k].get("name", ""),
            "Categoria": contifico[k].get("categoria", ""),
            "Marca": contifico[k].get("marca", ""),
            "Stock Contifico": contifico[k].get("qty", 0),
        }

    only_c_rows  = [_ctf_row(k) for k in only_contifico_keys]
    zero_b_rows  = [_ctf_row(k) for k in zero_both_keys]

    only_o_rows = [
        {
            "SKU": odoo[k]["sku"],
            "Nombre Odoo": odoo[k].get("name", ""),
            "Barcode": odoo[k].get("barcode", ""),
            "Stock Odoo": odoo[k].get("qty", 0),
        }
        for k in only_odoo_keys
    ]

    both_rows = [
        {
            "SKU": contifico[k]["sku"],
            "Nombre Contifico": contifico[k].get("name", ""),
            "Nombre Odoo": odoo[k].get("name", ""),
            "Barcode Odoo": odoo[k].get("barcode", ""),
        }
        for k in both_keys
    ]

    def write_csv(filepath: Path, rows: list[dict]) -> None:
        if not rows:
            filepath.write_text("(sin datos)\n", encoding="utf-8")
            return
        with filepath.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(output_folder / "sku_compare_only_contifico.csv", only_c_rows)
    write_csv(output_folder / "sku_compare_only_odoo.csv", only_o_rows)
    write_csv(output_folder / "sku_compare_in_both.csv", both_rows)
    write_csv(output_folder / "sku_compare_zero_both.csv", zero_b_rows)

    return {
        "contifico_total_skus": len(contifico),
        "odoo_total_skus": len(odoo),
        "in_both": len(both_keys),
        "only_in_contifico": len(only_contifico_keys),
        "only_in_odoo": len(only_odoo_keys),
        "coincide_zero_stock": len(zero_both_keys),
        "filter_zero_stock": filter_zero_stock,
        "source_type": source_type,
        "preview_only_contifico": [r["SKU"] for r in only_c_rows[:30]],
        "preview_only_odoo": [r["SKU"] for r in only_o_rows[:30]],
        "preview_in_both": [r["SKU"] for r in both_rows[:30]],
        "preview_zero_both": [r["SKU"] for r in zero_b_rows[:30]],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Main comparator
# ──────────────────────────────────────────────────────────────────────────────

def compare_stock(
    *,
    odoo_path: Path,
    contifico_path: Path,
    source_type: str,
    output_folder: Path,
) -> dict[str, Any]:
    """Compare Odoo vs Contifico inventory quantities.

    Args:
        odoo_path:        Odoo inventory CSV export.
        contifico_path:   Contifico inventory file.
        source_type:      One of 'csv_simple', 'csv_bodegas', 'raw_log'.
        output_folder:    Directory where output CSVs are written.

    Returns:
        Summary dict with counts, totals, and delta stats.
    """
    output_folder.mkdir(parents=True, exist_ok=True)

    # Load data
    odoo = load_odoo_stock(odoo_path)

    loaders = {
        "csv_simple": load_contifico_simple,
        "csv_bodegas": load_contifico_bodegas,
        "raw_log": load_contifico_raw_log,
    }
    if source_type not in loaders:
        raise ValueError(f"source_type inválido: {source_type!r}. Usa: {list(loaders)}")
    contifico = loaders[source_type](contifico_path)

    contifico_keys = set(contifico.keys())
    odoo_keys = set(odoo.keys())

    only_contifico = sorted(contifico_keys - odoo_keys)
    only_odoo = sorted(odoo_keys - contifico_keys)
    in_both = sorted(contifico_keys & odoo_keys)

    # Build comparison rows for products in both
    full_rows: list[dict] = []
    differ_rows: list[dict] = []

    for key in in_both:
        c = contifico[key]
        o = odoo[key]
        qty_c = c["qty"]
        qty_o = o["qty"]
        delta = round(qty_o - qty_c, 4)

        row: dict[str, Any] = {
            "SKU": c["sku"],
            "Nombre Contifico": c.get("name", ""),
            "Nombre Odoo": o.get("name", ""),
            "Stock Contifico": qty_c,
            "Stock Odoo": qty_o,
            "Delta (Odoo-Contifico)": delta,
            "Match": "SI" if delta == 0 else "NO",
        }
        if source_type == "csv_bodegas":
            for k in _BODEGAS_WAREHOUSE_KEYS:
                row[f"Contifico - {k}"] = c.get(f"wh_{k}", 0.0)
        full_rows.append(row)
        if delta != 0:
            differ_rows.append(row)

    full_rows.sort(key=lambda r: r["SKU"])
    differ_rows.sort(key=lambda r: r["SKU"])

    # Only-in-Contifico rows
    only_c_rows = sorted(
        [
            {
                "SKU": contifico[k]["sku"],
                "Nombre": contifico[k].get("name", ""),
                "Categoria": contifico[k].get("categoria", ""),
                "Marca": contifico[k].get("marca", ""),
                "Stock Contifico": contifico[k]["qty"],
            }
            for k in only_contifico
        ],
        key=lambda r: r["SKU"],
    )

    # Only-in-Odoo rows
    only_o_rows = sorted(
        [
            {
                "SKU": odoo[k]["sku"],
                "Nombre": odoo[k].get("name", ""),
                "Barcode": odoo[k].get("barcode", ""),
                "Stock Odoo": odoo[k]["qty"],
            }
            for k in only_odoo
        ],
        key=lambda r: r["SKU"],
    )

    # Write CSVs
    def write_csv(filepath: Path, rows: list[dict]) -> None:
        if not rows:
            filepath.write_text("(sin datos)\n", encoding="utf-8")
            return
        with filepath.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    write_csv(output_folder / "stock_compare_full.csv", full_rows)
    write_csv(output_folder / "stock_compare_differ.csv", differ_rows)
    write_csv(output_folder / "stock_compare_only_contifico.csv", only_c_rows)
    write_csv(output_folder / "stock_compare_only_odoo.csv", only_o_rows)

    # Stats
    match_count = len(in_both) - len(differ_rows)
    total_stock_c = sum(contifico[k]["qty"] for k in contifico_keys)
    total_stock_o = sum(odoo[k]["qty"] for k in odoo_keys)

    return {
        "contifico_total_skus": len(contifico),
        "odoo_total_skus": len(odoo),
        "in_both": len(in_both),
        "match": match_count,
        "differ": len(differ_rows),
        "only_in_contifico": len(only_contifico),
        "only_in_odoo": len(only_odoo),
        "total_stock_contifico": round(total_stock_c, 2),
        "total_stock_odoo": round(total_stock_o, 2),
        "delta_global": round(total_stock_o - total_stock_c, 2),
        "source_type": source_type,
        "preview_differ": [r["SKU"] for r in differ_rows[:30]],
        "preview_only_contifico": [only_c_rows[i]["SKU"] for i in range(min(30, len(only_c_rows)))],
        "preview_only_odoo": [only_o_rows[i]["SKU"] for i in range(min(30, len(only_o_rows)))],
    }
