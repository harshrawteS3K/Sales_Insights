"""Distributor / company name normalization for stable business identity matching."""

from __future__ import annotations

import re

# Legal suffixes are removed for matching only. Stored display names stay readable.
_LEGAL_SUFFIX = re.compile(
    r"\b(?:PRIVATE\s+LIMITED|PVT\s+LTD|COMPANY|LIMITED|PRIVATE|PVT|LTD|CO)\b",
    re.IGNORECASE,
)


def normalize_distributor_name(name: str | None) -> str:
    """
    Match key used before every distributor lookup.

    Uppercase, drop punctuation, collapse spaces, then remove
    COMPANY / CO / PVT / PRIVATE LIMITED / LTD. ``S.K.TRADING``,
    ``SK Trading`` and ``S.K.TRADING COMPANY`` share one key.
    """
    if not name:
        return ""
    text = str(name).upper().replace("&", " AND ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    previous = None
    while previous != text:
        previous = text
        text = _LEGAL_SUFFIX.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"[^A-Z0-9]", "", text)


def normalize_company_name(company: str | None) -> str:
    """
    Canonicalize Distributor Company — the permanent business entity key.

    Used for get-or-create, report replacement, and uniqueness.
    """
    if not company:
        return ""
    return " ".join(str(company).split())
