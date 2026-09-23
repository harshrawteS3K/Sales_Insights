"""Subject location → distributor region, and India vs other-country grouping."""

from __future__ import annotations

import re

# Indian sales regions and states. Anything else with a location is another country.
_INDIA = {
    "india",
    "indian",
    "south",
    "north",
    "east",
    "west",
    "central",
    "north east",
    "northeast",
    "north-east",
    "south india",
    "north india",
    "east india",
    "west india",
    "central india",
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "orissa",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "delhi",
    "new delhi",
    "jammu and kashmir",
    "ladakh",
    "puducherry",
    "chandigarh",
}


def normalize_location(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def country_group(location: object) -> str:
    """``india``, ``other``, or ``""`` when location is blank."""
    text = normalize_location(location).casefold()
    if not text or text in {"—", "-"}:
        return ""
    if text in _INDIA or "india" in text:
        return "india"
    return "other"


def country_label(location: object) -> str:
    """India for domestic regions; the submitted place for other countries."""
    group = country_group(location)
    if group == "india":
        return "India"
    if group == "other":
        return normalize_location(location)
    return ""


def apply_submitted_location(distributor, location: object) -> bool:
    """Write the subject location onto the distributor. Latest non-blank value wins."""
    loc = normalize_location(location)
    if not loc:
        return False
    current = normalize_location(getattr(distributor, "region", None))
    if current == loc:
        return False
    distributor.region = loc
    return True
