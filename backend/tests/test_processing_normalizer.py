"""Unit tests for processing/normalizer.py — unified SKU parser."""
from __future__ import annotations

import pytest

from app.odoo_migration.processing.normalizer import parse_sku, ParsedSKU


class TestShirtPattern:
    def test_shirt_sku_parsed_correctly(self):
        result = parse_sku("C001-15-S1", name="Camisa modelo C001", category="Ropa / Camisas")
        assert result.base_key == "C001"
        assert result.talla == "15"
        assert result.manga == "S1 - 32/33"
        assert result.ancho_corbata == ""
        assert result.parse_rule == "shirt"
        assert result.parse_status == "PARSED"

    def test_shirt_s2_sleeve(self):
        result = parse_sku("300-16-S2", name="Camisa 300", category="Camisas")
        assert result.base_key == "300"
        assert result.talla == "16"
        assert result.manga == "S2 - 34/35"
        assert result.parse_rule == "shirt"

    def test_shirt_pattern_not_matched_without_camisa_category(self):
        # Same pattern but no camisa category → should NOT use shirt rule
        result = parse_sku("C001-15-S1", name="Terno C001", category="Ropa / Ternos")
        assert result.parse_rule != "shirt"
        # Will fall through to slash/hyphen patterns; since there's no slash, hyphen-size matches
        # The size will be "S1" and base "C001-15"
        assert result.parse_status in ("PARSED", "UNPARSED")

    def test_shirt_decimal_size(self):
        result = parse_sku("ABC-15.5-S1", name="Camisa ABC", category="Ropa / Camisas")
        assert result.base_key == "ABC"
        assert result.talla == "15.5"
        assert result.manga == "S1 - 32/33"


class TestTiePattern:
    def test_tie_hyphen_width(self):
        result = parse_sku("CR01-7", name="Corbata CR01", category="Corbatas")
        assert result.base_key == "CR01"
        assert result.ancho_corbata == "7 cm"
        assert result.talla == ""
        assert result.parse_rule == "tie_hyphen_width"
        assert result.parse_status == "PARSED"

    def test_tie_decimal_width(self):
        result = parse_sku("TIE-6.5", name="Corbata slim", category="Ropa / Hombres / Corbatas")
        assert result.ancho_corbata == "6.5 cm"
        assert result.parse_rule == "tie_hyphen_width"

    def test_tie_slash_width(self):
        result = parse_sku("CR10/7", name="Corbata CR10", category="Corbatas")
        assert result.ancho_corbata == "7 cm"
        assert result.parse_rule == "tie_slash_width"

    def test_tie_no_valid_width_fallback(self):
        result = parse_sku("CR01-ABC", name="Corbata CR01", category="Corbatas")
        assert result.parse_status == "UNPARSED"
        assert result.parse_rule == "tie_no_width"
        # Treated as simple
        assert result.base_key == "CR01-ABC"

    def test_non_tie_hyphen_not_treated_as_tie_width(self):
        result = parse_sku("P200-7", name="Pantalon talla 7", category="Ropa / Pantalones")
        # Should NOT be treated as tie width — should be generic hyphen-size
        assert result.ancho_corbata == ""
        assert result.talla == "7"


class TestSlashPattern:
    def test_suit_slash_size(self):
        result = parse_sku("T500/42", name="Terno T500", category="Ropa / Ternos")
        assert result.base_key == "T500"
        assert result.talla == "42"
        assert result.parse_rule == "slash_size"
        assert result.parse_status == "PARSED"

    def test_slash_alpha_size(self):
        result = parse_sku("VEST/XL", name="Chaleco VEST", category="Ropa / Chalecos")
        assert result.base_key == "VEST"
        assert result.talla == "XL"

    def test_slash_decimal_size(self):
        result = parse_sku("PT100/28.5", name="Pantalon", category="Ropa")
        assert result.base_key == "PT100"
        assert result.talla == "28.5"


class TestHyphenSizePattern:
    def test_generic_hyphen_size_letter(self):
        result = parse_sku("P200-L", name="Pantalon P200", category="Ropa")
        assert result.base_key == "P200"
        assert result.talla == "L"
        assert result.parse_rule == "hyphen_size"

    def test_generic_hyphen_size_number(self):
        result = parse_sku("PT-30", name="Pantalon", category="Ropa / Pantalones")
        assert result.talla == "30"

    def test_generic_hyphen_xxl(self):
        result = parse_sku("SHIRT-XXL", name="Camisa", category="Ropa")
        assert result.talla == "XXL"
        assert result.parse_rule == "hyphen_size"


class TestSimpleProduct:
    def test_simple_no_pattern(self):
        result = parse_sku("ITEM123", name="Accesorio", category="Accesorios")
        assert result.base_key == "ITEM123"
        assert result.talla == ""
        assert result.manga == ""
        assert result.ancho_corbata == ""
        assert result.parse_rule == "simple"
        assert result.has_attributes is False

    def test_empty_sku(self):
        result = parse_sku("", name="Producto", category="Ropa")
        assert result.parse_status == "ERROR"
        assert result.parse_rule == "empty"


class TestSpecialSuffixes:
    def test_bowtie_co_suffix(self):
        result = parse_sku("CB01-CO", name="Corbatín", category="Corbatas")
        assert result.base_key == "CB01"
        assert result.parse_rule == "bowtie"
        assert result.has_attributes is False

    def test_fajin_fj_suffix(self):
        result = parse_sku("FJ100-FJ", name="Fajín", category="Accesorios")
        assert result.base_key == "FJ100"
        assert result.parse_rule == "fajin"


class TestExternalIdDerivation:
    def test_template_external_id_slugified(self):
        result = parse_sku("C001-15-S1", name="Camisa", category="Camisas")
        assert result.template_external_id == "product_template_c001"

    def test_variant_external_id_from_sku(self):
        result = parse_sku("C001-15-S1", name="Camisa", category="Camisas")
        assert result.variant_external_id == "adams_c001_15_s1"

    def test_slash_in_sku_slugified(self):
        result = parse_sku("T500/42", name="Terno", category="Ternos")
        assert result.variant_external_id == "adams_t500_42"
