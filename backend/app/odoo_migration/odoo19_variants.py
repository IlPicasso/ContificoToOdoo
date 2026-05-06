from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from datetime import datetime
import re
from typing import Any

ATTR_COLUMNS = ["Attribute", "Display Type", "Variant Creation Mode", "Values / Value"]
PRODUCTS_COLUMNS = [
    "External ID", "Name", "Product Type", "Product Category", "Sales Price", "Cost", "Can be Sold",
    "Can be Purchased", "Available in POS", "Customer Taxes", "Product Attributes / Attribute", "Product Attributes / Values",
]
VARIANT_MAPPING_COLUMNS = [
    "Product Template External ID", "Product Template Name", "Internal Reference", "Barcode", "Talla", "Color",
    "Manga de Camisa", "Ancho Corbata", "Marca", "Sales Price", "Cost", "Product Category", "Parse Status", "Parser Rule", "Warnings",
]
STOCK_QUANT_SIMPLE_COLUMNS = ["Product / Internal Reference", "Location", "Inventory Quantity"]
VALIDATION_COLUMNS = ["level", "rule", "entity", "message"]
STOCK_COLUMNS = ["Product", "Lot/Serial Number", "Quantity", "Counted Quantity", "Difference", "Scheduled Date", "Assigned To"]
SLEEVE_MAP = {"S1": "S1 - 32/33", "S2": "S2 - 34/35"}
ODOO_CSV_EXPORT_VERSION = "1.4.0"


def parse_base_code_and_variant(codigo: str) -> tuple[str, str]:
    value = (codigo or "").strip()
    if not value:
        return "", ""
    shirt = re.match(r"^(?P<base>[A-Za-z0-9]+)-(?P<size>\d+(?:\.\d+)?)-(?P<sleeve>S[12])$", value, flags=re.IGNORECASE)
    if shirt:
        return shirt.group("base"), f"{shirt.group('size')}-{shirt.group('sleeve').upper()}"
    if "/" not in value:
        m = re.match(r"^(?P<base>.+)-(?P<variant>(?:XXL|XL|XS|L|M|S|\d+(?:\.\d+)?|[A-Za-z]\d+))$", value, flags=re.IGNORECASE)
        if m:
            return m.group("base"), m.group("variant")
        return value, ""
    tie = re.match(r"^(?P<base>.+/\d+)-(?P<variant>\d+(?:\.\d+)?)$", value)
    if tie:
        return tie.group("base"), tie.group("variant")
    base, variant = value.rsplit("/", 1)
    return base.strip(), variant.strip()


def derive_parent_and_attrs(sku: str, name: str, category: str) -> dict[str, Any]:
    raw_sku = (sku or "").strip()
    attrs = {"Talla": "", "Color": "", "Manga de Camisa": "", "Ancho Corbata": "", "Marca": ""}
    cat = normalize_product_name(category).upper()
    name_u = normalize_product_name(name).upper()
    is_camisa = "CAMISA" in cat or "CAMISA" in name_u
    is_terno = "TERNO" in cat or "TERNO" in name_u
    is_corbata = "CORBATA" in cat or "CORBATA" in name_u
    warnings: list[str] = []
    m = re.match(r"^(?P<base>.+?)-(?P<size>\d+(?:\.\d+)?)-(?P<sleeve>S[12])$", raw_sku, flags=re.IGNORECASE)
    if m and is_camisa:
        base = m.group("base").strip()
        base = re.sub(r"BG(?=-|$)", "", base, flags=re.IGNORECASE)
        base = re.sub(r"-{2,}", "-", base).strip("-")
        attrs["Talla"] = m.group("size")
        attrs["Manga de Camisa"] = SLEEVE_MAP.get(m.group("sleeve").upper(), m.group("sleeve").upper())
        return {"sku": raw_sku, "parent_key": base, "template_external_id": normalize_external_id(base, "product_template"), "attrs": attrs, "parse_status": "PARSED", "parser_rule": "shirt_bg_dc", "warnings": warnings}
    if is_corbata:
        t = re.match(r"^(?P<base>.+)-(?P<w>\d+(?:\.\d+)?)$", raw_sku)
        if t:
            attrs["Ancho Corbata"] = _format_cm_value(t.group("w"))
            return {"sku": raw_sku, "parent_key": t.group("base"), "template_external_id": normalize_external_id(t.group("base"), "product_template"), "attrs": attrs, "parse_status": "PARSED", "parser_rule": "tie_width", "warnings": warnings}
        s_tie = re.match(r"^(?P<base>.+)/(?P<tail>\d+(?:\.\d+)?)$", raw_sku)
        if s_tie:
            tail = s_tie.group("tail")
            if tail in {"6", "6.5", "7", "7.5", "8"}:
                attrs["Ancho Corbata"] = _format_cm_value(tail)
                return {"sku": raw_sku, "parent_key": s_tie.group("base"), "template_external_id": normalize_external_id(s_tie.group("base"), "product_template"), "attrs": attrs, "parse_status": "PARSED", "parser_rule": "tie_slash_width", "warnings": warnings}
            return {"sku": raw_sku, "parent_key": raw_sku, "template_external_id": normalize_external_id(raw_sku, "product_template"), "attrs": attrs, "parse_status": "UNPARSED", "parser_rule": "tie_slash_non_width", "warnings": ["Slash final en corbata no coincide con ancho válido"]}
    s = re.match(r"^(?P<base>.+)/(?P<size>\d+(?:\.\d+)?|XS|S|M|L|XL|XXL|XXXL)$", raw_sku, flags=re.IGNORECASE)
    if s:
        base = s.group("base")
        if is_terno:
            base = re.sub(r"BG(?=/|$)", "", base, flags=re.IGNORECASE)
            base = re.sub(r"BG$", "", base, flags=re.IGNORECASE)
        attrs["Talla"] = s.group("size").upper()
        return {"sku": raw_sku, "parent_key": base, "template_external_id": normalize_external_id(base, "product_template"), "attrs": attrs, "parse_status": "PARSED", "parser_rule": "slash_size", "warnings": warnings}
    # Generic hyphen size suffix (e.g. VE-MICAELA-AZ-XL, VE-ELA-STP-M)
    g = re.match(r"^(?P<base>.+)-(?P<size>XS|S|M|L|XL|XXL|XXXL|\d+(?:\.\d+)?)$", raw_sku, flags=re.IGNORECASE)
    if g:
        attrs["Talla"] = g.group("size").upper()
        return {"sku": raw_sku, "parent_key": g.group("base"), "template_external_id": normalize_external_id(g.group("base"), "product_template"), "attrs": attrs, "parse_status": "PARSED", "parser_rule": "hyphen_size", "warnings": warnings}
    return {"sku": raw_sku, "parent_key": raw_sku, "template_external_id": normalize_external_id(raw_sku, "product_template"), "attrs": attrs, "parse_status": "UNPARSED", "parser_rule": "fallback", "warnings": ["No se pudo parsear SKU"]}


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


def normalize_brand_name(name: str) -> str:
    cleaned = normalize_product_name(name)
    if not cleaned:
        return ""
    parts = []
    for token in cleaned.split(" "):
        if len(token) <= 3:
            parts.append(token.upper())
        else:
            parts.append(token[:1].upper() + token[1:].lower())
    return " ".join(parts)


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
        brand = normalize_brand_name(str(p.get("marca_nombre") or ""))
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
        marcas = sorted({normalize_brand_name(str(i.get("marca_nombre") or "")) for i in items if str(i.get("marca_nombre") or "").strip()}, key=_natural_key)
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
        parsed = derive_parent_and_attrs(sku, str(row.get("name") or ""), str(row.get("category") or ""))
        cleaned_attrs = _clean_candidate_attrs(sku, parsed.get("attrs") or {}, row.get("attrs") or {})
        cleaned_attrs = _apply_tie_attribute_rules(cleaned_attrs, str(row.get("name") or ""), str(row.get("category") or ""))
        grouped.setdefault(parsed["parent_key"] or sku, []).append({**row, "_parsed": parsed, "_clean_attrs": cleaned_attrs})

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
        brand_values = sorted({
            normalize_product_name(str((((i.get("_parsed") or {}).get("attrs") or {}).get("Marca") or (i.get("attrs") or {}).get("Marca") or "")))
            for i in items
            if normalize_product_name(str((((i.get("_parsed") or {}).get("attrs") or {}).get("Marca") or (i.get("attrs") or {}).get("Marca") or "")))
        }, key=_natural_key)
        if len(brand_values) > 1:
            warnings.append(f"Marcas distintas en mismo base: {base}")
        sizes = sorted({normalize_product_name(str((i.get("_clean_attrs") or {}).get("Talla") or "")) for i in items if normalize_product_name(str((i.get("_clean_attrs") or {}).get("Talla") or ""))}, key=_natural_key)
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
            "Customer Taxes": "IVA 0%",
        }
        attr_values: dict[str, list[str]] = {}
        if sizes:
            attr_values["Talla"] = sizes
        brand_values = brand_values
        if brand_values:
            attr_values["Marca"] = [brand_values[0]]
        color_values = sorted({
            normalize_product_name(str((i.get("_clean_attrs") or {}).get("Color") or ""))
            for i in items
            if normalize_product_name(str((i.get("_clean_attrs") or {}).get("Color") or ""))
        }, key=_natural_key)
        if color_values:
            attr_values["Color"] = color_values
        manga_values = sorted({
            normalize_product_name(str((i.get("_clean_attrs") or {}).get("Manga de Camisa") or ""))
            for i in items
            if normalize_product_name(str((i.get("_clean_attrs") or {}).get("Manga de Camisa") or ""))
        }, key=_natural_key)
        if manga_values:
            attr_values["Manga de Camisa"] = manga_values
        ancho_values = sorted({
            normalize_product_name(str((i.get("_clean_attrs") or {}).get("Ancho Corbata") or ""))
            for i in items
            if normalize_product_name(str((i.get("_clean_attrs") or {}).get("Ancho Corbata") or ""))
        }, key=_natural_key)
        if ancho_values:
            attr_values["Ancho Corbata"] = ancho_values

        if not attr_values:
            result.append({**common, "Product Attributes / Attribute": "", "Product Attributes / Values": ""})
        else:
            for attr_name, values in attr_values.items():
                unique_values = sorted({normalize_product_name(v) for v in values if normalize_product_name(v)}, key=_natural_key)
                if not attr_name or not unique_values:
                    continue
                result.append({**common, "Product Attributes / Attribute": attr_name, "Product Attributes / Values": ",".join(unique_values)})
    return result




def _is_tie_product(name: str, category: str) -> bool:
    category_norm = normalize_product_name(category).upper()
    name_norm = normalize_product_name(name).upper()
    return category_norm == "ROPA / HOMBRES / CORBATAS" or "CORBATA" in name_norm


def _format_cm_value(value: str) -> str:
    raw = normalize_product_name(value)
    if not raw:
        return ""
    match = re.match(r"^(?P<num>\d+(?:[\.,]\d+)?)\s*(?:cm)?$", raw, flags=re.IGNORECASE)
    if not match:
        return raw if raw.lower().endswith("cm") else f"{raw} cm"
    num = match.group("num").replace(",", ".")
    try:
        dec = Decimal(num)
        if dec == dec.to_integral():
            num = str(int(dec))
        else:
            num = format(dec.normalize(), "f").rstrip("0").rstrip(".")
    except InvalidOperation:
        pass
    return f"{num} cm"


def _apply_tie_attribute_rules(attrs: dict[str, Any], name: str, category: str) -> dict[str, str]:
    normalized = {
        "Talla": attrs.get("Talla", ""),
        "Color": attrs.get("Color", ""),
        "Manga de Camisa": attrs.get("Manga de Camisa", ""),
        "Ancho Corbata": normalize_product_name(str(attrs.get("Ancho Corbata") or "")),
        "Marca": attrs.get("Marca", ""),
    }
    if _is_tie_product(name, category):
        talla = normalized["Talla"]
        ancho = normalized["Ancho Corbata"]
        if talla and re.match(r"^\d+(?:[\.,]\d+)?(?:\s*cm)?$", talla, flags=re.IGNORECASE):
            if not ancho:
                ancho = talla
            normalized["Talla"] = ""
        normalized["Ancho Corbata"] = _format_cm_value(ancho) if ancho else ""
        normalized["Talla"] = ""
    else:
        normalized["Ancho Corbata"] = _format_cm_value(normalized["Ancho Corbata"]) if normalized["Ancho Corbata"] else ""
    return normalized


def _looks_like_valid_size(value: str) -> bool:
    v = normalize_product_name(value).upper()
    if not v:
        return False
    return bool(re.match(r"^(XS|S|M|L|XL|XXL|XXXL|SL|ML|\d+(?:\.\d+)?)$", v))


def _clean_candidate_attrs(sku: str, parsed_attrs: dict[str, Any], raw_attrs: dict[str, Any]) -> dict[str, Any]:
    sku_u = normalize_product_name(sku).upper()
    talla = normalize_product_name(str(parsed_attrs.get("Talla") or raw_attrs.get("Talla") or ""))
    ancho = normalize_product_name(str(parsed_attrs.get("Ancho Corbata") or raw_attrs.get("Ancho Corbata") or ""))
    if (not _looks_like_valid_size(talla)) or normalize_product_name(talla).upper() == sku_u or "/" in talla:
        talla = ""
    # Ancho Corbata only accepts numeric-ish values, never full SKUs/codes
    if ancho and not re.match(r"^\d+(?:[\.,]\d+)?(?:\s*cm)?$", ancho, flags=re.IGNORECASE):
        ancho = ""
    return {
        "Talla": talla,
        "Ancho Corbata": ancho,
        "Color": normalize_product_name(str(parsed_attrs.get("Color") or raw_attrs.get("Color") or "")),
        "Manga de Camisa": normalize_product_name(str(parsed_attrs.get("Manga de Camisa") or raw_attrs.get("Manga de Camisa") or "")),
        "Marca": normalize_product_name(str(parsed_attrs.get("Marca") or raw_attrs.get("Marca") or "")),
    }


def build_variant_combination_key(row: dict[str, str]) -> str:
    attrs = [row.get("Talla", ""), row.get("Color", ""), row.get("Manga de Camisa", ""), row.get("Ancho Corbata", ""), row.get("Marca", "")]
    norm_attrs = [normalize_product_name(str(v or "")).upper() for v in attrs]
    return f"{row.get('Product Template External ID','')}|" + "|".join(norm_attrs)


def dedupe_variant_mapping_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = build_variant_combination_key(row)
        grouped.setdefault(key, []).append(row)
    deduped = []
    duplicates = []
    for key, items in grouped.items():
        ordered = sorted(items, key=lambda r: normalize_product_name(r.get("Internal Reference", "")))
        deduped.append(ordered[0])
        if len(items) > 1:
            duplicates.append({
                "key": key,
                "count": len(items),
                "template_external_id": ordered[0].get("Product Template External ID", ""),
                "examples": [i.get("Internal Reference", "") for i in ordered[:3]],
                "dropped_internal_references": [i.get("Internal Reference", "") for i in ordered[1:]],
            })
    return deduped, duplicates

def normalize_ancho_corbata(value: str) -> str:
    raw = normalize_product_name(value)
    if not raw:
        return ""
    if raw.lower().endswith("cm"):
        return raw.replace("CM", "cm")
    return f"{raw} cm"


def build_variant_sku_mapping(variant_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for row in variant_rows:
        sku = str(row.get("sku") or "").strip()
        parsed = derive_parent_and_attrs(sku, str(row.get("name") or ""), str(row.get("category") or ""))
        merged_attrs = _clean_candidate_attrs(sku, parsed.get("attrs") or {}, row.get("attrs") or {})
        attrs = _apply_tie_attribute_rules(merged_attrs, str(row.get("name") or ""), str(row.get("category") or ""))
        rows.append({
            "Product Template External ID": parsed.get("template_external_id") or normalize_external_id(sku, "product_template"),
            "Product Template Name": normalize_product_name(str(row.get("name") or "")),
            "Internal Reference": sku,
            "Barcode": str(row.get("barcode") or ""),
            "Talla": attrs.get("Talla", ""),
            "Color": attrs.get("Color", ""),
            "Manga de Camisa": attrs.get("Manga de Camisa", ""),
            "Ancho Corbata": attrs.get("Ancho Corbata", ""),
            "Marca": attrs.get("Marca", ""),
            "Sales Price": normalize_price(row.get("price")),
            "Cost": normalize_price(row.get("cost")),
            "Product Category": normalize_product_name(str(row.get("category") or "")),
            "Parse Status": str(parsed.get("parse_status") or ""),
            "Parser Rule": str(parsed.get("parser_rule") or ""),
            "Warnings": "|".join(parsed.get("warnings") or []),
        })
    return rows
