"""Processing pipeline for Módulo 1 — Inventory/Products."""
from .normalizer import parse_sku, ParsedSKU
from .grouper import group_products, TemplateGroup, VariantRow
from .validator import validate, ValidationReport
from .generators import generate_all, GeneratorOptions

__all__ = [
    "parse_sku", "ParsedSKU",
    "group_products", "TemplateGroup", "VariantRow",
    "validate", "ValidationReport",
    "generate_all", "GeneratorOptions",
]
