"""Unit conversion helpers — default MT is passthrough; KG is optional ÷1000."""

from decimal import Decimal

from app.utils.quantity import (
    format_mt,
    kg_to_mt,
    kg_to_mt_display,
    mt_to_kg,
    parse_quantity_as_mt,
    quantity_as_mt,
    round_mt,
    to_mt,
)


def test_analytics_kg_to_mt_keeps_three_decimals():
    assert kg_to_mt_display(None) == 0.0
    assert kg_to_mt_display(0) == 0.0
    assert kg_to_mt_display(3000) == 3.0
    assert kg_to_mt_display(2000) == 2.0
    assert kg_to_mt_display(1000) == 1.0
    assert kg_to_mt_display(600) == 0.6
    assert kg_to_mt_display(500) == 0.5
    assert kg_to_mt_display(225) == 0.225
    assert kg_to_mt_display(150) == 0.15
    assert kg_to_mt_display(75) == 0.075
    assert kg_to_mt_display(25) == 0.025
    assert format_mt(kg_to_mt_display(75)) == "0.075"
    assert format_mt(kg_to_mt_display(3000)) == "3.000"
    assert format_mt(kg_to_mt_display(25)) == "0.025"


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


def test_a_source_mt_display_mt_unchanged():
    """A) Source MT → display MT unchanged (Classic Solvents subject | MT)."""
    assert to_mt(Decimal("33.44"), source_unit="MT") == Decimal("33.44")
    assert to_mt(Decimal("3.30"), source_unit="MT") == Decimal("3.30")
    assert to_mt(Decimal("28.38"), source_unit="MT") == Decimal("28.38")
    assert quantity_as_mt(Decimal("65.12"), unit="MT", original_unit="MT") == Decimal("65.12")
    assert round_mt(quantity_as_mt(65.12, unit="MT")) == 65.12
    assert format_mt(quantity_as_mt(33.44, unit="MT")) == "33.440"


def test_b_source_kg_display_mt_divides_by_1000():
    """B) Source KG → display MT /1000."""
    assert to_mt(65, source_unit="KG") == Decimal("0.065000")
    assert quantity_as_mt(65, unit="KG", original_unit="KG") == Decimal("0.065000")
    assert round_mt(quantity_as_mt(65, unit="KG")) == 0.065
    assert format_mt(quantity_as_mt(65, unit="KG")) == "0.065"


def test_c_q1_aggregation_for_mt():
    """C) Q1 aggregation for MT: 33.44 + 3.30 + 28.38 = 65.12."""
    months = [Decimal("33.44"), Decimal("3.30"), Decimal("28.38")]
    q1 = sum(quantity_as_mt(v, unit="MT", original_unit="MT") for v in months)
    assert q1 == Decimal("65.12")
    assert round_mt(q1) == 65.12
    q2 = quantity_as_mt(Decimal("5.06"), unit="MT") + quantity_as_mt(
        Decimal("45.54"), unit="MT"
    )
    assert q2 == Decimal("50.60")
    assert round_mt(q1 + q2) == 115.72


def test_d_q1_aggregation_for_kg():
    """D) Q1 aggregation for KG: convert each month then sum."""
    months_kg = [Decimal("33440"), Decimal("3300"), Decimal("28380")]
    q1 = sum(quantity_as_mt(v, unit="KG", original_unit="KG") for v in months_kg)
    assert q1 == Decimal("65.120000")
    assert round_mt(q1) == 65.12


def test_e_mixed_records_respect_each_source_unit():
    """E) Mixed records must respect each record's source unit."""
    mt_row = quantity_as_mt(Decimal("65.12"), unit="MT", original_unit="MT")
    kg_row = quantity_as_mt(Decimal("65000"), unit="KG", original_unit="KG")
    # Both represent 65.12 MT when converted for display
    assert round_mt(mt_row) == 65.12
    assert round_mt(kg_row) == 65.0
    # Never divide an MT row
    assert quantity_as_mt(Decimal("65.12"), unit="MT", original_unit="KG") == Decimal("65.12")
    # KG-only (unit still KG) must divide
    assert quantity_as_mt(Decimal("65.12"), unit="KG", original_unit="KG") == Decimal("0.065120")
