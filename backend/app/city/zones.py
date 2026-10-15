"""Zone categories and labels in City of Toronto Zoning By-law 569-2013."""

import re

ZONE_CATEGORIES = {
    "R": "Residential",
    "RD": "Residential Detached",
    "RS": "Residential Semi-Detached",
    "RT": "Residential Townhouse",
    "RM": "Residential Multiple Dwelling",
    "RA": "Residential Apartment",
    "RAC": "Residential Apartment Commercial",
    "CR": "Commercial Residential",
    "CRE": "Commercial Residential Employment",
    "CL": "Commercial Local",
    "E": "Employment Industrial",
    "EL": "Employment Light Industrial",
    "EH": "Employment Heavy Industrial",
    "EO": "Employment Industrial Office",
    "I": "Institutional General",
    "IH": "Institutional Hospital",
    "IE": "Institutional Education",
    "IS": "Institutional School",
    "IPW": "Institutional Place of Worship",
    "O": "Open Space",
    "ON": "Open Space Natural",
    "OR": "Open Space Recreation",
    "OC": "Open Space Civic",
    "OG": "Open Space Golf",
    "OM": "Open Space Marina",
    "UT": "Utility and Transportation",
}


def zone_label(category: str | None) -> str | None:
    return ZONE_CATEGORIES.get(category or "")


# Codes inside a 569-2013 zone label, e.g. "RD (f12.0; a370; d0.6) (x1463)".
_LABEL_CODES = [
    ("au", "Minimum lot area per unit", "m²"),
    ("f", "Minimum lot frontage", "m"),
    ("a", "Minimum lot area", "m²"),
    ("u", "Maximum dwelling units", ""),
    ("d", "Maximum floor space index (density)", "× lot area"),
    ("c", "Maximum commercial floor space index", "× lot area"),
    ("r", "Maximum residential floor space index", "× lot area"),
]
_CODE = re.compile(r"\b(au|f|a|u|d|c|r)(\d+(?:\.\d+)?)\b")
_EXCEPTION = re.compile(r"\(x(\d+)\)")
_STANDARD_SET = re.compile(r"\bSS(\d)\b")
_TOTAL_DENSITY = re.compile(r"^[A-Z]+\s+(\d+(?:\.\d+)?)\b")  # "CR 3.0 (...)"


def zone_rules(zone_string: str | None) -> list[dict[str, str]]:
    """Decode the numbers packed into a zone label into readable rules."""
    if not zone_string:
        return []
    found = dict(_CODE.findall(zone_string))
    rules = []
    if total := _TOTAL_DENSITY.match(zone_string):
        rules.append({"label": "Maximum total floor space index", "value": f"{total.group(1)} × lot area"})
    rules += [
        {"label": label, "value": f"{found[code]} {unit}".strip()}
        for code, label, unit in _LABEL_CODES
        if code in found
    ]
    if standard_set := _STANDARD_SET.search(zone_string):
        rules.append({"label": "Standard set", "value": f"SS{standard_set.group(1)}"})
    if exception := _EXCEPTION.search(zone_string):
        rules.append({"label": "Site-specific exception", "value": f"#{exception.group(1)}"})
    return rules
