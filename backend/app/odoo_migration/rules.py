from __future__ import annotations
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _load_json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding='utf-8'))

CATEGORY_ALIASES = _load_json('config/category_aliases.json')
BRAND_ALIASES = _load_json('config/brand_aliases.json')
COLOR_ALIASES = _load_json('config/color_aliases.json')
PATTERNS = {k: re.compile(v) for k, v in _load_json('config/sku_patterns.json').items()}


def normalize_text(text: str) -> str:
    value = unicodedata.normalize('NFKD', (text or '')).encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'\s+', ' ', value.upper()).strip()


def detect_brand(marca_nombre: str, nombre: str = '') -> str:
    normalized = normalize_text(marca_nombre or nombre)
    for alias, brand in BRAND_ALIASES.items():
        if alias in normalized:
            return brand
    return ''


def detect_color(nombre: str) -> str:
    normalized = normalize_text(nombre)
    found = [v for k, v in COLOR_ALIASES.items() if k in normalized]
    found = list(dict.fromkeys(found))
    if len(found) > 1:
        return 'Multicolor'
    return found[0] if found else ''


def detect_category(nombre: str, categoria_raw: str = '', sku: str = '') -> str:
    source = f"{normalize_text(categoria_raw)} {normalize_text(nombre)}"
    sku_norm = normalize_text(sku)
    if sku_norm.startswith("ZP-"):
        if "MUJER" in source or "DAMA" in source:
            return "Ropa / Mujeres / Zapatos"
        return "Ropa / Hombres / Zapatos"

    woman_hint = "MUJER" in source or "DAMA" in source
    if woman_hint:
        if "PANTALON" in source:
            return "Ropa / Mujeres / Pantalones"
        if "JEANS" in source:
            return "Ropa / Mujeres / Jeans"
        if "ZAPATO" in source:
            return "Ropa / Mujeres / Zapatos"
        if "BERMUDA" in source:
            return "Ropa / Mujeres / Bermudas"
        for key, cat in CATEGORY_ALIASES.items():
            if key in source and cat.startswith("Ropa / Mujeres"):
                return cat
    for key, cat in CATEGORY_ALIASES.items():
        if key in source:
            return cat
    return ''


def calculate_total_stock(stock_map: dict[str, float]) -> float:
    return float(sum(float(v or 0) for v in stock_map.values()))


def should_exclude_zero_stock(total_stock: float) -> bool:
    return total_stock <= 0


def parse_shirt_sku(sku: str):
    m = PATTERNS['shirt'].match(sku)
    if not m:
        return None
    sleeve = 'S1 - 32/33' if m.group('sleeve') == 'S1' else 'S2 - 34/35'
    return {'product_name': f"Camisa {m.group('model')}", 'talla': m.group('size'), 'manga': sleeve, 'parser_rule': 'shirt'}


def parse_suit_sku(sku: str):
    m = PATTERNS['suit'].match(sku)
    if not m:
        return None
    return {'product_name': f"Terno {m.group('base')}", 'talla': m.group('size'), 'parser_rule': 'suit'}


def parse_blazer_sku(sku: str):
    m = PATTERNS['suit'].match(sku)
    if not m:
        return None
    return {'product_name': f"Leva {m.group('base')}", 'talla': m.group('size'), 'parser_rule': 'blazer'}


def parse_tie_sku(sku: str):
    m = PATTERNS['tie_width'].match(sku)
    if not m:
        return None
    return {'product_name': f"Corbata {m.group('base')}", 'ancho_corbata': m.group('width'), 'parser_rule': 'tie_width'}


def parse_bowtie_sku(sku: str):
    m = PATTERNS['bowtie'].match(sku)
    if not m:
        return None
    return {'product_name': f"Corbatín {m.group('base')}", 'parser_rule': 'bowtie'}


def parse_fajin_sku(sku: str):
    m = PATTERNS['fajin'].match(sku)
    if not m:
        return None
    return {'product_name': f"Set Corbatín + Faja {m.group('base')}", 'parser_rule': 'fajin'}


def parse_generic_size(sku: str):
    norm = normalize_text(sku)
    m = re.search(r'(?:/|-)(?:T)?(\d{2}(?:\.\d)?)$', norm)
    if m:
        return m.group(1)
    m = re.search(r'(?:/|-)([SMLX]{1,3})$', norm)
    return m.group(1) if m else ''


def build_product_values(*, talla='', manga='', ancho_corbata='', marca='', color=''):
    parts = []
    if talla: parts.append(f'Talla:{talla}')
    if manga: parts.append(f'Manga de Camisa:{manga}')
    if ancho_corbata: parts.append(f'Ancho de Corbata:{ancho_corbata}')
    if marca: parts.append(f'Marca:{marca}')
    if color: parts.append(f'Color:{color}')
    return ','.join(parts)


def build_external_id(sku: str):
    return 'adams_' + re.sub(r'[^a-z0-9]+', '_', sku.lower()).strip('_')


def build_mapping_report_row(**kwargs):
    return kwargs


def build_error_row(**kwargs):
    return kwargs


def build_zero_stock_exclusion_row(**kwargs):
    kwargs['motivo_exclusion'] = 'stock_total_0'
    return kwargs
