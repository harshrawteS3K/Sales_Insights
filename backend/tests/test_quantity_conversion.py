"""Unit conversion helpers — app canonical unit is MT."""

from decimal import Decimal

from app.utils.quantity import kg_to_mt, mt_to_kg, parse_quantity_as_mt, to_mt


def test_kg_to_mt_and_back():
    assert kg_to_mt(1000) == Decimal("1")
    assert kg_to_mt(1250.5) == Decimal("1.250500")
    assert mt_to_kg(1) == Decimal("1000.000")


def test_to_mt_from_kg_default():
    assert to_mt(10000, source_unit="KG") == Decimal("10.000000")
    assert to_mt(10, source_unit="MT") == Decimal("10")


def test_parse_quantity_as_mt():
    mt, display = parse_quantity_as_mt("1,250.5", source_unit="KG")
    assert mt == Decimal("1.250500")
    assert "1.25" in display
