"""Helpers for Excel named ranges tied to Industry Type / Segment."""

from __future__ import annotations

import re


_SAFE = re.compile(r"[^A-Za-z0-9_]")
_MULTI_UNDERSCORE = re.compile(r"_+")


def segment_range_name(segment: str) -> str:
    """
    Build a valid Excel defined-name for a segment's product list.

    Excel names: start with letter/underscore; letters, digits, underscore only.
    Prefix SEG_ to avoid collisions with built-ins and digit-leading names.
    """
    raw = (segment or "").strip()
    cleaned = _SAFE.sub("_", raw)
    cleaned = _MULTI_UNDERSCORE.sub("_", cleaned).strip("_")
    if not cleaned:
        cleaned = "UNKNOWN"
    if cleaned[0].isdigit():
        cleaned = f"N_{cleaned}"
    name = f"SEG_{cleaned}"
    return name[:200]
