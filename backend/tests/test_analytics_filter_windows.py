"""Analytics filter windows stay distinct and every chart uses the same quantity."""

from datetime import date

from app.services.sales_insights_service import (
    _month_trend_points,
    _period_year_months,
    resolve_period_month_keys,
)
from app.utils.quantity import kg_to_mt_display


def test_rolling_windows_are_different_lengths():
    as_of = date(2026, 9, 28)
    last_3 = _period_year_months("last_3_months", as_of=as_of)
    last_6 = _period_year_months("last_6_months", as_of=as_of)
    last_12 = _period_year_months("last_12_months", as_of=as_of)
    assert last_3 is not None and last_6 is not None and last_12 is not None
    assert len(last_3) == 3
    assert len(last_6) == 6
    assert len(last_12) == 12
    assert last_3 == last_6[-3:]
    assert last_6 == last_12[-6:]
    assert last_12 != last_6
    assert last_12[0] == (2025, 10)
    assert last_3[0] == (2026, 7)


def test_fy_2025_matches_stored_quarter_and_annual_labels():
    keys = resolve_period_month_keys("full_year", fiscal_year_start=2025)
    assert keys is not None
    assert "FY 2025-26" in keys
    assert "FY 2025–26" in keys
    assert "FY 2025-26 • Q1" in keys
    assert "April 2025" in keys
    assert "March 2026" in keys
    assert "FY 2026-27 • Q1" not in keys

    q1 = resolve_period_month_keys("q1", fiscal_year_start=2025)
    assert q1 is not None
    assert "FY 2025-26 • Q1" in q1
    assert "April 2025" in q1
    assert "FY 2025-26" not in q1
    assert "July 2025" not in q1


def test_trend_keeps_month_rows_and_quarter_rows():
    window = [(2025, 4), (2025, 5), (2025, 6)]
    points = _month_trend_points(
        [
            ("April 2025", None, "FY 2025-26 • Q1", "FY 2025-26", 500.0),
            (None, None, "FY 2025-26 • Q1", "FY 2025-26", 1000.0),
        ],
        window,
    )
    assert [point["month"] for point in points] == ["Apr", "May", "Jun"]
    assert abs(sum(point["kg"] for point in points) - 1500.0) < 0.001
    assert abs(kg_to_mt_display(sum(point["kg"] for point in points)) - 1.5) <= 0.001
