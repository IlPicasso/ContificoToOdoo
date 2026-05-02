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
