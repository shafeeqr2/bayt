"""Parse listing addresses into the parts City of Toronto address points use."""

import re
from dataclasses import dataclass

# Listing street types (as REALTOR.ca spells them) -> City of Toronto LINEAR_NAME_TYPE.
STREET_TYPES = {
    "AVENUE": "Ave", "AVE": "Ave",
    "ROAD": "Rd", "RD": "Rd",
    "DRIVE": "Dr", "DR": "Dr",
    "STREET": "St", "ST": "St",
    "CRESCENT": "Cres", "CRES": "Cres",
    "BOULEVARD": "Blvd", "BLVD": "Blvd",
    "COURT": "Crt", "CRT": "Crt", "CT": "Crt",
    "TRAIL": "Trl", "TRL": "Trl",
    "SQUARE": "Sq", "SQ": "Sq",
    "PLACE": "Pl", "PL": "Pl",
    "LANE": "Lane", "LN": "Lane",
    "CIRCLE": "Crcl", "CRCL": "Crcl",
    "TERRACE": "Ter", "TER": "Ter",
    "GARDENS": "Gdns", "GDNS": "Gdns",
    "WAY": "Way",
    "GROVE": "Grv", "GRV": "Grv",
    "PARKWAY": "Pkwy", "PKWY": "Pkwy",
    "MEWS": "Mews",
    "GATE": "Gt", "GT": "Gt",
    "PATHWAY": "Ptwy", "PTWY": "Ptwy",
    "PATH": "Path",
    "HEIGHTS": "Hts", "HTS": "Hts",
    "CIRCUIT": "Crct", "CRCT": "Crct",
    "PARK": "Pk", "PK": "Pk",
    "HILL": "Hill",
    "LINE": "Line",
    "WOOD": "Wood",
    "WALK": "Walk",
    "WOODS": "Wds", "WDS": "Wds",
}

DIRECTIONS = {
    "N": "N", "NORTH": "N",
    "S": "S", "SOUTH": "S",
    "E": "E", "EAST": "E",
    "W": "W", "WEST": "W",
}

_NUMBER_AND_STREET = re.compile(r"^(\d+[A-Z]?)\s+(.+)$")
_TRAILING_UNIT = re.compile(r"\s+(?:UNIT|SUITE|APT)\s*#?\s*(\S+)\s*$", re.IGNORECASE)


def normalize_name(name: str) -> str:
    """Uppercase and drop punctuation so "St. Clair" matches "St Clair".

    Must stay in sync with the SQL expression in `app.city.match.NAME_SQL`.
    """
    return re.sub(r"\s+", " ", re.sub(r"[.']", "", name.upper())).strip()


@dataclass(frozen=True)
class ParsedAddress:
    unit: str | None
    number: str
    name: str
    street_type: str | None
    direction: str | None


def parse(address: str | None) -> ParsedAddress | None:
    """Split "610 - 1787 St. Clair Avenue W" into unit, number, name, type, direction."""
    if not address:
        return None
    unit = None
    if " - " in address:
        unit, address = (part.strip() for part in address.rsplit(" - ", 1))
    if trailing_unit := _TRAILING_UNIT.search(address):
        unit = unit or trailing_unit.group(1)
        address = address[: trailing_unit.start()]

    match = _NUMBER_AND_STREET.match(address.strip().upper())
    if not match:
        return None
    number, street = match.groups()
    tokens = normalize_name(street).split(" ")

    direction = DIRECTIONS.get(tokens[-1]) if len(tokens) > 1 else None
    if direction:
        tokens = tokens[:-1]
    street_type = STREET_TYPES.get(tokens[-1]) if len(tokens) > 1 else None
    if street_type:
        tokens = tokens[:-1]
        # Agents sometimes repeat the type ("Ridelle Ave Avenue").
        while len(tokens) > 1 and STREET_TYPES.get(tokens[-1]) == street_type:
            tokens = tokens[:-1]

    return ParsedAddress(unit, number, " ".join(tokens), street_type, direction)
