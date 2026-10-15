from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, func
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
