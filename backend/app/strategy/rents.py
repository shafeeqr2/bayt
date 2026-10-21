"""Market rent benchmarks used when a listing does not state its own rent.

Source: TRREB Rental Market Report, Q2 2026 (average rent of condominium
apartments and townhouses leased through the TRREB MLS System, April to June
2026). Figures are per month, by city and bedroom count. Houses are not in
the report; see `market_rent` for how they are derived.

Update this file when a newer quarterly report is out and bump
`app.strategy.estimate.MODEL_VERSION` so every listing is re-estimated.
"""

from __future__ import annotations

RENT_SOURCE = "TRREB Rental Market Report, Q2 2026"
RENT_PERIOD = "Q2 2026"

# (bachelor, one bedroom, two bedrooms, three or more bedrooms)
Rates = tuple[int, int, int, int]

APARTMENT_RENTS: dict[str, Rates] = {
    "Toronto": (1862, 2316, 3154, 3882),
    "Vaughan": (1688, 2130, 2666, 3300),
    "Markham": (1800, 2214, 2840, 3573),
    "Richmond Hill": (1850, 2310, 2910, 3711),
    "Mississauga": (1833, 2177, 2686, 3195),  # Peel Region row
    "Pickering": (1849, 1946, 2574, 2980),  # no bachelor leases in Q2; TRREB-wide bachelor used
}

# Townhouses with fewer than two bedrooms are rare (a handful of leases per
# city per quarter), so only the two and three+ bedroom averages are used and
# smaller townhouses fall back to apartment rates.
TOWNHOUSE_RENTS: dict[str, tuple[int, int]] = {
    "Toronto": (2932, 3575),
    "Vaughan": (2706, 3292),
    "Markham": (2667, 3290),
    "Richmond Hill": (2799, 3158),
    "Mississauga": (2653, 3242),  # Peel Region row
    "Pickering": (2624, 2820),
}

DEFAULT_CITY = "Toronto"

# A detached or semi-detached house rents for a little more than a townhouse
# with the same bedroom count (private yard, parking, no shared walls).
HOUSE_OVER_TOWNHOUSE = 1.10
# Each bedroom beyond the third adds this much; the report tops out at "three or more".
EXTRA_BEDROOM_RENT = 350
MAX_EXTRA_BEDROOMS = 3
# A self-contained basement apartment, by its own bedroom count (0 = bachelor).
BASEMENT_SUITE_RENT = {0: 1500, 1: 1750, 2: 2000}
# Units in an older duplex/triplex rent below condo apartments of the same size.
MULTIPLEX_UNIT_FACTOR = 0.90


def _city(city: str | None) -> str:
    return city if city in APARTMENT_RENTS else DEFAULT_CITY


def apartment_rent(city: str | None, bedrooms: int) -> int:
    rates = APARTMENT_RENTS[_city(city)]
    base = rates[min(max(bedrooms, 0), 3)]
    return base + EXTRA_BEDROOM_RENT * min(max(bedrooms - 3, 0), MAX_EXTRA_BEDROOMS)


def townhouse_rent(city: str | None, bedrooms: int) -> int:
    if bedrooms < 2:
        return apartment_rent(city, bedrooms)
    two, three = TOWNHOUSE_RENTS[_city(city)]
    base = two if bedrooms == 2 else three
    return base + EXTRA_BEDROOM_RENT * min(max(bedrooms - 3, 0), MAX_EXTRA_BEDROOMS)


def house_rent(city: str | None, bedrooms: int) -> int:
    return round(townhouse_rent(city, bedrooms) * HOUSE_OVER_TOWNHOUSE)


def basement_suite_rent(bedrooms_below: int | None) -> int:
    return BASEMENT_SUITE_RENT[min(max(bedrooms_below or 0, 0), 2)]


def multiplex_unit_rent(city: str | None, bedrooms_per_unit: int) -> int:
    return round(apartment_rent(city, bedrooms_per_unit) * MULTIPLEX_UNIT_FACTOR)
