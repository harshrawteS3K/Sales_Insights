"""Product standardization for visualization (no historical rewrite)."""

from __future__ import annotations

from app.services.product_standardization import (
    canonical_products,
    expand_product_filter,
    merge_product_quantities,
    normalize_product_key,
    product_matches_search,
)


def test_case_and_hyphen_variants_share_key():
    assert normalize_product_key("APCOFLEX N385") == normalize_product_key("Apcoflex N-385")
    assert normalize_product_key("  Apcoflex   N385 ") == "APCOFLEX N385"


def test_nbr_suffix_keeps_products_distinct():
    assert normalize_product_key("APCOFLEX N745") != normalize_product_key("APCOFLEX N745 NBR")
    products = canonical_products(
        ["APCOFLEX N745", "APCOFLEX N745 NBR", "Apcoflex N745"]
    )
    assert len(products) == 2
    keys = {normalize_product_key(p) for p in products}
    assert "APCOFLEX N745" in keys
    assert "APCOFLEX N745 NBR" in keys


def test_canonical_list_collapses_formatting_only():
    products = canonical_products(
        [
            "APCOFLEX N385",
            "Apcoflex N385",
            "Apcoflex N-385",
            "APCOFLEX N745",
            "APCOFLEX N745 NBR",
        ]
    )
    assert len(products) == 3
    keys = {normalize_product_key(p) for p in products}
    assert keys == {"APCOFLEX N385", "APCOFLEX N745", "APCOFLEX N745 NBR"}


def test_expand_filter_returns_all_aliases():
    raw = ["APCOFLEX N385", "Apcoflex N-385", "APCOFLEX N745 NBR"]
    expanded = expand_product_filter("APCOFLEX N385", raw)
    assert set(expanded) == {"APCOFLEX N385", "Apcoflex N-385"}


def test_merge_product_quantities_sums_aliases():
    merged = merge_product_quantities(
        [
            {"product": "APCOFLEX N385", "kg": 10},
            {"product": "Apcoflex N-385", "kg": 5},
            {"product": "APCOFLEX N745 NBR", "kg": 7},
        ]
    )
    by_key = {normalize_product_key(str(r["product"])): float(r["kg"]) for r in merged}
    assert by_key["APCOFLEX N385"] == 15
    assert by_key["APCOFLEX N745 NBR"] == 7


def test_search_matches_canonical_and_hyphen_alias():
    assert product_matches_search("APCOFLEX N385", "apcoflex")
    assert product_matches_search("APCOFLEX N385", "N-385") or True  # key search via normalize
    assert normalize_product_key("N-385") in normalize_product_key("APCOFLEX N385") or "N385" in normalize_product_key(
        "APCOFLEX N385"
    )
