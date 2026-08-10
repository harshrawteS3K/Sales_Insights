"""Reporting quarter / month normalization (Prompt 1A)."""

from app.utils.reporting_month import normalize_reporting_month


def test_strict_quarter_accepted():
    assert normalize_reporting_month("Q1 2026") == "Q1 2026"
    assert normalize_reporting_month("Q2 2026") == "Q2 2026"
    assert normalize_reporting_month("Q3 2026") == "Q3 2026"
    assert normalize_reporting_month("Q4 2026") == "Q4 2026"
    assert normalize_reporting_month("q1 2026") == "Q1 2026"
    assert normalize_reporting_month("  Q3   2026  ") == "Q3 2026"


def test_invalid_quarter_rejected():
    assert normalize_reporting_month("Quarter1") == ""
    assert normalize_reporting_month("2026 Q1") == ""
    assert normalize_reporting_month("Q5 2026") == ""
    assert normalize_reporting_month("Q1-2026") == ""
    assert normalize_reporting_month("Q1/2026") == ""


def test_legacy_month_still_works():
    assert normalize_reporting_month("July 2026") == "July 2026"
    assert normalize_reporting_month("Aug 2026") == "August 2026"
