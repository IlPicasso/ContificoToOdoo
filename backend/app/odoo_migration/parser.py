from __future__ import annotations
import re
from dataclasses import dataclass

SLEEVE_MAP = {"S1": "S1 - 32/33", "S2": "S2 - 34/35"}
SUIT = re.compile(r"^(?P<model>\d+)/(?P<size>\d+(?:\.\d+)?)$")
SHIRT = re.compile(r"^(?P<model>\d+)-(?P<size>\d+(?:\.\d+)?)-(?P<sleeve>S[12])$")

@dataclass
class ParsedSku:
    sku: str
    product_name: str
    category_odoo: str
    talla: str
    manga: str
    model: str
    ancho_corbata: str = ""


def parse_adams_sku(raw: str) -> ParsedSku:
    sku = (raw or "").strip()
    m = SUIT.match(sku)
    if m:
        model = m.group("model")
        return ParsedSku(sku, f"Terno {model}", "Ropa / Ternos", m.group("size"), "", model)
    m = SHIRT.match(sku)
    if m:
        model = m.group("model")
        sleeve = m.group("sleeve")
        return ParsedSku(sku, f"Camisa {model}", "Ropa / Camisas", m.group("size"), SLEEVE_MAP[sleeve], model)
    raise ValueError("SKU sin formato ADAMS reconocido")


def make_external_id(parsed: ParsedSku) -> str:
    base = parsed.sku.lower().replace('/', '_').replace('-', '_').replace('.', '')
    return f"adams_{base}"


ALLOWED_TIE_WIDTHS = {"6", "6.5", "7", "7.5"}

def parse_adams_product(raw_sku: str, *, product_name_hint: str = "", category_hint: str = "") -> ParsedSku:
    sku = (raw_sku or "").strip()
    # Try original ADAMS formats first
    try:
        return parse_adams_sku(sku)
    except ValueError:
        pass

    hint = f"{product_name_hint} {category_hint}".lower()
    if "corbata" in hint:
        if "/" in sku:
            code, width = [p.strip() for p in sku.split("/", 1)]
            if not code or not width:
                raise ValueError("SKU de corbata incompleto")
            if width not in ALLOWED_TIE_WIDTHS:
                raise ValueError("Ancho Corbata no reconocido")
            return ParsedSku(sku, f"Corbata {code}", "Ropa / Corbatas", "", "", code, ancho_corbata=width)
        if sku:
            return ParsedSku(sku, f"Corbata {sku}", "Ropa / Corbatas", "", "", sku, ancho_corbata="Estándar")
    raise ValueError("SKU sin formato ADAMS reconocido")
