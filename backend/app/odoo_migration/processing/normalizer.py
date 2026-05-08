"""Unified SKU parser — single source of truth for SKU → parsed attributes.

Category disambiguation happens BEFORE pattern matching to correctly handle:
- Ties: hyphen suffix is tie width (not size)
- Suits/shoes: slash suffix is size (not something else)
- Shirts: BASE-SIZE-S[12] three-part pattern
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


SLEEVE_MAP = {"S1": "S1 - 32/33", "S2": "S2 - 34/35"}

TIE_WIDTHS = {"6", "6.5", "7", "7.5", "8"}

# Category keyword detectors (check against normalized upper-cased string)
_CAT_CORBATA = re.compile(r"CORBAT[AI]")
_CAT_CAMISA = re.compile(r"CAMISA")
_CAT_TERNO = re.compile(r"TERNO|TRAJE")
_CAT_LEVA = re.compile(r"LEVA|SACO|BLAZER")
_CAT_ZAPATO = re.compile(r"ZAPATO|ZP-")
_CAT_PANTALON = re.compile(r"PANTALON|PT-")
_CAT_CHALECO = re.compile(r"CHALECO|CH-")

# SKU patterns
_SHIRT_RE = re.compile(r"^(?P<base>[A-Za-z0-9]+)-(?P<size>\d+(?:\.\d+)?)-(?P<sleeve>S[12])$", re.IGNORECASE)
_SLASH_RE = re.compile(r"^(?P<base>.+)/(?P<size>[A-Za-z0-9]+(?:\.\d+)?)$")
_HYPHEN_SIZE_RE = re.compile(
    r"^(?P<base>.+)-(?P<size>XXL|XL|XS|L|M|S|\d+(?:\.\d+)?)$", re.IGNORECASE
)
_HYPHEN_WIDTH_RE = re.compile(r"^(?P<base>.+)-(?P<width>\d+(?:\.\d+)?)$")
_BOWTIE_RE = re.compile(r"^(?P<base>.+)-CO$", re.IGNORECASE)
_FAJIN_RE = re.compile(r"^(?P<base>.+)-FJ$", re.IGNORECASE)


def _norm(text: str) -> str:
    value = unicodedata.normalize("NFKD", (text or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", value.upper()).strip()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


def _format_cm(value: str) -> str:
    try:
        f = float(value)
        return f"{f:g} cm"
    except ValueError:
        return f"{value} cm"


@dataclass
class ParsedSKU:
    sku: str
    base_key: str
    # Attributes (empty string = not applicable)
    talla: str = ""
    manga: str = ""             # sleeve: "S1 - 32/33" or "S2 - 34/35"
    ancho_corbata: str = ""
    # Meta
    parse_rule: str = "fallback"
    parse_status: str = "UNPARSED"
    warnings: list[str] = field(default_factory=list)

    # Derived — set after construction
    template_external_id: str = ""
    variant_external_id: str = ""

    def __post_init__(self) -> None:
        self.template_external_id = f"product_template_{_slugify(self.base_key)}" if self.base_key else "product_template_unknown"
        self.variant_external_id = f"adams_{_slugify(self.sku)}" if self.sku else "adams_unknown"

    @property
    def has_attributes(self) -> bool:
        return bool(self.talla or self.manga or self.ancho_corbata)


def parse_sku(sku: str, name: str = "", category: str = "") -> ParsedSKU:
    """Parse a Contifico SKU into structured attributes.

    Category disambiguation runs first so that the same hyphen/slash means
    different things depending on the product type.
    """
    raw = (sku or "").strip()
    if not raw:
        return ParsedSKU(sku="", base_key="", parse_rule="empty", parse_status="ERROR",
                         warnings=["SKU vacío"])

    cat_norm = _norm(category)
    name_norm = _norm(name)
    combined = f"{cat_norm} {name_norm}"

    is_corbata = bool(_CAT_CORBATA.search(combined))
    is_camisa = bool(_CAT_CAMISA.search(combined))

    # ── 1. Bowtie / fajin (special suffixes, check before shirt) ──────────
    m = _BOWTIE_RE.match(raw)
    if m:
        base = m.group("base")
        return ParsedSKU(sku=raw, base_key=base, parse_rule="bowtie", parse_status="PARSED")

    m = _FAJIN_RE.match(raw)
    if m:
        base = m.group("base")
        return ParsedSKU(sku=raw, base_key=base, parse_rule="fajin", parse_status="PARSED")

    # ── 2. Shirt pattern: BASE-SIZE-S[12] (three parts) ───────────────────
    m = _SHIRT_RE.match(raw)
    if m and is_camisa:
        base = m.group("base")
        size = m.group("size")
        sleeve_raw = m.group("sleeve").upper()
        sleeve = SLEEVE_MAP.get(sleeve_raw, sleeve_raw)
        return ParsedSKU(sku=raw, base_key=base, talla=size, manga=sleeve,
                         parse_rule="shirt", parse_status="PARSED")

    # ── 3. Tie / corbata patterns ─────────────────────────────────────────
    if is_corbata:
        # Prefer hyphen-width pattern
        m = _HYPHEN_WIDTH_RE.match(raw)
        if m and m.group("width") in TIE_WIDTHS:
            base = m.group("base")
            ancho = _format_cm(m.group("width"))
            return ParsedSKU(sku=raw, base_key=base, ancho_corbata=ancho,
                             parse_rule="tie_hyphen_width", parse_status="PARSED")
        # Slash-width pattern
        m_slash = _SLASH_RE.match(raw)
        if m_slash and m_slash.group("size") in TIE_WIDTHS:
            base = m_slash.group("base")
            ancho = _format_cm(m_slash.group("size"))
            return ParsedSKU(sku=raw, base_key=base, ancho_corbata=ancho,
                             parse_rule="tie_slash_width", parse_status="PARSED")
        # Corbata but no recognizable width → treat as simple
        return ParsedSKU(sku=raw, base_key=raw, parse_rule="tie_no_width",
                         parse_status="UNPARSED",
                         warnings=["Corbata sin ancho reconocible; tratado como simple"])

    # ── 4. Slash-size pattern: BASE/SIZE ──────────────────────────────────
    m = _SLASH_RE.match(raw)
    if m:
        base = m.group("base")
        size = m.group("size").upper()
        return ParsedSKU(sku=raw, base_key=base, talla=size,
                         parse_rule="slash_size", parse_status="PARSED")

    # ── 5. Generic hyphen-size: BASE-SIZE ─────────────────────────────────
    m = _HYPHEN_SIZE_RE.match(raw)
    if m:
        base = m.group("base")
        size = m.group("size").upper()
        return ParsedSKU(sku=raw, base_key=base, talla=size,
                         parse_rule="hyphen_size", parse_status="PARSED")

    # ── 6. Fallback: treat entire SKU as its own base (simple product) ────
    return ParsedSKU(sku=raw, base_key=raw, parse_rule="simple",
                     parse_status="UNPARSED")
