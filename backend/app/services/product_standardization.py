"""Deterministic product name standardization for visualization/analytics.

Does NOT rewrite historical sales rows. Used only when grouping/filtering
products in analytics responses.

Rules are conservative:
- case / whitespace / hyphen-in-grade (N-385 → N385) are equivalent
- extra product tokens (e.g. trailing NBR) keep products distinct
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Grade token: APCOFLEX-style letter prefix + digits, optional trailing letters.
_GRADE_HYPHEN = re.compile(r"\b([A-Z]{1,12})-(\d{2,5}[A-Z]{0,6})\b")


def normalize_product_key(name: str) -> str:
    """Stable key for grouping clearly equivalent product labels."""
    text = " ".join(str(name or "").strip().split())
    if not text:
        return ""
    upper = text.upper()
    # Only collapse hyphen inside grade codes (N-385 → N385), never strip tokens.
    upper = _GRADE_HYPHEN.sub(r"\1\2", upper)
    return upper


def prefer_display_name(current: Optional[str], candidate: str) -> str:
    """Pick a stable display label among aliases (prefer Title-ish / denser)."""
    cand = " ".join(str(candidate or "").strip().split())
    if not cand:
        return current or ""
    if not current:
        return cand
    # Prefer the candidate that already looks normalized (no hyphen in grade).
    cur_key = normalize_product_key(current)
    cand_key = normalize_product_key(cand)
    if cur_key != cand_key:
        return current
    cur_hyphen = "-" in current.upper()
    cand_hyphen = "-" in cand.upper()
    if cur_hyphen and not cand_hyphen:
        return cand
    if len(cand) > len(current) and cand.isupper() == current.isupper():
        # Prefer slightly longer only when same casing style; else keep current.
        pass
    # Prefer all-caps brand style commonly used in ERP exports.
    if cand.isupper() and not current.isupper():
        return cand
    return current


def canonical_products(raw_names: Sequence[str]) -> List[str]:
    """Deduplicate raw product strings into sorted canonical display names."""
    best: Dict[str, str] = {}
    for raw in raw_names:
        name = " ".join(str(raw or "").strip().split())
        if not name:
            continue
        key = normalize_product_key(name)
        if not key:
            continue
        best[key] = prefer_display_name(best.get(key), name)
    return sorted(best.values(), key=lambda s: s.casefold())


def expand_product_filter(selected: str, all_raw: Sequence[str]) -> List[str]:
    """
    Expand a canonical (or alias) selection to every raw DB product label
    that shares the same normalized key.
    """
    selected_name = " ".join(str(selected or "").strip().split())
    if not selected_name or selected_name.lower() == "all":
        return []
    key = normalize_product_key(selected_name)
    matches = [
        " ".join(str(raw).strip().split())
        for raw in all_raw
        if raw and normalize_product_key(str(raw)) == key
    ]
    return matches or [selected_name]


def merge_product_quantities(
    rows: Sequence[Dict[str, object]],
    *,
    name_key: str = "product",
    qty_key: str = "kg",
) -> List[Dict[str, object]]:
    """Merge quantity rows that share a normalized product key."""
    buckets: Dict[str, Dict[str, object]] = {}
    order: List[str] = []
    for row in rows:
        raw = str(row.get(name_key) or "").strip()
        if not raw or raw == "Others":
            # Preserve Others as-is at the end
            key = "__others__" if raw == "Others" else ""
            if not key:
                continue
        else:
            key = normalize_product_key(raw)
        if key not in buckets:
            buckets[key] = {
                name_key: raw if key != "__others__" else "Others",
                qty_key: float(row.get(qty_key) or 0),
            }
            order.append(key)
        else:
            buckets[key][qty_key] = float(buckets[key][qty_key] or 0) + float(
                row.get(qty_key) or 0
            )
            if key != "__others__":
                buckets[key][name_key] = prefer_display_name(
                    str(buckets[key][name_key] or ""), raw
                )
    return [buckets[k] for k in order]


def product_matches_search(canonical_or_alias: str, search: str) -> bool:
    """True when search text hits the canonical key or original alias string."""
    needle = " ".join(str(search or "").strip().split()).casefold()
    if not needle:
        return True
    hay = " ".join(str(canonical_or_alias or "").strip().split())
    if needle in hay.casefold():
        return True
    return needle in normalize_product_key(hay).casefold()
