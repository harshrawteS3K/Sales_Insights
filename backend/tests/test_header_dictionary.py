"""Tests for configurable ERP header dictionary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.erp_parser.header_dictionary import (
    HeaderDictionary,
    normalize_header_text,
)
from app.erp_parser.header_mapper import best_field_match, map_headers


@pytest.fixture
def dict_file(tmp_path: Path) -> Path:
    path = tmp_path / "header_dictionary.json"
    payload = {
        "customer": ["customer", "party name", "buyer"],
        "product": ["product", "material", "item code"],
        "quantity": ["qty", "dispatch qty", "sales quantity"],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_json_loads(dict_file: Path):
    hd = HeaderDictionary(dict_file)
    assert "party name" in hd.get_customer_headers()
    assert "material" in hd.get_product_headers()
    assert "dispatch qty" in hd.get_quantity_headers()


def test_cache_works(dict_file: Path):
    hd = HeaderDictionary(dict_file)
    first = hd.get_customer_headers()
    # Mutate file on disk without reload — cache should still serve old data
    dict_file.write_text(
        json.dumps(
            {
                "customer": ["onlynew"],
                "product": ["product"],
                "quantity": ["qty"],
            }
        ),
        encoding="utf-8",
    )
    assert hd.get_customer_headers() == first
    reloaded = hd.reload()
    assert reloaded["customer"] == ["onlynew"]
    assert hd.get_customer_headers() == ["onlynew"]


def test_normalize_trailing_colon():
    assert normalize_header_text(" Party Name : ") == "party name"
    assert normalize_header_text("Dispatch Qty：") == "dispatch qty"


def test_duplicate_rejection(dict_file: Path):
    hd = HeaderDictionary(dict_file)
    with pytest.raises(ValueError, match="Duplicate"):
        hd.update(
            {
                "customer": ["buyer", "Buyer"],
                "product": ["product"],
                "quantity": ["qty"],
            }
        )


def test_empty_and_max_length_rejection(dict_file: Path):
    hd = HeaderDictionary(dict_file)
    with pytest.raises(ValueError, match="empty"):
        hd.update(
            {
                "customer": ["  "],
                "product": ["product"],
                "quantity": ["qty"],
            }
        )
    with pytest.raises(ValueError, match="100"):
        hd.update(
            {
                "customer": ["x" * 101],
                "product": ["product"],
                "quantity": ["qty"],
            }
        )


def test_api_update_and_live_reload(dict_file: Path):
    """Update persists + refreshes cache so next match uses new synonyms."""
    hd = HeaderDictionary(dict_file)

    from app.erp_parser import header_dictionary as hd_mod

    original = hd_mod._DICTIONARY
    hd_mod._DICTIONARY = hd
    try:
        _label, _score, method_before = best_field_match("vendormaster", "customer")
        assert method_before == "none"

        new_data, added, _removed = hd.update(
            {
                "customer": ["customer", "party name", "buyer", "vendormaster"],
                "product": ["product", "material", "item code"],
                "quantity": ["qty", "dispatch qty", "sales quantity"],
            }
        )
        assert "vendormaster" in added["customer"]
        assert "vendormaster" in new_data["customer"]

        # Live reload: same process, no restart — cache already refreshed by update()
        label, score, method = best_field_match("vendormaster", "customer")
        assert method == "exact"
        assert score == 100.0
        assert label == "Customer Name"

        disk = json.loads(dict_file.read_text(encoding="utf-8"))
        assert "vendormaster" in disk["customer"]
        assert all(h == h.lower() for h in disk["customer"])
    finally:
        hd_mod._DICTIONARY = original


def test_rapidfuzz_still_maps_correctly():
    """Default production dictionary still fuzzy-maps common ERP variants."""
    from app.erp_parser.header_dictionary import get_header_dictionary

    get_header_dictionary().reload()
    mapped = map_headers(["Party Name", "Material Description", "Dispatch Qty"])
    assert mapped["positions"]["customer"] == 0
    assert mapped["positions"]["product"] == 1
    assert mapped["positions"]["quantity"] == 2
    assert mapped["confidences"]["customer"] >= 90
    assert mapped["confidences"]["product"] >= 75
    assert mapped["confidences"]["quantity"] >= 90


def test_default_json_file_exists_and_loads():
    from app.erp_parser.header_dictionary import DEFAULT_DICTIONARY_PATH, get_header_dictionary

    assert DEFAULT_DICTIONARY_PATH.is_file()
    data = get_header_dictionary().reload()
    assert data["customer"]
    assert data["product"]
    assert data["quantity"]
