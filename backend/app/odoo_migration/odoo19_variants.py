from __future__ import annotations

from collections import Counter
from datetime import datetime
import re
from typing import Any

ATTR_COLUMNS = ["Attribute", "Display Type", "Variant Creation Mode", "Values / Value"]
PRODUCTS_COLUMNS = [
    "External ID", "Name", "Product Type", "Product Category", "Sales Price", "Cost", "Can be Sold",
    "Can be Purchased", "Available in POS", "Internal Reference", "Barcode", "Sales Description", "Customer Taxes",
    "Product Attributes / Attribute", "Product Attributes / Values",
]
STOCK_COLUMNS = ["Product", "Lot/Serial Number", "Quantity", "Counted Quantity", "Difference", "Scheduled Date", "Assigned To"]


def parse_base_code_and_variant(codigo: str) -> tuple[str, str]:
    value = (codigo or "").strip()
    if "/" not in value:
        return value, ""
    base, variant = value.rsplit("/", 1)
    return base.strip(), variant.strip()


def normalize_external_id(value: str, prefix: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")
    return f"{prefix}_{slug}" if slug else prefix


def normalize_price(value: Any) -> str:
    try:
        return f"{float(value or 0):.2f}"
    except Exception:
        return "0.00"


def normalize_bool(value: Any, default: bool = True) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    text = str(value or "").strip().lower()
    if text in {"1", "true", "t", "yes", "si", "sí", "a", "pro"}:
        return "True"
    if text in {"0", "false", "f", "no", "n"}:
        return "False"
    return "True" if default else "False"


def normalize_product_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def _natural_key(val: str):
    s = str(val or "")
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _tax_name(iva: Any) -> str:
    try:
        return "IVA 15%" if float(iva or 0) == 15 else "IVA 0%"
    except Exception:
        return "IVA 0%"


def build_attributes_values(products: list[dict[str, Any]]) -> list[dict[str, str]]:
    sizes, brands = set(), set()
    for p in products:
        base, size = parse_base_code_and_variant(str(p.get("codigo") or ""))
        if base and size:
            sizes.add(size)
        brand = normalize_product_name(str(p.get("marca_nombre") or ""))
        if brand:
            brands.add(brand)
    rows = [{"Attribute": "Talla", "Display Type": "Selection", "Variant Creation Mode": "Instantly", "Values / Value": s} for s in sorted(sizes, key=_natural_key)]
    rows += [{"Attribute": "Marca", "Display Type": "Selection", "Variant Creation Mode": "Never", "Values / Value": b} for b in sorted(brands, key=_natural_key)]
    return rows


def build_products_with_variants(products: list[dict[str, Any]], warnings: list[str] | None = None) -> list[dict[str, str]]:
    warnings = warnings if warnings is not None else []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for p in products:
        code = str(p.get("codigo") or "").strip()
        if not code:
            warnings.append("Producto sin codigo")
            continue
        base, _ = parse_base_code_and_variant(code)
        grouped.setdefault(base or code, []).append(p)

    rows: list[dict[str, str]] = []
    for base, items in grouped.items():
        names = [normalize_product_name(str(i.get("nombre") or "")) for i in items if str(i.get("nombre") or "").strip()]
        if not names:
            warnings.append(f"Producto sin nombre: {base}")
            continue
        name = Counter(names).most_common(1)[0][0]
        prices = [normalize_price(i.get("pvp1")) for i in items]
        price = min(prices, key=lambda x: float(x or 0)) if prices else "0.00"
        if len(set(prices)) > 1:
            warnings.append(f"Precios distintos en variantes: {base}")
        cost = normalize_price(items[0].get("costo_maximo"))
        barcode = "" if any(parse_base_code_and_variant(str(i.get("codigo") or ""))[1] for i in items) else str(items[0].get("codigo_barra") or "")
        marcas = sorted({normalize_product_name(str(i.get("marca_nombre") or "")) for i in items if str(i.get("marca_nombre") or "").strip()}, key=_natural_key)
        if len(marcas) > 1:
            warnings.append(f"Marcas distintas en mismo base: {base}")
        talla_vals = sorted({parse_base_code_and_variant(str(i.get("codigo") or ""))[1] for i in items if parse_base_code_and_variant(str(i.get("codigo") or ""))[1]}, key=_natural_key)
        common = {
            "External ID": normalize_external_id(base, "product_template"), "Name": name, "Product Type": "Goods",
            "Product Category": "All / ADAMS / Sin categoría", "Sales Price": price, "Cost": cost,
            "Can be Sold": "True", "Can be Purchased": "True", "Available in POS": normalize_bool(items[0].get("para_pos")),
            "Internal Reference": base, "Barcode": barcode, "Sales Description": str(items[0].get("descripcion") or ""), "Customer Taxes": _tax_name(items[0].get("porcentaje_iva")),
        }
        if talla_vals:
            rows.append({**common, "Product Attributes / Attribute": "Talla", "Product Attributes / Values": ",".join(talla_vals)})
            if not talla_vals:
                warnings.append(f"Tallas no detectables: {base}")
        else:
            rows.append({**common, "Product Attributes / Attribute": "", "Product Attributes / Values": ""})
        if marcas:
            rows.append({**common, "Product Attributes / Attribute": "Marca", "Product Attributes / Values": marcas[0]})
    return rows


def build_stock_quant(products: list[dict[str, Any]], scheduled_date: str | None = None, include_inactive: bool = False) -> list[dict[str, str]]:
    date_value = scheduled_date or datetime.utcnow().date().isoformat()
    rows = []
    for p in products:
        if not include_inactive and str(p.get("estado") or "").upper() not in {"", "A"}:
            continue
        code = str(p.get("codigo") or "").strip()
        if not code:
            continue
        base, variant = parse_base_code_and_variant(code)
        name = normalize_product_name(str(p.get("nombre") or code))
        qty = normalize_price(p.get("cantidad_stock"))
        label = f"[{code}] {name} ({variant})" if variant else f"[{base}] {name}"
        rows.append({"Product": label, "Lot/Serial Number": "", "Quantity": qty, "Counted Quantity": qty, "Difference": "0", "Scheduled Date": date_value, "Assigned To": ""})
    return rows


def build_products_with_variants_from_variant_rows(variant_rows: list[dict[str, Any]], warnings: list[str] | None = None) -> list[dict[str, str]]:
    """Build Odoo19 template rows using normalized phase1 rows (category/brand already resolved)."""
    warnings = warnings if warnings is not None else []
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in variant_rows:
        sku = str(row.get("sku") or "").strip()
        if not sku:
            warnings.append("Producto sin codigo")
            continue
        base, _ = parse_base_code_and_variant(sku)
        grouped.setdefault(base or sku, []).append(row)

    result: list[dict[str, str]] = []
    for base, items in grouped.items():
        names = [normalize_product_name(str(i.get("name") or "")) for i in items if str(i.get("name") or "").strip()]
        if not names:
            warnings.append(f"Producto sin nombre: {base}")
            continue
        name = Counter(names).most_common(1)[0][0]
        prices = [normalize_price(i.get("price")) for i in items]
        if len(set(prices)) > 1:
            warnings.append(f"Precios distintos en variantes: {base}")
        price = min(prices, key=lambda x: float(x or 0)) if prices else "0.00"
        category = normalize_product_name(str(items[0].get("category") or "All / ADAMS / Sin categoría"))
        brand_values = sorted({normalize_product_name(str((i.get("attrs") or {}).get("Marca") or "")) for i in items if normalize_product_name(str((i.get("attrs") or {}).get("Marca") or ""))}, key=_natural_key)
        if len(brand_values) > 1:
            warnings.append(f"Marcas distintas en mismo base: {base}")
        sizes = sorted({normalize_product_name(str((i.get("attrs") or {}).get("Talla") or "")) for i in items if normalize_product_name(str((i.get("attrs") or {}).get("Talla") or ""))}, key=_natural_key)
        barcode = "" if sizes else str(items[0].get("barcode") or "")
        common = {
            "External ID": normalize_external_id(base, "product_template"),
            "Name": name,
            "Product Type": "Goods",
            "Product Category": category,
            "Sales Price": price,
            "Cost": normalize_price(items[0].get("cost")),
            "Can be Sold": "True",
            "Can be Purchased": "True",
            "Available in POS": "True",
            "Internal Reference": base,
            "Barcode": barcode,
            "Sales Description": "",
            "Customer Taxes": "IVA 0%",
        }
        attr_values: dict[str, list[str]] = {}
        if sizes:
            attr_values["Talla"] = sizes
        brand_values = brand_values
        if brand_values:
            attr_values["Marca"] = [brand_values[0]]
        color_values = sorted({normalize_product_name(str((i.get("attrs") or {}).get("Color") or "")) for i in items if normalize_product_name(str((i.get("attrs") or {}).get("Color") or ""))}, key=_natural_key)
        if color_values:
            attr_values["Color"] = color_values
        manga_values = sorted({normalize_product_name(str((i.get("attrs") or {}).get("Manga de Camisa") or "")) for i in items if normalize_product_name(str((i.get("attrs") or {}).get("Manga de Camisa") or ""))}, key=_natural_key)
        if manga_values:
            attr_values["Manga de Camisa"] = manga_values
        ancho_values = sorted({normalize_product_name(str((i.get("attrs") or {}).get("Ancho Corbata") or "")) for i in items if normalize_product_name(str((i.get("attrs") or {}).get("Ancho Corbata") or ""))}, key=_natural_key)
        if ancho_values:
            attr_values["Ancho Corbata"] = ancho_values

        if not attr_values:
            result.append({**common, "Product Attributes / Attribute": "", "Product Attributes / Values": ""})
        else:
            for attr_name, values in attr_values.items():
                result.append({**common, "Product Attributes / Attribute": attr_name, "Product Attributes / Values": ",".join(values)})
    return result
