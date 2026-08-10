"""Customer name normalization for distributor mapping."""

from __future__ import annotations

import re


_WS = re.compile(r"\s+")


def normalize_customer_name(value: object) -> str:
    """Trim, collapse whitespace, preserve display casing of first occurrence."""
    if value is None:
        return ""
    text = _WS.sub(" ", str(value).strip())
    return text


def customer_name_key(value: object) -> str:
    """Case-insensitive uniqueness key."""
    return normalize_customer_name(value).casefold()
