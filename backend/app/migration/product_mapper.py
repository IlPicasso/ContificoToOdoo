from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Any

SHIRT_SKU_PATTERN = re.compile(r"^(?P<model>\d+)-(?P<size>\d+(?:\.\d+)?)-(?P<sleeve>S[12])$")
SUIT_SKU_PATTERN = re.compile(r"^(?P<model>\d+)/(?P<size>\d+(?:\.\d+)?)$")

SLEEVE_TO_ODOO = {
    "S1": "S1 - 32/33",
    "S2": "S2 - 34/35",
}


@dataclass
class ExportProductRow:
    producto_madre: str
    sku: str
    codigo_barras: str
    categoria_odoo: str
    talla: str
    manga: str
    marca: str
    color: str
    precio_venta: float
    costo: float
    stock_bpu: float
    stock_tur: float
    stock_bat: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_sku(sku: str) -> tuple[str, str, str]:
    sku = sku.strip()
    suit_match = SUIT_SKU_PATTERN.match(sku)
    if suit_match:
        model = suit_match.group("model")
        size = suit_match.group("size")
        return f"Terno {model}", size, ""

    shirt_match = SHIRT_SKU_PATTERN.match(sku)
    if shirt_match:
        model = shirt_match.group("model")
        size = shirt_match.group("size")
        sleeve_key = shirt_match.group("sleeve")
        return f"Camisa {model}", size, SLEEVE_TO_ODOO[sleeve_key]

    return f"Producto {sku}", "", ""


def map_contifico_product(item: dict[str, Any]) -> ExportProductRow:
    sku = str(item.get("sku") or "").strip()
    producto_madre, talla, manga = parse_sku(sku)

    bodega_stock = item.get("stock_por_bodega") or {}

    return ExportProductRow(
        producto_madre=producto_madre,
        sku=sku,
        codigo_barras=str(item.get("codigo_barras") or ""),
        categoria_odoo=str(item.get("categoria_odoo") or "Ropa / Accesorios"),
        talla=talla,
        manga=manga,
        marca=str(item.get("marca") or "BRUNO CASSINI"),
        color=str(item.get("color") or ""),
        precio_venta=float(item.get("precio_venta") or 0),
        costo=float(item.get("costo") or 0),
        stock_bpu=float(bodega_stock.get("BPU") or 0),
        stock_tur=float(bodega_stock.get("TUR") or 0),
        stock_bat=float(bodega_stock.get("BAT") or 0),
    )
