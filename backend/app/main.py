from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import Listing
from app.schemas import Facets, ListingDetail, ListingPage, ListingSummary

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
