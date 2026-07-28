"""Unit tests for the intelligent confidence engine."""

from app.integrations.excel.confidence import compute_confidence_breakdown


def test_perfect_official_lands_in_95_99():
    details = {"name": "A", "company": "B", "address": "C", "phone": "D"}
    result = compute_confidence_breakdown(
        template_detected=True,
        sales_table_detected=True,
        is_official_template=True,
        distributor_details=details,
        expected_rows=10,
        imported_rows=10,
        incomplete_rows=0,
        parse_succeeded=True,
        mapping_strategy="official_template",
    )
    assert 95 <= result["total"] <= 99
    assert result["total"] != 100
    assert result["components"]["template_detection"] == 25.0


def test_missing_distributor_lowers_score():
    result = compute_confidence_breakdown(
        template_detected=True,
        sales_table_detected=True,
        is_official_template=True,
        distributor_details={},
        expected_rows=5,
        imported_rows=5,
        incomplete_rows=0,
        parse_succeeded=True,
        mapping_strategy="official_template",
    )
    assert result["total"] < 95
    assert result["components"]["distributor_details"] == 0.0


def test_parse_failure_stays_low():
    result = compute_confidence_breakdown(
        template_detected=False,
        sales_table_detected=False,
        is_official_template=False,
        distributor_details={},
        expected_rows=0,
        imported_rows=0,
        incomplete_rows=0,
        parse_succeeded=False,
        mapping_strategy="none",
    )
    assert result["total"] <= 40
