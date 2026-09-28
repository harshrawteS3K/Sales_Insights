"""Unit conversion helpers — default MT is passthrough; KG is optional ÷1000."""

from decimal import Decimal

from app.utils.quantity import kg_to_mt, mt_to_kg, parse_quantity_as_mt, to_mt


def test_analytics_kg_to_mt_keeps_two_decimals():
    from app.utils.quantity import kg_to_mt_display

    assert kg_to_mt_display(None) == 0.0
    assert kg_to_mt_display(0) == 0.0
    assert kg_to_mt_display(3000) == 3.00
    assert kg_to_mt_display(2000) == 2.00
    assert kg_to_mt_display(1000) == 1.00
    assert kg_to_mt_display(600) == 0.60
    assert kg_to_mt_display(500) == 0.50
    assert kg_to_mt_display(225) == 0.23
    assert kg_to_mt_display(150) == 0.15
    assert kg_to_mt_display(25) == 0.03


def test_kg_to_mt_and_back():
    assert kg_to_mt(1000) == Decimal("1")
    assert kg_to_mt(1250.5) == Decimal("1.250500")
    assert mt_to_kg(1) == Decimal("1000.000")


def test_to_mt_default_passthrough():
    # Default source is MT — Excel numbers stay as-is
    assert to_mt(10000) == Decimal("10000")
    assert to_mt(10, source_unit="MT") == Decimal("10")
    assert to_mt(10000, source_unit="KG") == Decimal("10.000000")


def test_parse_quantity_as_mt_passthrough():
    mt, display = parse_quantity_as_mt("1,250.5", source_unit="MT")
    assert mt == Decimal("1250.5")
    assert "1,250.5" in display or "1250.5" in display
