"""PDF monthly rows must not collapse on customer+product+quantity alone."""

from datetime import date
from decimal import Decimal

from app.erp_parser.pdf_stock_register import extract_pdf_stock_register_rows
from app.services.incremental_upload import (
    analyse_rows,
    needs_review,
    rows_for_insert,
    transaction_date_of,
)
from app.utils.period_calendar import month_label


def _pdf_matrix_three_months():
    """Purandar-style lines: same customer/product/qty in June, July, August."""
    return [
        ["New India Rubber Works Pvt.Ltd. 3000 Kgs."],
        ["18-Jun-26 Apcotex SR-568 1000 Kgs."],
        ["16-Jul-26 Apcotex SR-568 1000 Kgs."],
        ["26-Aug-26 Apcotex SR-568 1000 Kgs."],
    ]


def test_pdf_extracts_three_dated_rows_not_collapsed():
    extracted = extract_pdf_stock_register_rows(_pdf_matrix_three_months())
    assert extracted is not None
    rows = extracted["rows"]
    assert len(rows) == 3
    months = [row["source_month"] for row in rows]
    assert months == ["June 2026", "July 2026", "August 2026"]
    assert all(row["customer_name"] == "New India Rubber Works Pvt.Ltd." for row in rows)
    assert all(row["product"] == "Apcotex SR-568" for row in rows)
    assert all(Decimal(str(row["sales_quantity"])) == Decimal("1000") for row in rows)
    assert {row["period"] for row in rows} == {
        "FY 2026-27 • Q1",
        "FY 2026-27 • Q2",
    }
    assert rows[0]["transaction_date"] == date(2026, 6, 18).isoformat()
    assert rows[1]["transaction_date"] == date(2026, 7, 16).isoformat()
    assert rows[2]["transaction_date"] == date(2026, 8, 26).isoformat()


def test_a_different_months_same_qty_are_three_new_records():
    """A) Same customer + product + qty + DIFFERENT month → 3 NEW."""
    incoming = extract_pdf_stock_register_rows(_pdf_matrix_three_months())["rows"]
    plan = analyse_rows(incoming, [])
    assert plan["new_count"] == 3
    assert plan["exact_count"] == 0
    assert plan["modified_count"] == 0
    assert plan["status"] == "ready"
    assert len(rows_for_insert(incoming, plan, None, confirm_add=True)) == 3


def test_b_same_month_same_qty_is_exact_duplicate():
    """B) Same customer + product + qty + SAME month → Exact duplicate."""
    incoming = [
        {
            "customer_name": "New India Rubber Works Pvt.Ltd.",
            "product": "Apcotex SR-568",
            "sales_quantity": 1000,
            "period": "FY 2026-27 • Q1",
            "source_month": "June 2026",
            "transaction_date": "2026-06-18",
        }
    ]
    existing = [
        {
            "id": 11,
            "customer_name": "New India Rubber Works Pvt.Ltd.",
            "product": "Apcotex SR-568",
            "quantity": 1000,
            "period": "FY 2026-27 • Q1",
            "source_month": "June 2026",
        }
    ]
    plan = analyse_rows(incoming, existing)
    assert plan["exact_count"] == 1
    assert plan["new_count"] == 0
    assert plan["status"] == "duplicate_upload"
    assert rows_for_insert(incoming, plan, None, confirm_add=True) == []


def test_c_same_month_different_qty_is_modified():
    """C) Same customer + product + month + DIFFERENT qty → Modified/conflict."""
    incoming = [
        {
            "customer_name": "New India Rubber Works Pvt.Ltd.",
            "product": "Apcotex SR-568",
            "sales_quantity": 1200,
            "period": "FY 2026-27 • Q1",
            "source_month": "June 2026",
        }
    ]
    existing = [
        {
            "id": 12,
            "customer_name": "New India Rubber Works Pvt.Ltd.",
            "product": "Apcotex SR-568",
            "quantity": 1000,
            "period": "FY 2026-27 • Q1",
            "source_month": "June 2026",
        }
    ]
    plan = analyse_rows(incoming, existing)
    assert plan["modified_count"] == 1
    assert plan["new_count"] == 0
    assert plan["exact_count"] == 0
    assert needs_review(plan, None) is True


def test_d_resubmit_same_pdf_rows_are_exact_duplicates():
    """D) Same PDF rows submitted again → Exact duplicates, skip."""
    incoming = extract_pdf_stock_register_rows(_pdf_matrix_three_months())["rows"]
    existing = [
        {
            "id": idx + 1,
            "customer_name": row["customer_name"],
            "product": row["product"],
            "quantity": row["sales_quantity"],
            "period": row["period"],
            "source_month": row["source_month"],
        }
        for idx, row in enumerate(incoming)
    ]
    plan = analyse_rows(incoming, existing)
    assert plan["exact_count"] == 3
    assert plan["new_count"] == 0
    assert plan["modified_count"] == 0
    assert plan["status"] == "duplicate_upload"
    assert rows_for_insert(incoming, plan, None, confirm_add=True) == []


def test_e_multi_quarter_june_q1_july_august_q2_all_kept():
    """E) June=Q1, July/August=Q2 — all three remain distinct NEW records."""
    incoming = extract_pdf_stock_register_rows(_pdf_matrix_three_months())["rows"]
    assert incoming[0]["period"].endswith("Q1")
    assert incoming[1]["period"].endswith("Q2")
    assert incoming[2]["period"].endswith("Q2")
    # Existing has only June — July and August must still be NEW
    existing = [
        {
            "id": 1,
            "customer_name": "New India Rubber Works Pvt.Ltd.",
            "product": "Apcotex SR-568",
            "quantity": 1000,
            "period": "FY 2026-27 • Q1",
            "source_month": "June 2026",
        }
    ]
    plan = analyse_rows(incoming, existing)
    assert plan["exact_count"] == 1
    assert plan["new_count"] == 2
    assert plan["modified_count"] == 0
    inserted = rows_for_insert(incoming, plan, None, confirm_add=True)
    assert len(inserted) == 2
    assert {row["source_month"] for row in inserted} == {"July 2026", "August 2026"}


def test_transaction_date_of_never_uses_quarter_period():
    """Quarter labels must not become the monthly identity key."""
    assert transaction_date_of({"period": "FY 2026-27 • Q2"}) == ""
    assert transaction_date_of(
        {"source_month": "July 2026", "period": "FY 2026-27 • Q2"}
    ) == "July 2026"
    assert transaction_date_of({"transaction_date": "2026-08-26"}) == month_label(8, 2026)
    assert transaction_date_of({"transaction_date": "26-Aug-26"}) == month_label(8, 2026)


def test_period_fallback_no_longer_collapses_july_and_august():
    """Regression: without source_month, period fallback used to make Jul=Aug exact."""
    incoming = [
        {
            "customer_name": "New India Rubber Works Pvt.Ltd.",
            "product": "Apcotex SR-568",
            "sales_quantity": 1000,
            "period": "FY 2026-27 • Q2",
            "transaction_date": "2026-07-16",
        },
        {
            "customer_name": "New India Rubber Works Pvt.Ltd.",
            "product": "Apcotex SR-568",
            "sales_quantity": 1000,
            "period": "FY 2026-27 • Q2",
            "transaction_date": "2026-08-26",
        },
    ]
    plan = analyse_rows(incoming, [])
    assert plan["new_count"] == 2
    assert plan["exact_count"] == 0
