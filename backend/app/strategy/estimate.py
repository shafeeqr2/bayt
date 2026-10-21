"""Per-listing investment estimates: rent, operating costs, returns, and ways to add value.

Run with `python -m app.strategy.estimate` (done on every backend start, and
by `./start.sh lot-analysis` and `./start.sh city-data` once their data is in).
Listings whose row is missing or was computed by an older `MODEL_VERSION` are
recomputed; `--refresh` recomputes everything.

Rent comes from the listing itself when the description states what the
property earns, and from TRREB averages otherwise (`app.strategy.rents`).
Operating costs are the listing's property tax and condo fees plus allowances
set out in `EXPENSE_ASSUMPTIONS`. Value-add flags combine the listing's room
list and basement features with the lot analysis and zoning already stored
for Toronto listings.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Listing, ListingCityData, ListingInvestment, LotAnalysisCache
from app.strategy import rents

# Bump whenever rent benchmarks, assumptions or detection rules change.
MODEL_VERSION = 2

# Operating cost allowances, per year unless noted.
VACANCY_RATE = 0.04  # CMHC Toronto purpose-built vacancy was 3.5% in 2025 and rising
INSURANCE_FREEHOLD = 1500
INSURANCE_CONDO = 600  # the building is insured through the fees; this covers contents and liability
MAINTENANCE_FREEHOLD_PCT = 0.5  # of price per year, for a house the owner keeps up
MAINTENANCE_CONDO = 500  # in-suite upkeep; the reserve fund is inside the fees
DEFAULT_TAX_PCT = 0.5  # of price, when the listing omits the property tax
MIN_PLAUSIBLE_TAX = 500

EXPENSE_ASSUMPTIONS = [
    f"Vacancy allowance of {VACANCY_RATE:.0%} of rent.",
    f"Insurance of ${INSURANCE_FREEHOLD:,}/yr for freehold homes and ${INSURANCE_CONDO:,}/yr for condos.",
    f"Maintenance of {MAINTENANCE_FREEHOLD_PCT}% of the price per year for freehold homes and ${MAINTENANCE_CONDO:,}/yr for condos.",
    "Property tax and condo fees as published in the listing. Utilities are assumed paid by the tenant.",
    "No property management fee.",
]

MULTIPLEX_UNITS = {"Duplex": 2, "Triplex": 3, "Fourplex": 4}
CONDO_OWNERSHIP = {"Condominium/Strata", "Condominium", "Leasehold Condo/Strata", "Shares in Co-operative"}
# Zones where Toronto allows up to four units as-of-right since 2023 (six in sixplex wards).
MULTIPLEX_ZONES = {"R", "RD", "RS", "RT", "RM"}
MULTIPLEX_BUILDING_TYPES = {"House", "Duplex", "Triplex", "Fourplex", "Multi-Family", "Other", None}

# Rooms that can be closed in as a bedroom when they are big enough, without
# giving up the main living space (so not living, family or great rooms).
# Ontario Building Code 9.5.7: a bedroom needs at least 7 m2 (with a closet) and a window.
CONVERTIBLE_ROOMS = {
    "Den",
    "Office",
    "Study",
    "Library",
    "Loft",
    "Sitting room",
    "Solarium",
    "Sunroom",
    "Media",
    "Games room",
    "Recreational, Games room",
    "Playroom",
    "Exercise room",
}
# Condo dens are usually windowless alcoves; only rooms that have windows count there.
CONDO_CONVERTIBLE_ROOMS = {"Solarium", "Sunroom", "Office", "Library"}
MIN_BEDROOM_AREA_M2 = 7.0
MIN_BEDROOM_SIDE_M = 2.1
BASEMENT_LEVELS = {"Basement", "Lower level", "Sub-basement"}

_ROOM_DIMENSION = re.compile(r"^\s*([\d.]+)\s*m\s*x\s*([\d.]+)\s*m\s*$", re.I)

# --- Rent stated in the description ---------------------------------------------------------

_AMOUNT = r"\$\s?(?P<amount>\d[\d,]*(?:\.\d+)?)\s*(?P<k>k\b)?"
_PERIOD = r"(?P<period>\s*(?:/|per|a|each)\s*(?:month|mo\b|mth|m\b|year|yr|annum)|\s*(?:monthly|annually|per annum))?"
# "Total rental income of $5,563/month", "Total Annual Rental Income: $97,080", "$145k Gross".
_TOTAL_INCOME = re.compile(
    r"(?:total|gross|annual|current|potential|projected)\s+(?:current\s+|annual\s+|monthly\s+)?(?:rental\s+|rent\s+|gross\s+)?income"
    r"[^.$]{0,30}?" + _AMOUNT + _PERIOD,
    re.I,
)
_GROSS_AMOUNT = re.compile(_AMOUNT + _PERIOD + r"\s*(?:gross|in\s+gross\s+(?:rent|income))\b", re.I)
# "Currently rented for $2,350/month", "tenanted at $3,000", "under lease for $3500/Month", "rent is $2,350".
_WHOLE_RENT = re.compile(
    r"(?:rented(?:\s+out)?|tenanted|leased|under\s+lease|lease|rent(?:al)?|rents?\s+(?:is|at|of|for)?|collecting)"
    r"\s*(?:for|at|of|is|:)?\s*(?:approximately|approx\.?|about|around)?\s*" + _AMOUNT + _PERIOD,
    re.I,
)
_PARKING_WORDS = re.compile(r"parking|locker|storage", re.I)
# Words that mean the amount is for one part of the home, not all of it.
_PARTIAL_WORDS = re.compile(
    r"basement|bsmt|lower\s+level|lower\s+unit|upper\s+unit|upstairs|main\s+floor|main\s+level|ground\s+floor"
    r"|second\s+floor|each\s+unit|per\s+unit|one\s+of|suite|studio|apartment|apt\b|in-?law|garden\s+suite|nanny",
    re.I,
)
CONTEXT_BEFORE = 110
MIN_MONTHLY_RENT = 700
MAX_MONTHLY_RENT = 30_000
ANNUAL_IF_AT_LEAST = 15_000  # an amount with no period this large is a yearly figure


@dataclass(frozen=True)
class StatedRent:
    monthly: int
    sentence: str
    whole_property: bool  # True for a total-income figure, False for "rented at $X" of one unit


def _monthly(amount: str, k: str | None, period: str | None) -> int:
    value = float(amount.replace(",", "")) * (1000 if k else 1)
    period = (period or "").lower()
    if re.search(r"year|yr|annum|annually", period):
        value /= 12
    elif not period and value >= ANNUAL_IF_AT_LEAST:
        value /= 12
    return round(value)


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("!", 0, start), text.rfind("(", 0, start)) + 1
    right_candidates = [i for i in (text.find(".", end), text.find("!", end), text.find(")", end)) if i != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left:right].strip(" .")


def stated_rent(listing: Listing) -> StatedRent | None:
    """Rent the description says the property earns, or None when it says nothing usable."""
    text = listing.description or ""
    if not text:
        return None
    for pattern, whole in ((_TOTAL_INCOME, True), (_GROSS_AMOUNT, True), (_WHOLE_RENT, False)):
        for match in pattern.finditer(text):
            before = text[max(0, match.start() - CONTEXT_BEFORE) : match.start("amount")]
            if _PARKING_WORDS.search(before):
                continue
            if not whole and listing.building_type != "Apartment" and _PARTIAL_WORDS.search(before):
                continue
            monthly = _monthly(match.group("amount"), match.group("k"), match.group("period"))
            if not MIN_MONTHLY_RENT <= monthly <= MAX_MONTHLY_RENT:
                continue
            return StatedRent(monthly, _sentence_around(text, match.start(), match.end()), whole)
    return None


# --- Rent from market averages -------------------------------------------------------------


def _building(listing: Listing) -> dict[str, Any]:
    details = listing.raw.get("_details") or {}
    return details.get("Building") or listing.raw.get("Building") or {}


def _basement_features(listing: Listing) -> set[str]:
    raw = _building(listing).get("BasementFeatures") or ""
    return {f.strip() for f in raw.split(",") if f.strip()}


def _kitchens(listing: Listing) -> int:
    return sum(1 for room in listing.rooms if "kitchen" in (room.get("type") or "").lower())


def _basement_kitchens(listing: Listing) -> int:
    return sum(
        1
        for room in listing.rooms
        if "kitchen" in (room.get("type") or "").lower() and (room.get("level") or "") in BASEMENT_LEVELS
    )


def is_condo(listing: Listing) -> bool:
    return listing.ownership_type in CONDO_OWNERSHIP


def units(listing: Listing) -> int:
    if listing.building_type in MULTIPLEX_UNITS:
        return MULTIPLEX_UNITS[listing.building_type]
    if listing.building_type == "Multi-Family":
        return max(_kitchens(listing), 2)
    return 1


def _bedrooms_main(listing: Listing) -> int:
    if listing.bedrooms_above is not None:
        return listing.bedrooms_above
    return listing.bedrooms_total if listing.bedrooms_total is not None else 1


@dataclass(frozen=True)
class MarketRent:
    monthly: int
    note: str


def market_rent(listing: Listing, has_suite: bool) -> MarketRent:
    city = listing.city if listing.city in rents.APARTMENT_RENTS else rents.DEFAULT_CITY
    n = units(listing)
    if n > 1:
        per_unit_beds = min(max(round((listing.bedrooms_total or n) / n), 1), 3)
        per_unit = rents.multiplex_unit_rent(city, per_unit_beds)
        return MarketRent(
            per_unit * n,
            f"{n} units at about ${per_unit:,}/mo each, {rents.MULTIPLEX_UNIT_FACTOR:.0%} of the {city} "
            f"average for a {_beds_label(per_unit_beds)} condo apartment ({rents.RENT_SOURCE}).",
        )

    beds = _bedrooms_main(listing)
    kind = listing.building_type
    if kind == "Apartment":
        return MarketRent(
            rents.apartment_rent(city, beds),
            f"{city} average for a {_beds_label(beds)} condo apartment ({rents.RENT_SOURCE}).",
        )
    if kind == "Row / Townhouse":
        return MarketRent(
            rents.townhouse_rent(city, beds),
            f"{city} average for a {_beds_label(beds)} townhouse ({rents.RENT_SOURCE}).",
        )

    base = rents.house_rent(city, beds)
    note = (
        f"{city} average for a {_beds_label(beds)} townhouse plus {rents.HOUSE_OVER_TOWNHOUSE - 1:.0%} "
        f"for a house ({rents.RENT_SOURCE})."
    )
    if has_suite:
        suite = rents.basement_suite_rent(listing.bedrooms_below)
        return MarketRent(base + suite, f"{note} Plus about ${suite:,}/mo for the basement apartment.")
    return MarketRent(base, note)


def _beds_label(beds: int) -> str:
    return "bachelor" if beds <= 0 else f"{beds}-bedroom"


# --- Ways to add value -----------------------------------------------------------------------

_SUITE_WORDS = re.compile(
    r"(?:legal|registered|self[- ]contained|in-?law|basement|bsmt|lower[- ]level|nanny|secondary|second|income|rental)"
    r"\s+(?:suite|apartment|apt|unit)|basement\s+(?:is\s+)?(?:rented|tenanted|leased)|apartment\s+in\s+basement",
    re.I,
)
_SUITE_POTENTIAL_WORDS = re.compile(
    r"separate\s+entrance|potential\s+(?:for\s+)?(?:a\s+|an\s+)?(?:basement|in-?law|rental|income|second|secondary)\s+"
    r"(?:suite|apartment|apt|unit)|income\s+potential|rough(?:ed)?[- ]in\s+kitchen|kitchen\s+rough",
    re.I,
)


# A way into the basement that does not go through the main home.
_SEPARATE_ENTRANCE_WORDS = re.compile(
    r"sep[ae]rate\s+(?:side\s+|rear\s+|back\s+|basement\s+|private\s+)?entrance|private\s+entrance\s+to\s+(?:the\s+)?(?:basement|lower\s+level)",
    re.I,
)


@dataclass(frozen=True)
class SuiteCheck:
    has_suite: bool
    potential: bool
    note: str | None


def suite_check(listing: Listing) -> SuiteCheck:
    """An existing self-contained basement apartment, or the makings of one."""
    if listing.building_type == "Apartment" or units(listing) > 1:
        return SuiteCheck(False, False, None)
    features = _basement_features(listing)
    text = listing.description or ""

    if "Apartment in basement" in features:
        return SuiteCheck(True, False, "The listing records an apartment in the basement.")
    if _basement_kitchens(listing) >= 1:
        return SuiteCheck(True, False, "The room list shows a second kitchen in the basement.")
    if _SUITE_WORDS.search(text):
        return SuiteCheck(True, False, f"The description mentions a {_SUITE_WORDS.search(text).group(0).lower()}.")

    if is_condo(listing):
        return SuiteCheck(False, False, None)
    access = [f for f in ("Separate entrance", "Walk out", "Walk-up") if f in features]
    if access:
        return SuiteCheck(False, True, f"The basement has a {access[0].lower()} but no apartment yet.")
    if _SUITE_POTENTIAL_WORDS.search(text):
        return SuiteCheck(False, True, f"The description mentions {_SUITE_POTENTIAL_WORDS.search(text).group(0).lower()}.")
    basement = (_building(listing).get("BasementType") or "").lower()
    if listing.building_type == "House" and ("unfinished" in basement or "partial" in basement):
        return SuiteCheck(False, True, "The basement is unfinished, so it could be laid out as a suite.")
    return SuiteCheck(False, False, None)


def separate_entrance(listing: Listing) -> str | None:
    """Why we believe the basement has its own entrance, or None. Condos and apartments never qualify."""
    if listing.building_type == "Apartment" or is_condo(listing):
        return None
    if "Separate entrance" in _basement_features(listing):
        return "The listing records a separate entrance to the basement."
    if _SEPARATE_ENTRANCE_WORDS.search(listing.description or ""):
        return "The description mentions a separate entrance."
    return None


def convertible_room(listing: Listing) -> str | None:
    """The largest room that could be closed in as another bedroom, described for the buyer."""
    allowed = CONDO_CONVERTIBLE_ROOMS if listing.building_type == "Apartment" else CONVERTIBLE_ROOMS
    best: tuple[float, str] | None = None
    for room in listing.rooms:
        kind = room.get("type") or ""
        if kind not in allowed:
            continue
        match = _ROOM_DIMENSION.match(room.get("dimension") or "")
        if not match:
            continue
        length, width = float(match.group(1)), float(match.group(2))
        area = length * width
        if area < MIN_BEDROOM_AREA_M2 or min(length, width) < MIN_BEDROOM_SIDE_M:
            continue
        level = (room.get("level") or "").lower()
        label = f"{kind}, {length:g} m × {width:g} m" + (f", {level}" if level else "")
        if best is None or area > best[0]:
            best = (area, label)
    return best[1] if best else None


# --- Operating costs and returns ----------------------------------------------------------


@dataclass(frozen=True)
class Expenses:
    property_tax: int
    condo_fees: int
    insurance: int
    maintenance: int
    vacancy: int
    tax_estimated: bool

    @property
    def total(self) -> int:
        return self.property_tax + self.condo_fees + self.insurance + self.maintenance + self.vacancy


def expenses(listing: Listing, gross_annual: int) -> Expenses:
    condo = is_condo(listing)
    tax = listing.tax_annual if listing.tax_annual and listing.tax_annual >= MIN_PLAUSIBLE_TAX else None
    return Expenses(
        property_tax=round(tax if tax is not None else listing.price * DEFAULT_TAX_PCT / 100),
        condo_fees=round((listing.maintenance_fee_monthly or 0) * 12),
        insurance=INSURANCE_CONDO if condo else INSURANCE_FREEHOLD,
        maintenance=MAINTENANCE_CONDO if condo else round(listing.price * MAINTENANCE_FREEHOLD_PCT / 100),
        vacancy=round(gross_annual * VACANCY_RATE),
        tax_estimated=tax is None,
    )


def estimate(listing: Listing, city: ListingCityData | None, lot: dict[str, Any] | None) -> ListingInvestment:
    """A fresh (unsaved) investment row for the listing."""
    suite = suite_check(listing)
    market = market_rent(listing, suite.has_suite)
    stated = stated_rent(listing)
    low, high = (0.4, 4.0) if stated and stated.whole_property else (0.6, 3.0)
    if stated and low * market.monthly <= stated.monthly <= high * market.monthly:
        rent, source = stated.monthly, "listing"
        note = f"Stated in the listing: “{stated.sentence}”"
    else:
        rent, source, note = market.monthly, "market", market.note

    gross = rent * 12
    costs = expenses(listing, gross)
    noi = gross - costs.total

    lot = lot or {}
    zoning = lot.get("zoning") or {}
    multiplex_zone = (
        city is not None
        and city.zone_category in MULTIPLEX_ZONES
        and not is_condo(listing)
        and listing.building_type in MULTIPLEX_BUILDING_TYPES
    )
    return ListingInvestment(
        listing_id=listing.id,
        model_version=MODEL_VERSION,
        rent_monthly=rent,
        rent_source=source,
        rent_note=note,
        units=units(listing),
        gross_annual=gross,
        expenses_annual=costs.total,
        noi_annual=noi,
        gross_yield_pct=round(gross / listing.price * 100, 2),
        cap_rate_pct=round(noi / listing.price * 100, 2),
        has_suite=suite.has_suite,
        suite_potential=suite.potential,
        suite_note=suite.note,
        extra_bedroom_room=convertible_room(listing),
        separate_entrance=separate_entrance(listing),
        garden_suite=(lot.get("garden_suite") or {}).get("verdict"),
        severance=(lot.get("severance") or {}).get("verdict"),
        as_of_right_units=zoning.get("as_of_right_units") if multiplex_zone else None,
        multiplex_zone=multiplex_zone,
        computed_at=datetime.now(timezone.utc),
    )


def refresh(session: Session, listing: Listing) -> ListingInvestment:
    """Recompute and store the row for one listing (after a lot analysis, for example)."""
    city = session.get(ListingCityData, listing.id)
    cached = session.get(LotAnalysisCache, listing.id)
    row = estimate(listing, city, cached.result if cached else None)
    session.merge(row)
    session.commit()
    return row


def refresh_all(session: Session, *, only_stale: bool) -> int:
    query = select(Listing, ListingCityData, LotAnalysisCache.result).outerjoin(
        ListingCityData, ListingCityData.listing_id == Listing.id
    ).outerjoin(LotAnalysisCache, LotAnalysisCache.listing_id == Listing.id)
    if only_stale:
        query = query.outerjoin(ListingInvestment, ListingInvestment.listing_id == Listing.id).where(
            (ListingInvestment.listing_id.is_(None)) | (ListingInvestment.model_version != MODEL_VERSION)
        )
    count = 0
    for listing, city, lot in session.execute(query):
        session.merge(estimate(listing, city, lot))
        count += 1
    session.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="recompute every listing, not just missing or stale rows")
    args = parser.parse_args()
    with SessionLocal() as session:
        n = refresh_all(session, only_stale=not args.refresh)
    print(f"investment-estimates: {'recomputed' if args.refresh else 'computed'} {n} listings (model v{MODEL_VERSION})")


if __name__ == "__main__":
    main()
