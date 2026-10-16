"""Lot analysis orchestration + per-listing cache."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.lot.analysis import analyze
from app.lot.schemas import LotAnalysis
from app.lot.toronto import GISError, TorontoGIS
from app.models import Listing, LotAnalysisCache

CACHE_TTL = timedelta(days=30)  # parcel/zoning data changes slowly; building outlines refresh quarterly


class NotInCoverage(Exception):
    """The point is outside the data we can analyze (currently: City of Toronto)."""


class ListingNotLocated(Exception):
    """The listing has no coordinates."""


@lru_cache(maxsize=1)
def default_gis() -> TorontoGIS:
    return TorontoGIS()


def analyze_point(lat: float, lon: float, gis: TorontoGIS | None = None) -> LotAnalysis:
    gis = gis or default_gis()
    inputs = gis.lot_inputs(lat, lon)
    if inputs is None:
        raise NotInCoverage("No parcel found at this location (only Toronto is supported).")
    return analyze(inputs)


def analyze_listing(
    session: Session, listing: Listing, *, refresh: bool = False, gis: TorontoGIS | None = None
) -> LotAnalysis:
    if listing.latitude is None or listing.longitude is None:
        raise ListingNotLocated("Listing has no coordinates.")
    cached = session.get(LotAnalysisCache, listing.id)
    if cached and not refresh and datetime.now(timezone.utc) - cached.computed_at < CACHE_TTL:
        try:
            return LotAnalysis.model_validate(cached.result)
        except ValidationError:
            pass  # computed by an older version of the analysis; recompute below

    result = analyze_point(listing.latitude, listing.longitude, gis)
    _cross_check_listing(result, listing)
    row = cached or LotAnalysisCache(listing_id=listing.id)
    row.parcel_id = result.parcel.parcel_id
    row.result = result.model_dump(mode="json")
    row.computed_at = result.computed_at
    session.add(row)
    session.commit()
    return result


def listed_lot_area_m2(lot_size: str | None) -> float | None:
    """REALTOR.ca lot sizes look like '40 x 125 FT' or '12.19 x 38.1 M'."""
    m = re.match(r"\s*([\d.]+)\s*x\s*([\d.]+)\s*(FT|M)\b", lot_size or "", re.I)
    if not m:
        return None
    w, d = float(m.group(1)), float(m.group(2))
    factor = 0.09290304 if m.group(3).upper() == "FT" else 1.0
    return w * d * factor


def _cross_check_listing(result: LotAnalysis, listing: Listing) -> None:
    """Flag parcels that do not look like the lot the listing describes.

    Condo townhouses and some semis sit on a parcel covering several homes, and
    geocoding occasionally lands on the neighbour. The listing's own lot size is
    the cheapest sanity check we have.
    """
    listed = listed_lot_area_m2(listing.lot_size)
    if listed and abs(listed - result.parcel.area_m2) > 0.25 * listed:
        result.caveats.insert(
            0,
            f"Mapped parcel is {result.parcel.area_m2:.0f} m2 but the listing says about {listed:.0f} m2; "
            "the parcel may be shared (condo/townhouse) or mis-located, so treat these numbers with care.",
        )


__all__ = ["analyze_point", "analyze_listing", "GISError", "NotInCoverage", "ListingNotLocated"]
