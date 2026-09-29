"""Row identity for incremental distributor uploads."""

from app.services.incremental_upload import analyse_rows, needs_review, public_plan

FY = "FY 2026-27 • Q1"


def _row(customer, product, month, qty):
    return {
        "customer_name": customer,
        "product": product,
        "source_month": month,
        "period": FY,
        "sales_quantity": qty,
    }


def _existing(record_id, customer, product, month, qty):
    return {
        "id": record_id,
        "customer_name": customer,
        "product": product,
        "source_month": month,
        "period": FY,
        "quantity": qty,
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


def test_changed_april_quantity_requires_review():
    plan = analyse_rows(
        [_row("VR Tex", "APCOTEX TX 400", "April 2026", 60)],
        [_existing(4, "VR Tex", "APCOTEX TX 400", "April 2026", 50)],
    )
    assert plan["modified_count"] == 1
    assert plan["status"] == "human_review"
    change = plan["modified_rows"][0]
    assert change["existing_qty"] == 50
    assert change["incoming_qty"] == 60
    assert change["difference"] == 10
    assert needs_review(plan, None) is True
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
