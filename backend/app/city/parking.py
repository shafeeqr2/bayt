"""Parking rules from City of Toronto Zoning By-law 569-2013, Chapter 200.

By-law 89-2022 (in force since 2022) removed minimum parking requirements for
nearly every use. Table 200.5.10.1 now sets no minimum for houses, houseplexes
and secondary suites, and only maximums for resident parking in apartment
buildings, which depend on the Parking Zone overlay (A, B or neither).
Only accessible spaces, and visitor spaces in apartment buildings, still have
minimums.
"""

from dataclasses import dataclass

# Table 200.5.10.1: maximum resident spaces per dwelling unit in an apartment
# building, by unit type, for Parking Zone A, Parking Zone B and all other areas.
APARTMENT_MAX_PER_UNIT = {
    "Bachelor (up to 45 m²)": {"A": 0.3, "B": 0.7, None: 0.8},
    "Bachelor (over 45 m²)": {"A": 1.0, "B": 1.0, None: 1.0},
    "One bedroom": {"A": 0.5, "B": 0.8, None: 0.9},
    "Two bedroom": {"A": 0.8, "B": 0.9, None: 1.0},
    "Three or more bedrooms": {"A": 1.0, "B": 1.1, None: 1.2},
}

# Visitor spaces for apartment buildings: minimum is 2 plus a rate per unit.
APARTMENT_VISITOR_MIN_PER_UNIT = {"A": 0.01, "B": 0.05, None: 0.05}

# Low-rise building types that Table 200.5.10.1 lists with no minimum and no
# maximum (detached, semi-detached, townhouse and their houseplex forms).
HOUSE_TYPES = {"House", "Row / Townhouse", "Duplex", "Triplex", "Fourplex", "Multi-Family"}

PARKING_ZONE_NAMES = {
    "A": "Parking Zone A (downtown and the centres)",
    "B": "Parking Zone B (inner suburbs near transit)",
}


@dataclass(frozen=True)
class ParkingRule:
    label: str
    value: str


def parking_rules(
    zone_category: str | None,
    parking_zone: str | None,
    building_type: str | None,
    bedrooms: int | None = None,
) -> tuple[list[ParkingRule], str | None]:
    """Return the by-law's parking rules and a plain-language note for a site.

    Returns an empty list and no note for sites outside By-law 569-2013.
    """
    if not zone_category:
        return [], None

    zone = parking_zone if parking_zone in ("A", "B") else None
    rules: list[ParkingRule] = []
    if zone:
        rules.append(ParkingRule("Parking zone", PARKING_ZONE_NAMES[zone]))

    if building_type == "Apartment":
        unit_type = _unit_type(bedrooms)
        if unit_type:
            rules.append(
                ParkingRule(
                    "Minimum resident parking",
                    "None required (minimums removed in 2022)",
                )
            )
            rules.append(
                ParkingRule(
                    f"Maximum resident parking, {unit_type.lower()} unit",
                    f"{APARTMENT_MAX_PER_UNIT[unit_type][zone]:g} spaces per unit",
                )
            )
        rules.append(
            ParkingRule(
                "Minimum visitor parking",
                f"2 spaces plus {APARTMENT_VISITOR_MIN_PER_UNIT[zone]:g} per unit",
            )
        )
        note = (
            "These rates apply to new apartment buildings. "
            "An existing building keeps the parking it was built with, so check how many "
            "spaces come with this unit and whether they are owned, exclusive-use or rented."
        )
        return rules, note

    if building_type in HOUSE_TYPES:
        rules.append(ParkingRule("Required parking", "None (Toronto removed minimums in 2022)"))
        rules.append(ParkingRule("Maximum parking", "No cap for houses and houseplexes"))
        note = (
            "Adding a secondary suite, garden suite, laneway suite or extra units "
            "does not require adding parking. Only accessible spaces still have a minimum."
        )
        return rules, note

    rules.append(ParkingRule("Required parking", "None for most uses (minimums removed in 2022)"))
    return rules, "Check Chapter 200 of By-law 569-2013 for the maximum that applies to this use."


def _unit_type(bedrooms: int | None) -> str | None:
    if bedrooms is None:
        return None
    if bedrooms == 0:
        # Listings do not give the floor area reliably, so use the lower bachelor row.
        return "Bachelor (up to 45 m²)"
    if bedrooms == 1:
        return "One bedroom"
    if bedrooms == 2:
        return "Two bedroom"
    return "Three or more bedrooms"
