"""Groups ParsedSKU instances into product.template + product.product pairs.

Each TemplateGroup represents one product.template in Odoo.
Variants within a group are the product.product rows.
Simple products (no attributes) are still wrapped in a TemplateGroup with one variant.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .normalizer import ParsedSKU, _slugify

LARGE_GROUP_THRESHOLD = 20


@dataclass
class VariantRow:
    """One product.product row (one SKU)."""
    sku: str
    name: str
    barcode: str
    price: float
    cost: float
    para_pos: bool
    talla: str
    manga: str
    ancho_corbata: str
    parse_rule: str
    parse_status: str
    stock_map: dict[str, float]
    warnings: list[str] = field(default_factory=list)
    # derived
    external_id: str = ""
    template_external_id: str = ""

    def __post_init__(self) -> None:
        self.external_id = f"adams_{_slugify(self.sku)}" if self.sku else "adams_unknown"
        self.total_stock: float = sum(self.stock_map.values())


@dataclass
class TemplateGroup:
    """One product.template in Odoo with its variants."""
    base_key: str
    template_external_id: str
    name: str           # canonical name (most common among variants)
    category: str
    price: float        # minimum price across variants
    cost: float         # cost from first variant
    para_pos: bool
    attribute_axes: list[str]   # which axes have values: Talla, Manga de Camisa, Ancho Corbata
    variants: list[VariantRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_simple(self) -> bool:
        return not self.attribute_axes

    @property
    def total_stock(self) -> float:
        return sum(v.total_stock for v in self.variants)

    @property
    def has_stock(self) -> bool:
        return self.total_stock > 0

    @property
    def is_large(self) -> bool:
        return len(self.variants) > LARGE_GROUP_THRESHOLD


def group_products(
    items: list[dict[str, Any]],
    *,
    parsed_skus: list[ParsedSKU],
    include_zero_stock: bool = False,
) -> list[TemplateGroup]:
    """Group product items (from Contifico) + their parsed SKUs into TemplateGroups.

    Args:
        items: Raw Contifico product dicts (one per SKU, already deduplicated).
        parsed_skus: Parallel list — parsed_skus[i] corresponds to items[i].
        include_zero_stock: If False (default), omit variants with zero stock.
            A template is omitted entirely only if ALL its variants have zero stock.
    """
    # Bucket by base_key
    buckets: dict[str, list[tuple[dict[str, Any], ParsedSKU]]] = {}
    for item, parsed in zip(items, parsed_skus):
        buckets.setdefault(parsed.base_key, []).append((item, parsed))

    groups: list[TemplateGroup] = []

    for base_key, pairs in buckets.items():
        # Resolve canonical name from majority vote
        names = [str(p[0].get("nombre") or "").strip() for p in pairs if str(p[0].get("nombre") or "").strip()]
        canonical_name = Counter(names).most_common(1)[0][0] if names else base_key

        # Category: from first item (already resolved upstream)
        category = str(pairs[0][0].get("_category") or "All / ADAMS / Sin categoría")

        # Price: minimum across variants
        prices = [float(p[0].get("pvp1") or 0) for p in pairs]
        price = min(prices) if prices else 0.0

        # Cost: from first item
        cost = float(pairs[0][0].get("costo_maximo") or pairs[0][0].get("costo_promedio") or pairs[0][0].get("costo") or 0)

        # POS: any variant marked para_pos
        para_pos = any(str(p[0].get("para_pos") or "").upper() in {"A", "TRUE", "1", "PRO"} for p in pairs)

        # Determine attribute axes present in this group
        has_talla = any(p[1].talla for p in pairs)
        has_manga = any(p[1].manga for p in pairs)
        has_ancho = any(p[1].ancho_corbata for p in pairs)
        attribute_axes = []
        if has_talla:
            attribute_axes.append("Talla")
        if has_manga:
            attribute_axes.append("Manga de Camisa")
        if has_ancho:
            attribute_axes.append("Ancho Corbata")

        # Build variant rows
        variant_rows: list[VariantRow] = []
        group_warnings: list[str] = []

        for item, parsed in pairs:
            # Prefer pre-computed stock_map injected by service (uses full warehouse mapping)
            stock_map = item.get("_stock_map") or _extract_stock(item)
            total_stock = sum(stock_map.values())

            if not include_zero_stock and total_stock <= 0:
                continue  # skip this variant; template may still be kept if others have stock

            vrow = VariantRow(
                sku=parsed.sku,
                name=str(item.get("nombre") or "").strip() or parsed.sku,
                barcode=str(item.get("codigo_barra") or "").strip(),
                price=float(item.get("pvp1") or 0),
                cost=float(item.get("costo_maximo") or item.get("costo_promedio") or item.get("costo") or 0),
                para_pos=str(item.get("para_pos") or "").upper() in {"A", "TRUE", "1", "PRO"},
                talla=parsed.talla,
                manga=parsed.manga,
                ancho_corbata=parsed.ancho_corbata,
                parse_rule=parsed.parse_rule,
                parse_status=parsed.parse_status,
                stock_map=stock_map,
                warnings=list(parsed.warnings),
            )
            vrow.template_external_id = parsed.template_external_id
            variant_rows.append(vrow)

        # If no variants survive the zero-stock filter, skip the whole group
        if not variant_rows:
            continue

        tmpl_ext_id = f"product_template_{_slugify(base_key)}" if base_key else "product_template_unknown"

        grp = TemplateGroup(
            base_key=base_key,
            template_external_id=tmpl_ext_id,
            name=canonical_name,
            category=category,
            price=price,
            cost=cost,
            para_pos=para_pos,
            attribute_axes=attribute_axes,
            variants=variant_rows,
            warnings=group_warnings,
        )

        if grp.is_large:
            grp.warnings.append(f"Grupo grande: {len(variant_rows)} variantes")

        groups.append(grp)

    return groups


# ── Helpers ──────────────────────────────────────────────────────────────────

_WAREHOUSE_KEYS = ["BPU", "TUR", "BAT", "BSR", "OFA", "BMT", "B2", "BW", "BM", "BTL"]


def _extract_stock(item: dict[str, Any]) -> dict[str, float]:
    """Extract per-warehouse stock from a Contifico product dict."""
    stock_map: dict[str, float] = {k: 0.0 for k in _WAREHOUSE_KEYS}
    bodegas = item.get("bodegas") or []
    if isinstance(bodegas, list):
        for bodega in bodegas:
            codigo = str(bodega.get("bodega_codigo") or bodega.get("codigo") or "").upper()
            qty = float(bodega.get("existencia") or bodega.get("cantidad") or 0)
            if codigo in stock_map:
                stock_map[codigo] += qty
    # Flat fields fallback
    for key in _WAREHOUSE_KEYS:
        flat_key = f"stock_{key.lower()}"
        if flat_key in item and stock_map[key] == 0.0:
            stock_map[key] = float(item[flat_key] or 0)
    return stock_map
