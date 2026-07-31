"""Distributor / company name normalization for stable business identity matching."""

from __future__ import annotations


def normalize_distributor_name(name: str | None) -> str:
    """
    Canonicalize distributor representative display names.

    - trim ends
    - collapse internal whitespace
    Does not change case of stored values; matching uses casefold separately.
    """
    if not name:
        return ""
    return " ".join(str(name).split())


def normalize_company_name(company: str | None) -> str:
    """
    Canonicalize Distributor Company — the permanent business entity key.

    Used for get-or-create, report replacement, and uniqueness.
    """
    if not company:
        return ""
    return " ".join(str(company).split())
