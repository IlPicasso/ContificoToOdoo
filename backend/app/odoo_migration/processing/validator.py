"""Pre-import validation — run before writing any CSV.

Returns a ValidationReport with counts and lists of issues.
Can optionally cross-reference Productos.csv and Saldos CSV for completeness checks.
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .grouper import TemplateGroup, VariantRow


@dataclass
class ValidationIssue:
    level: str      # "error" | "warning" | "info"
    rule: str
    entity: str     # SKU or template base_key
    message: str


@dataclass
class ValidationReport:
    # Counts
    total_templates: int = 0
    total_variants: int = 0
    total_simples: int = 0
    total_with_attributes: int = 0

    # Issues
    duplicate_skus: list[str] = field(default_factory=list)
    barcode_conflicts: list[dict] = field(default_factory=list)
    orphan_variants: list[str] = field(default_factory=list)      # parse_status != PARSED
    large_templates: list[dict] = field(default_factory=list)     # > 20 variants
    sku_not_in_saldos: list[str] = field(default_factory=list)    # in Contifico but not in Saldos
    sku_only_in_saldos: list[str] = field(default_factory=list)   # in Saldos but not in processed

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.level == "warning")

    def to_dict(self) -> dict:
        return {
            "summary": {
                "total_templates": self.total_templates,
                "total_variants": self.total_variants,
                "total_simples": self.total_simples,
                "total_with_attributes": self.total_with_attributes,
                "error_count": self.error_count,
                "warning_count": self.warning_count,
            },
            "duplicate_skus": self.duplicate_skus,
            "barcode_conflicts": self.barcode_conflicts,
            "orphan_variants": self.orphan_variants,
            "large_templates": self.large_templates,
            "sku_not_in_saldos": self.sku_not_in_saldos,
            "sku_only_in_saldos": self.sku_only_in_saldos,
            "issues": [
                {"level": i.level, "rule": i.rule, "entity": i.entity, "message": i.message}
                for i in self.issues
            ],
        }

    def write_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def validate(
    groups: list[TemplateGroup],
    *,
    raw_sku_list: list[str] | None = None,
    saldos_csv: Optional[Path] = None,
    write_to: Optional[Path] = None,
) -> ValidationReport:
    """Validate template groups and return a structured report.

    Args:
        groups: Output from grouper.group_products().
        raw_sku_list: All SKUs seen in Contifico BEFORE deduplication, used to detect duplicates.
        saldos_csv: Path to ReporteSaldosInventarioPorBodega.csv for cross-reference.
        write_to: If provided, writes validation_report.json to this path.
    """
    report = ValidationReport()
    report.total_templates = len(groups)

    seen_barcodes: dict[str, str] = {}   # barcode → first SKU
    processed_skus: set[str] = set()
    issues: list[ValidationIssue] = []

    for grp in groups:
        variant_count = len(grp.variants)
        report.total_variants += variant_count

        if grp.is_simple:
            report.total_simples += 1
        else:
            report.total_with_attributes += 1

        if grp.is_large:
            report.large_templates.append({
                "base_key": grp.base_key,
                "template_name": grp.name,
                "variant_count": variant_count,
            })
            issues.append(ValidationIssue(
                level="warning",
                rule="large_template",
                entity=grp.base_key,
                message=f"Plantilla con {variant_count} variantes (umbral: 20)",
            ))

        for v in grp.variants:
            processed_skus.add(v.sku)

            if v.parse_status not in ("PARSED", "UNPARSED"):
                pass  # only log actual errors
            if v.parse_status == "ERROR":
                report.orphan_variants.append(v.sku)
                issues.append(ValidationIssue(
                    level="error",
                    rule="parse_error",
                    entity=v.sku,
                    message=f"Error al parsear SKU: {'; '.join(v.warnings)}",
                ))

            barcode = v.barcode
            if barcode:
                if barcode in seen_barcodes and seen_barcodes[barcode] != v.sku:
                    conflict = {"barcode": barcode, "sku_a": seen_barcodes[barcode], "sku_b": v.sku}
                    report.barcode_conflicts.append(conflict)
                    issues.append(ValidationIssue(
                        level="error",
                        rule="barcode_conflict",
                        entity=v.sku,
                        message=f"Barcode {barcode!r} ya usado por {seen_barcodes[barcode]!r}",
                    ))
                else:
                    seen_barcodes[barcode] = v.sku

    # Duplicate SKU detection from raw Contifico list
    if raw_sku_list:
        from collections import Counter
        counts = Counter(raw_sku_list)
        for sku, count in counts.items():
            if count > 1:
                report.duplicate_skus.append(sku)
                issues.append(ValidationIssue(
                    level="warning",
                    rule="duplicate_sku",
                    entity=sku,
                    message=f"SKU aparece {count} veces en Contifico",
                ))

    # Saldos cross-reference
    if saldos_csv and saldos_csv.exists():
        saldos_skus = _read_saldos_skus(saldos_csv)
        report.sku_not_in_saldos = sorted(processed_skus - saldos_skus)
        report.sku_only_in_saldos = sorted(saldos_skus - processed_skus)
        if report.sku_only_in_saldos:
            issues.append(ValidationIssue(
                level="info",
                rule="saldos_only",
                entity="saldos_csv",
                message=f"{len(report.sku_only_in_saldos)} SKUs en Saldos no encontrados en pipeline",
            ))

    report.issues = issues

    if write_to:
        report.write_json(write_to)

    return report


def _read_saldos_skus(path: Path) -> set[str]:
    """Read SKUs from ReporteSaldosInventarioPorBodega.csv."""
    skus: set[str] = set()
    try:
        with path.open(encoding="latin-1", errors="replace") as f:
            # Skip title rows until we find the header row
            lines = f.readlines()

        header_idx = None
        for i, line in enumerate(lines):
            if "codigo" in line.lower() or "sku" in line.lower() or "producto" in line.lower():
                header_idx = i
                break

        if header_idx is None:
            return skus

        import io
        content = "".join(lines[header_idx:])
        # Try semicolon first, then comma
        for delimiter in (";", ","):
            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            rows = list(reader)
            if rows and len(rows[0]) > 1:
                # Find the SKU column
                for col in reader.fieldnames or []:
                    col_norm = col.strip().lower()
                    if col_norm in ("codigo", "sku", "código", "codigo_producto", "codigo producto"):
                        for row in rows:
                            val = (row.get(col) or "").strip()
                            if val:
                                skus.add(val)
                        break
                if skus:
                    break
    except Exception:
        pass
    return skus
