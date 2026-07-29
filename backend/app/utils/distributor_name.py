"""Distributor name normalization for stable business identity matching."""

from __future__ import annotations


def normalize_distributor_name(name: str | None) -> str:
    """
    Canonicalize distributor display names for lookup / create.

    - trim ends
    - collapse internal whitespace
    Does not change case of stored values; matching uses casefold separately.
    """
    if not name:
        return ""
    return " ".join(str(name).split())
