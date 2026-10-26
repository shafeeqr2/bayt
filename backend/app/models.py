from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    investment_estimate: Mapped["ListingInvestment | None"] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
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


class ListingInvestment(Base):
    """What a listing would earn as a rental and what could be added to it.

    Computed by `app.strategy.estimate` from the listing, its City of Toronto
    match and its lot analysis, so the search can filter and sort on returns
    in SQL. Rows are recomputed whenever `MODEL_VERSION` changes.
    """

    __tablename__ = "listing_investment"

    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    model_version: Mapped[int] = mapped_column(Integer)

    # Monthly rent for the whole property: "listing" when the description
    # states it, "market" when estimated from TRREB averages.
    rent_monthly: Mapped[int] = mapped_column(Integer)
    rent_source: Mapped[str] = mapped_column(Text)
    rent_note: Mapped[str] = mapped_column(Text)
    units: Mapped[int] = mapped_column(Integer)

    gross_annual: Mapped[int] = mapped_column(Integer)
    expenses_annual: Mapped[int] = mapped_column(Integer)
    noi_annual: Mapped[int] = mapped_column(Integer, index=True)
    gross_yield_pct: Mapped[float] = mapped_column(Float)
    cap_rate_pct: Mapped[float] = mapped_column(Float, index=True)

    # Ways to add value, each with a short reason shown to the buyer.
    has_suite: Mapped[bool] = mapped_column(Boolean)
    suite_potential: Mapped[bool] = mapped_column(Boolean)
    suite_note: Mapped[str | None] = mapped_column(Text)
    extra_bedroom_room: Mapped[str | None] = mapped_column(Text)
    separate_entrance: Mapped[str | None] = mapped_column(Text)  # the evidence, or None
    garden_suite: Mapped[str | None] = mapped_column(Text)  # lot analysis verdict
    severance: Mapped[str | None] = mapped_column(Text)  # lot analysis verdict
    as_of_right_units: Mapped[int | None] = mapped_column(Integer)
    multiplex_zone: Mapped[bool] = mapped_column(Boolean)

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    listing: Mapped[Listing] = relationship(back_populates="investment_estimate")


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


class ZoningAnswer(Base):
    """A model-written zoning answer for one listing and one intent (phase 2 cache).

    Keyed by `request_hash` (intent, playbook version, prompt version, model), so
    the same question costs one model call. `answer` is `app.zoning.answer.Answer`;
    null when the model gave nothing usable, with the reason in `note`.
    """

    __tablename__ = "zoning_answers"

    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    request_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[int] = mapped_column(Integer)
    intent: Mapped[dict[str, Any]] = mapped_column(JSONB)
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ListingPhoto(Base):
    """What a vision model saw in one listing photo (`app.photos.reader.PhotoFacts`).

    Keyed by the listing and the photo index. `url` and `prompt_version` say what
    was read; a changed photo or prompt reads again. `facts` is null when the model
    gave nothing usable, with the reason in `note`.
    """

    __tablename__ = "listing_photos"

    listing_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True
    )
    photo_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    prompt_version: Mapped[int] = mapped_column(Integer)
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
