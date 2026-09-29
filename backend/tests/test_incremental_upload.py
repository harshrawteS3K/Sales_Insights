"""Row identity for incremental distributor uploads."""

from app.services.incremental_upload import (
    CONFIRM_ADD_MESSAGE,
    analyse_rows,
    needs_review,
    public_plan,
    rows_for_insert,
)

FY = "FY 2026-27 • Q1"


def _row(customer, product, month, qty, *, location="", segment=""):
    return {
        "customer_name": customer,
        "product": product,
        "source_month": month,
        "period": FY,
        "sales_quantity": qty,
        "location": location,
        "segment": segment,
    }


def _existing(record_id, customer, product, month, qty, *, location="", segment=""):
    return {
        "id": record_id,
        "customer_name": customer,
        "product": product,
        "source_month": month,
        "period": FY,
        "quantity": qty,
        "location": location,
        "segment": segment,
    }


def test_same_april_quantity_is_exact_duplicate():
    plan = analyse_rows(
        [_row("Bata", "APCOTEX TX 400", "April 2026", 100)],
        [_existing(1, "Bata", "APCOTEX TX 400", "April 2026", 100)],
    )
    assert plan["exact_count"] == 1
    assert plan["new_count"] == 0
    assert plan["modified_count"] == 0
    assert plan["status"] == "duplicate_upload"
    assert public_plan(plan)["modified_rows"] == []


def test_changed_april_quantity_requires_confirm_add():
    plan = analyse_rows(
        [_row("VR Tex", "APCOTEX TX 400", "April 2026", 60)],
        [_existing(4, "VR Tex", "APCOTEX TX 400", "April 2026", 50)],
    )
    assert plan["modified_count"] == 1
    assert plan["status"] == "confirm_add"
    assert plan["recommendation"] == CONFIRM_ADD_MESSAGE
    change = plan["modified_rows"][0]
    assert change["existing_qty"] == 50
    assert change["incoming_qty"] == 60
    assert change["difference"] == 10
    assert needs_review(plan, None) is True
    assert needs_review(plan, None, confirm_add=True) is False
    assert needs_review(plan, [{"row_index": change["row_index"], "action": "keep"}]) is False


def test_may_after_april_is_new():
    plan = analyse_rows(
        [_row("Bata", "APCOTEX TX 400", "May 2026", 120)],
        [_existing(1, "Bata", "APCOTEX TX 400", "April 2026", 100)],
    )
    assert plan["new_count"] == 1
    assert plan["status"] == "ready"


def test_workbook_inserts_only_the_missing_month():
    plan = analyse_rows(
        [
            _row("Bata", "APCOTEX TX 400", "April 2026", 100),
            _row("Bata", "APCOTEX TX 400", "May 2026", 80),
        ],
        [_existing(1, "Bata", "APCOTEX TX 400", "April 2026", 100)],
    )
    assert plan["exact_count"] == 1
    assert plan["new_count"] == 1
    assert plan["modified_count"] == 0
    assert plan["status"] == "confirm_add"


def test_same_customer_different_product_is_new():
    plan = analyse_rows(
        [_row("Bata", "APCOTEX SR 558", "April 2026", 100)],
        [_existing(1, "Bata", "APCOTEX TX 400", "April 2026", 100)],
    )
    assert plan["new_count"] == 1


def test_same_product_different_date_is_new():
    plan = analyse_rows(
        [_row("Bata", "APCOTEX TX 400", "June 2026", 100)],
        [_existing(1, "Bata", "APCOTEX TX 400", "April 2026", 100)],
    )
    assert plan["new_count"] == 1


def test_one_modified_row_is_the_only_line_shown():
    incoming = [_row("Bata", "APCOTEX TX 400", "April 2026", 100)] * 2
    incoming.append(_row("Bata", "APCOTEX TX 400", "April 2026", 90))
    existing = [_existing(1, "Bata", "APCOTEX TX 400", "April 2026", 100)]
    plan = analyse_rows(incoming, existing)
    assert plan["analysed"] == 3
    assert plan["exact_count"] == 2
    assert plan["modified_count"] == 1
    assert len(public_plan(plan)["modified_rows"]) == 1
    assert "rows" not in public_plan(plan)


def test_identical_quarter_is_duplicate_upload():
    rows = [
        _row("Bata", "APCOTEX TX 400", "April 2026", 100),
        _row("Bata", "APCOTEX TX 400", "May 2026", 50),
    ]
    existing = [
        _existing(1, "Bata", "APCOTEX TX 400", "April 2026", 100),
        _existing(2, "Bata", "APCOTEX TX 400", "May 2026", 50),
    ]
    plan = analyse_rows(rows, existing)
    assert plan["new_count"] == 0
    assert plan["modified_count"] == 0
    assert plan["exact_count"] == 2
    assert plan["status"] == "duplicate_upload"


def test_a_same_distributor_india_west_matches_existing():
    """A) Same distributor + INDIA WEST → treated as existing scope."""
    existing = [
        _existing(
            1,
            "Classic",
            "TX",
            "April 2026",
            10,
            location="INDIA WEST",
            segment="CONSTRUCTION",
        )
    ]
    plan = analyse_rows(
        [_row("Classic", "TX", "April 2026", 10, location="INDIA WEST", segment="CONSTRUCTION")],
        existing,
        location="INDIA WEST",
        segment="CONSTRUCTION",
    )
    assert plan["exact_count"] == 1
    assert plan["new_count"] == 0
    assert plan["status"] == "duplicate_upload"


def test_b_same_distributor_india_east_is_separate_row():
    """B) Same distributor + INDIA EAST → accepted as separate consolidation row."""
    existing_west = [
        _existing(
            1,
            "Classic",
            "TX",
            "April 2026",
            10,
            location="INDIA WEST",
            segment="CONSTRUCTION",
        )
    ]
    # Scoped load for EAST finds nothing — EAST row is new.
    plan = analyse_rows(
        [_row("Classic", "TX", "April 2026", 10, location="INDIA EAST", segment="CONSTRUCTION")],
        [],
        location="INDIA EAST",
        segment="CONSTRUCTION",
    )
    assert plan["new_count"] == 1
    assert plan["status"] == "ready"
    # Even if west rows were wrongly passed in, identity must not collide.
    plan_mixed = analyse_rows(
        [_row("Classic", "TX", "April 2026", 10, location="INDIA EAST", segment="CONSTRUCTION")],
        existing_west,
        location="INDIA EAST",
        segment="CONSTRUCTION",
    )
    assert plan_mixed["new_count"] == 1
    assert plan_mixed["exact_count"] == 0


def test_c_confirm_add_yes_imports_only_new_rows():
    """C) Some duplicate + some new → confirmation YES imports new rows only."""
    existing = [
        _existing(
            1,
            "Classic",
            "TX",
            "April 2026",
            10,
            location="INDIA WEST",
            segment="CONSTRUCTION",
        )
    ]
    incoming = [
        _row("Classic", "TX", "April 2026", 10, location="INDIA WEST", segment="CONSTRUCTION"),
        _row("Classic", "TX", "May 2026", 20, location="INDIA WEST", segment="CONSTRUCTION"),
    ]
    plan = analyse_rows(incoming, existing, location="INDIA WEST", segment="CONSTRUCTION")
    assert plan["exact_count"] == 1
    assert plan["new_count"] == 1
    assert plan["status"] == "confirm_add"
    assert needs_review(plan, None) is True
    assert needs_review(plan, None, confirm_add=True) is False
    inserted = rows_for_insert(incoming, plan, None, confirm_add=True)
    assert len(inserted) == 1
    assert inserted[0]["source_month"] == "May 2026"


def test_d_confirm_add_no_leaves_data_unchanged():
    """D) Same case → NO leaves data unchanged (review gate, no insert)."""
    existing = [
        _existing(
            1,
            "Classic",
            "TX",
            "April 2026",
            10,
            location="INDIA WEST",
            segment="CONSTRUCTION",
        )
    ]
    incoming = [
        _row("Classic", "TX", "April 2026", 10, location="INDIA WEST", segment="CONSTRUCTION"),
        _row("Classic", "TX", "May 2026", 20, location="INDIA WEST", segment="CONSTRUCTION"),
    ]
    plan = analyse_rows(incoming, existing, location="INDIA WEST", segment="CONSTRUCTION")
    assert plan["status"] == "confirm_add"
    assert needs_review(plan, None, confirm_add=False) is True
    # Without confirm_add the import path must not proceed past the review gate.
    assert needs_review(plan, None, confirm_add=True) is False


def test_e_exact_duplicate_upload_inserts_nothing():
    """E) Exact duplicate upload does not create another identical record."""
    rows = [
        _row("Classic", "TX", "April 2026", 10, location="INDIA WEST", segment="CONSTRUCTION"),
    ]
    existing = [
        _existing(
            1,
            "Classic",
            "TX",
            "April 2026",
            10,
            location="INDIA WEST",
            segment="CONSTRUCTION",
        )
    ]
    plan = analyse_rows(rows, existing, location="INDIA WEST", segment="CONSTRUCTION")
    assert plan["status"] == "duplicate_upload"
    assert plan["exact_count"] == 1
    assert plan["new_count"] == 0
    assert needs_review(plan, None) is False
    assert rows_for_insert(rows, plan, None, confirm_add=True) == []
