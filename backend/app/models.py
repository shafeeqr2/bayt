from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Listing(Base):
    """A for-sale listing, normalized from a REALTOR.ca payload.

    `raw` keeps the full source payload so new fields can be backfilled
    with a migration instead of a re-scrape.
    """

    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    mls_number: Mapped[str | None] = mapped_column(String(32), index=True)
    url: Mapped[str | None] = mapped_column(Text)

    price: Mapped[int] = mapped_column(Integer, index=True)
    property_type: Mapped[str | None] = mapped_column(Text)
    building_type: Mapped[str | None] = mapped_column(Text, index=True)
    ownership_type: Mapped[str | None] = mapped_column(Text)

    bedrooms_text: Mapped[str | None] = mapped_column(Text)
    bedrooms_above: Mapped[int | None] = mapped_column(Integer)
    bedrooms_below: Mapped[int | None] = mapped_column(Integer)
    bedrooms_total: Mapped[int | None] = mapped_column(Integer, index=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    # TRREB publishes interior size as a range ("1100-1500 sqft"), so keep both ends.
    sqft_min: Mapped[int | None] = mapped_column(Integer)
    sqft_max: Mapped[int | None] = mapped_column(Integer)
    stories: Mapped[str | None] = mapped_column(Text)
    lot_size: Mapped[str | None] = mapped_column(Text)
    parking_spaces: Mapped[int | None] = mapped_column(Integer)
    # REALTOR.ca's comma-joined parking features, e.g. "Attached Garage, Garage" or "Underground, No Garage".
    parking_type: Mapped[str | None] = mapped_column(Text)

    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text, index=True)
    community: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    cross_streets: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    tax_annual: Mapped[float | None] = mapped_column(Float)
    maintenance_fee_monthly: Mapped[float | None] = mapped_column(Float)

    description: Mapped[str | None] = mapped_column(Text)
    photos: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    rooms: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)

    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ListingCityData(Base):
    """A listing matched to City of Toronto open data (address, lot, zoning).

    Rebuilt by `app.city.match` whenever listings or city data are reloaded.
    Building permits are not copied here; they are looked up live by
    `address_point_id`.
    """

    __tablename__ = "listing_city_data"

    listing_id: Mapped[str] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    # How the listing was tied to a city address: "address" (street number and
    # name match) or "nearest" (closest address point to the listing's pin).
    match_method: Mapped[str] = mapped_column(Text)
    match_distance_m: Mapped[float | None] = mapped_column(Float)

    address_point_id: Mapped[int | None] = mapped_column(Integer, index=True)
    address_full: Mapped[str | None] = mapped_column(Text)
    former_municipality: Mapped[str | None] = mapped_column(Text)
    ward: Mapped[str | None] = mapped_column(Text)

    parcel_id: Mapped[int | None] = mapped_column(Integer)
    lot_area_m2: Mapped[float | None] = mapped_column(Float)
    lot_frontage_m: Mapped[float | None] = mapped_column(Float)
    lot_depth_m: Mapped[float | None] = mapped_column(Float)
    lot_geojson: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    zone_category: Mapped[str | None] = mapped_column(Text)
    zone_string: Mapped[str | None] = mapped_column(Text)
    zone_exception: Mapped[str | None] = mapped_column(Text)
    zoning_bylaw_section: Mapped[str | None] = mapped_column(Text)
    height_limit_m: Mapped[float | None] = mapped_column(Float)
    height_limit_storeys: Mapped[int | None] = mapped_column(Integer)
    lot_coverage_pct: Mapped[float | None] = mapped_column(Float)
    parking_zone: Mapped[str | None] = mapped_column(Text)
    policy_area: Mapped[str | None] = mapped_column(Text)
    rooming_house_area: Mapped[str | None] = mapped_column(Text)
    heritage_status: Mapped[str | None] = mapped_column(Text)


class LotAnalysisCache(Base):
    """Cached result of `app.lot.service.analyze_listing`.

    Lot analysis takes 6-8 calls to the city's GIS, so we keep the last result
    per listing. `result` is the serialized `app.lot.schemas.LotAnalysis`.
    """

    __tablename__ = "lot_analyses"

    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    parcel_id: Mapped[int | None] = mapped_column(Integer, index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
