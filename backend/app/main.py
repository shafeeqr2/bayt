from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.city.permits import permits_for
from app.city.zones import zone_label, zone_rules
from app.config import settings
from app.db import get_session
from app.lot import service as lot_service
from app.lot.schemas import LotAnalysis
from app.models import Listing, ListingCityData
from app.schemas import CityData, Facets, ListingDetail, ListingPage, ListingSummary

app = FastAPI(title="Bayt API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

SessionDep = Annotated[Session, Depends(get_session)]

SORTS = {
    "newest": Listing.source_updated_at.desc().nulls_last(),
    "price_asc": Listing.price.asc(),
    "price_desc": Listing.price.desc(),
}


def _cover(listing: Listing) -> str | None:
    # "medium" is only 256px wide; the frontend resizes "high" (1600px) itself.
    return listing.photos[0]["high"] if listing.photos else None


def _summary(listing: Listing) -> ListingSummary:
    return ListingSummary.model_validate(listing, from_attributes=True).model_copy(
        update={"cover_photo": _cover(listing)}
    )


@app.get("/api/health")
def health(session: SessionDep) -> dict[str, str]:
    session.execute(text("select 1"))
    return {"status": "ok"}


@app.get("/api/listings")
def list_listings(
    session: SessionDep,
    city: str | None = None,
    building_type: str | None = None,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    min_beds: Annotated[int | None, Query(ge=0)] = None,
    min_baths: Annotated[int | None, Query(ge=0)] = None,
    q: str | None = None,
    sort: Literal["newest", "price_asc", "price_desc"] = "newest",
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ListingPage:
    filters = []
    if city:
        filters.append(Listing.city == city)
    if building_type:
        filters.append(Listing.building_type == building_type)
    if min_price is not None:
        filters.append(Listing.price >= min_price)
    if max_price is not None:
        filters.append(Listing.price <= max_price)
    if min_beds is not None:
        filters.append(Listing.bedrooms_total >= min_beds)
    if min_baths is not None:
        filters.append(Listing.bathrooms >= min_baths)
    if q:
        pattern = f"%{q}%"
        filters.append(
            Listing.address.ilike(pattern)
            | Listing.community.ilike(pattern)
            | Listing.mls_number.ilike(pattern)
        )

    total = session.scalar(select(func.count()).select_from(Listing).where(*filters)) or 0
    rows = session.scalars(
        select(Listing)
        .where(*filters)
        .order_by(SORTS[sort], Listing.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return ListingPage(
        items=[_summary(r) for r in rows], total=total, limit=limit, offset=offset
    )


@app.get("/api/listings/facets")
def facets(session: SessionDep) -> Facets:
    def distinct(column) -> list[str]:
        return list(
            session.scalars(select(column).where(column.is_not(None)).distinct().order_by(column))
        )

    return Facets(cities=distinct(Listing.city), building_types=distinct(Listing.building_type))


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: str, session: SessionDep) -> ListingDetail:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return ListingDetail.model_validate(listing, from_attributes=True).model_copy(
        update={"cover_photo": _cover(listing)}
    )


@app.get("/api/listings/{listing_id}/city")
def get_listing_city_data(listing_id: str, session: SessionDep) -> CityData:
    """Lot, zoning and permits from City of Toronto open data.

    404 when the listing is outside Toronto or city data has not been loaded.
    """
    data = session.get(ListingCityData, listing_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No City of Toronto data for this listing")
    return CityData.model_validate(data, from_attributes=True).model_copy(
        update={
            "zone_label": zone_label(data.zone_category),
            "zone_rules": zone_rules(data.zone_string),
            "permits": permits_for(session, data.address_point_id)
            if data.address_point_id
            else [],
        }
    )


def _lot_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, lot_service.NotInCoverage):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, lot_service.ListingNotLocated):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, lot_service.GISError):
        return HTTPException(status_code=502, detail=f"City of Toronto GIS unavailable: {exc}")
    raise exc


@app.get("/api/listings/{listing_id}/lot")
def get_listing_lot(listing_id: str, session: SessionDep, refresh: bool = False) -> LotAnalysis:
    """Lot coverage and infill potential for a listing (cached for 30 days)."""
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        return lot_service.analyze_listing(session, listing, refresh=refresh)
    except (lot_service.NotInCoverage, lot_service.ListingNotLocated, lot_service.GISError) as exc:
        raise _lot_errors(exc) from exc


@app.get("/api/lot")
def get_lot(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> LotAnalysis:
    """Lot coverage and infill potential for any point in Toronto (not cached)."""
    try:
        return lot_service.analyze_point(lat, lon)
    except (lot_service.NotInCoverage, lot_service.GISError) as exc:
        raise _lot_errors(exc) from exc
