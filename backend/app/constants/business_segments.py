"""Canonical business segments for persona RBAC and consolidated filters."""

BUSINESS_SEGMENTS = [
    "Paper",
    "Carpet",
    "Construction",
    "Rubber",
    "Gloves",
]

# Subject / Excel aliases that map into the five business segments
SEGMENT_ALIASES: dict[str, str] = {
    "paper": "Paper",
    "carpet": "Carpet",
    "construction": "Construction",
    "rubber": "Rubber",
    "gloves": "Gloves",
    "glove": "Gloves",
    # Rubber product families often appear in subject segment slot
    "nvc": "Rubber",
    "hsr": "Rubber",
    "nbr": "Rubber",
    "latex": "Rubber",
    "nvc latex": "Rubber",
    "rubber (nvc)": "Rubber",
    "rubber (hsr)": "Rubber",
    "rubber (nbr)": "Rubber",
    "rubber (latex)": "Rubber",
}


def normalize_business_segment(raw: str | None) -> str:
    """
    Map a free-text segment (from email subject) onto a canonical BUSINESS_SEGMENTS value.

    Returns title-cased original when no known mapping exists (still stored / displayed).
    """
    text = " ".join((raw or "").strip().split())
    if not text:
        return ""
    key = text.casefold()
    if key in SEGMENT_ALIASES:
        return SEGMENT_ALIASES[key]
    for seg in BUSINESS_SEGMENTS:
        if key == seg.casefold():
            return seg
    # "Rubber - NVC" / "Rubber NVC" style
    if key.startswith("rubber"):
        return "Rubber"
    return text.title()
