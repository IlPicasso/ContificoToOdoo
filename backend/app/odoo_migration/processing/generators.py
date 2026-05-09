"""Numbered CSV file generators for Odoo import.

Outputs four files:
  01_product_template.csv   — product.template rows (no Internal Reference)
  02_product_product.csv    — product.product rows WITH Internal Reference (SKU)
  03_product_attribute.csv  — attribute value definitions (Talla, Ancho Corbata, etc.)
  04_stock_quant.csv        — initial stock quantities per warehouse location

Key design decision: Internal Reference (default_code) goes in 02_product_product.csv,
NOT in 01_product_template.csv. This eliminates the Phase 2 merger step entirely.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .grouper import TemplateGroup, VariantRow
from .validator import ValidationReport

# ── Column definitions ────────────────────────────────────────────────────────

TEMPLATE_COLUMNS = [
    "External ID",
    "Name",
    "Product Type",
    "Product Category",
    "Sales Price",
    "Cost",
    "Can be Sold",
    "Can be Purchased",
    "is_storable",
    "available_in_pos",
    "Customer Taxes",
    "Product Attributes / Attribute",
    "Product Attributes / Values",
    "Product Attributes / Create Variants",
]

PRODUCT_PRODUCT_COLUMNS = [
    "External ID",
    "Internal Reference",
    "Barcode",
    "Product Template/External ID",
    "Talla",
    "Manga de Camisa",
    "Ancho Corbata",
    "Sales Price",
    "Cost",
    "available_in_pos",
]

ATTRIBUTE_COLUMNS = [
    "Attribute",
    "Display Type",
    "Variant Creation Mode",
    "Values / Value",
]

STOCK_QUANT_COLUMNS = [
    "Product / External ID",
    "Product / Internal Reference",
    "Location",
    "Inventory Quantity",
]

WAREHOUSE_TO_LOCATION = {
    "BPU": "BPU/Existencias",
    "TUR": "TUR/Existencias",
    "BAT": "BAT/Existencias",
    "BSR": "BSR/Existencias",
    "OFA": "OFA/Existencias",
    "BMT": "BMT/Existencias",
    "B2": "B2/Existencias",
    "BW": "BW/Existencias",
    "BM": "BM/Existencias",
    "BTL": "BTL/Existencias",
}

# Attributes that create product.product variants (vs. "no_variant" attributes like Marca, Color)
VARIANT_CREATING_ATTRIBUTES = {"Talla", "Manga de Camisa", "Ancho Corbata"}


@dataclass
class GeneratorOptions:
    output_folder: Path
    include_stock: bool = False
    default_tax: str = "IVA 15%"
    default_product_type: str = "Goods"


def generate_all(
    groups: list[TemplateGroup],
    report: ValidationReport,
    options: GeneratorOptions,
) -> dict[str, str]:
    """Generate four numbered CSV files in import order.

    File naming matches the required Odoo import sequence:
      01_product_attribute.csv  — import first (attribute definitions)
      02_product_template.csv   — import second (templates/product.template)
      03_product_product.csv    — import third (variants with Internal Reference)
      04_stock_quant.csv        — import fourth (optional: initial stock)

    Returns a dict mapping file role → filename written.
    """
    folder = options.output_folder
    folder.mkdir(parents=True, exist_ok=True)

    template_rows, product_rows, attr_rows, stock_rows = _build_rows(groups, options)

    _write_csv(folder / "01_product_attribute.csv", ATTRIBUTE_COLUMNS, attr_rows)
    _write_csv(folder / "02_product_template.csv", TEMPLATE_COLUMNS, template_rows)
    _write_csv(folder / "03_product_product.csv", PRODUCT_PRODUCT_COLUMNS, product_rows)
    _write_csv(folder / "04_stock_quant.csv", STOCK_QUANT_COLUMNS, stock_rows if options.include_stock else [])

    output = {
        "01_product_attribute": "01_product_attribute.csv",
        "02_product_template": "02_product_template.csv",
        "03_product_product": "03_product_product.csv",
        "04_stock_quant": "04_stock_quant.csv",
    }

    _write_run_summary(folder, groups, report, output)

    return output


# ── Row builders ──────────────────────────────────────────────────────────────

def _build_rows(
    groups: list[TemplateGroup],
    options: GeneratorOptions,
) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    template_rows: list[dict] = []
    product_rows: list[dict] = []
    attr_values_seen: dict[str, set[str]] = {}  # attr_name → set of values
    stock_rows: list[dict] = []

    for grp in groups:
        _emit_template_rows(grp, template_rows, attr_values_seen, options)
        _emit_product_rows(grp, product_rows, options)
        if options.include_stock:
            _emit_stock_rows(grp, stock_rows)

    # Build attribute catalog from all values seen
    attr_rows: list[dict] = []
    attr_order = ["Talla", "Manga de Camisa", "Ancho Corbata"]
    for attr in attr_order:
        values = sorted(attr_values_seen.get(attr, set()), key=_natural_key)
        for v in values:
            # Talla and Manga create variants; AnchoCorbata creates variants
            # (Marca and Color are intentionally excluded from this pipeline)
            attr_rows.append({
                "Attribute": attr,
                "Display Type": "Select",
                "Variant Creation Mode": "Instantly",
                "Values / Value": v,
            })

    return template_rows, product_rows, attr_rows, stock_rows


def _emit_template_rows(
    grp: TemplateGroup,
    out: list[dict],
    attr_values_seen: dict[str, set[str]],
    options: GeneratorOptions,
) -> None:
    common = {
        "External ID": grp.template_external_id,
        "Name": grp.name,
        "Product Type": options.default_product_type,
        "Product Category": grp.category,
        "Sales Price": f"{grp.price:.2f}",
        "Cost": f"{grp.cost:.2f}",
        "Can be Sold": "True",
        "Can be Purchased": "True",
        "is_storable": "True",
        "available_in_pos": "True" if grp.para_pos else "False",
        "Customer Taxes": options.default_tax,
    }

    if grp.is_simple:
        # Simple product: no attribute rows
        out.append({**common, "Product Attributes / Attribute": "", "Product Attributes / Values": "", "Product Attributes / Create Variants": ""})
        return

    # Collect all attribute values across variants for this template
    axes: dict[str, set[str]] = {}
    for v in grp.variants:
        if v.talla:
            axes.setdefault("Talla", set()).add(v.talla)
            attr_values_seen.setdefault("Talla", set()).add(v.talla)
        if v.manga:
            axes.setdefault("Manga de Camisa", set()).add(v.manga)
            attr_values_seen.setdefault("Manga de Camisa", set()).add(v.manga)
        if v.ancho_corbata:
            axes.setdefault("Ancho Corbata", set()).add(v.ancho_corbata)
            attr_values_seen.setdefault("Ancho Corbata", set()).add(v.ancho_corbata)

    # One row per attribute (Odoo multi-row template format)
    for attr_name, values in axes.items():
        sorted_vals = ",".join(sorted(values, key=_natural_key))
        out.append({
            **common,
            "Product Attributes / Attribute": attr_name,
            "Product Attributes / Values": sorted_vals,
            "Product Attributes / Create Variants": "Instantly",
        })


def _emit_product_rows(
    grp: TemplateGroup,
    out: list[dict],
    options: GeneratorOptions,
) -> None:
    for v in grp.variants:
        row = {
            "External ID": v.external_id,
            "Internal Reference": v.sku,
            "Barcode": v.barcode,
            "Product Template/External ID": grp.template_external_id,
            "Talla": v.talla,
            "Manga de Camisa": v.manga,
            "Ancho Corbata": v.ancho_corbata,
            "Sales Price": f"{v.price:.2f}",
            "Cost": f"{v.cost:.2f}",
            "available_in_pos": "True" if v.para_pos else "False",
        }
        out.append(row)


def _emit_stock_rows(grp: TemplateGroup, out: list[dict]) -> None:
    for v in grp.variants:
        for wh_code, location in WAREHOUSE_TO_LOCATION.items():
            qty = v.stock_map.get(wh_code, 0.0)
            if qty > 0:
                out.append({
                    "Product / External ID": v.external_id,
                    "Product / Internal Reference": v.sku,
                    "Location": location,
                    "Inventory Quantity": f"{qty:.2f}",
                })


# ── File writing ──────────────────────────────────────────────────────────────

def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_run_summary(
    folder: Path,
    groups: list[TemplateGroup],
    report: ValidationReport,
    output_files: dict[str, str],
) -> None:
    total_variants = sum(len(g.variants) for g in groups)
    summary = {
        "total_templates": len(groups),
        "total_simples": sum(1 for g in groups if g.is_simple),
        "total_with_attributes": sum(1 for g in groups if not g.is_simple),
        "total_variants": total_variants,
        "total_errors": report.error_count,
        "total_warnings": report.warning_count,
        "large_templates": len(report.large_templates),
        "barcode_conflicts": len(report.barcode_conflicts),
        "duplicate_skus": len(report.duplicate_skus),
        "output_files": output_files,
    }
    (folder / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _natural_key(val: str):
    s = str(val or "")
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
