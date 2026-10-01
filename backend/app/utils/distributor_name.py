"""Distributor / company name normalization for stable business identity matching."""

from __future__ import annotations

import re

# Legal suffixes are removed for matching only. Stored display names stay readable.
_LEGAL_SUFFIX = re.compile(
    r"\b(?:PRIVATE\s+LIMITED|PVT\s+LTD|COMPANY|LIMITED|PRIVATE|PVT|LTD|CO)\b",
    re.IGNORECASE,
)

# Truncated / joined legal-form tokens, stripped only from the END of the name
# ("Reda pvt lt", "Reda Pvt.Ltd", "Reda (P) Ltd", "REDA PVTLTD").
_TRAILING_LIMITED = frozenset({"LTD", "LT", "LIMITED", "LIMITE", "LIMTED", "LMT"})
_TRAILING_PRIVATE = frozenset(
    {"PVT", "PRIVATE", "PRIV", "PVTLTD", "PVTLIMITED", "PLTD", "CO", "COMPANY"}
)


def _strip_trailing_legal_form(tokens: list[str]) -> list[str]:
    stripped_limited = False
    while len(tokens) > 1:
        last = tokens[-1]
        if last in _TRAILING_LIMITED:
            stripped_limited = True
        elif last in _TRAILING_PRIVATE or (last == "P" and stripped_limited):
            pass
        else:
            break
        tokens = tokens[:-1]
    return tokens


def normalize_distributor_name(name: str | None) -> str:
    """
    Match key used before every distributor lookup.

    Uppercase, drop punctuation, collapse spaces, then remove
    COMPANY / CO / PVT / PRIVATE LIMITED / LTD (and truncated trailing
    forms such as ``PVT LT``). ``S.K.TRADING``, ``SK Trading`` and
    ``S.K.TRADING COMPANY`` share one key; ``Reda pvt lt`` and
    ``REDA Private Ltd`` share one key.
    """
    if not name:
        return ""
    text = str(name).upper().replace("&", " AND ")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    base = text
    text = " ".join(_strip_trailing_legal_form(text.split())) if text else ""
    previous = None
    while previous != text:
        previous = text
        text = _LEGAL_SUFFIX.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
    tokens = _strip_trailing_legal_form(text.split()) if text else []
    key = re.sub(r"[^A-Z0-9]", "", "".join(tokens))
    return key or re.sub(r"[^A-Z0-9]", "", base)


def normalize_company_name(company: str | None) -> str:
    """
    Canonicalize Distributor Company — the permanent business entity key.

    Used for get-or-create, report replacement, and uniqueness.
    """
    if not company:
        return ""
    return " ".join(str(company).split())
