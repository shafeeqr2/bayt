"""Load REALTOR.ca listings exported from Apify into the database.

Runs on every backend start and only inserts when the table is empty, so it is
safe to run repeatedly. Drop a newer Apify export (gzipped JSON) into
`backend/seed/` and run `./start.sh reset` to reseed from scratch.
"""

import gzip
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Listing

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
SKIPPED_PROPERTY_TYPES = {"Vacant Land", "Parking"}
MIN_REAL_PRICE = 10_000  # Below this, the price is a placeholder ($1, $100, ...).
OPEN_ENDED_SQFT = 100_000  # TRREB's "5000-100000 sqft" bucket means "5000+".


def _int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _money(value: Any) -> float | None:
    match = re.search(r"[\d,]+(?:\.\d+)?", str(value or ""))
    return float(match.group().replace(",", "")) if match else None


def _bedrooms(text: str | None) -> tuple[int | None, int | None]:
    """Split TRREB-style "3 + 1" into above-grade and below-grade counts."""
    if not text:
        return None, None
    parts = [_int(p) for p in text.split("+")]
    above = parts[0]
    below = parts[1] if len(parts) > 1 else 0
    return above, below


def _sqft_range(building: dict[str, Any]) -> tuple[int | None, int | None]:
    """Parse TRREB's size bucket ("1100-1500 sqft", "5000-100000 sqft", "2047 sqft").

    Open-ended buckets lose their placeholder end: "0-499" has no minimum and
    "5000-100000" has no maximum.
    """
    measurements = building.get("FloorAreaMeasurements") or []
    text = measurements[0].get("AreaUnformatted") if measurements else None
    match = re.fullmatch(r"\s*(\d+)(?:\s*-\s*(\d+))?\s*sqft\s*", text or "")
    if not match:
        return None, None
    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) else low
    return (low or None), (high if high < OPEN_ENDED_SQFT else None)


def _updated_at(text: str | None) -> datetime | None:
    try:
        return datetime.strptime(text or "", "%Y-%m-%d %I:%M:%S %p").replace(tzinfo=UTC)
    except ValueError:
        return None


def normalize(item: dict[str, Any]) -> Listing | None:
    detail = item.get("_details") or {}
    prop = detail.get("Property") or item.get("Property") or {}
    building = detail.get("Building") or item.get("Building") or {}
    land = detail.get("Land") or item.get("Land") or {}
    address = prop.get("Address") or {}

    price = _int(prop.get("PriceUnformattedValue"))
    if price is None or price < MIN_REAL_PRICE:
        return None
    if prop.get("Type") in SKIPPED_PROPERTY_TYPES:
        return None

    address_lines = (address.get("AddressText") or "").split("|")
    above, below = _bedrooms(building.get("Bedrooms"))
    sqft_min, sqft_max = _sqft_range(building)

    return Listing(
        id=str(item["Id"]),
        mls_number=item.get("MlsNumber"),
        url=item.get("URL"),
        price=price,
        property_type=prop.get("Type"),
        building_type=building.get("Type"),
        ownership_type=prop.get("OwnershipType"),
        bedrooms_text=building.get("Bedrooms"),
        bedrooms_above=above,
        bedrooms_below=below,
        bedrooms_total=(above or 0) + (below or 0) if above is not None else None,
        bathrooms=_int(building.get("BathroomTotal")),
        sqft_min=sqft_min,
        sqft_max=sqft_max,
        stories=building.get("StoriesTotal") or None,
        lot_size=land.get("SizeTotal") or None,
        parking_spaces=_int(prop.get("ParkingSpaceTotal")),
        address=address_lines[0].title() if address_lines[0] else None,
        city=(address.get("City") or "").split(" (")[0] or None,
        community=address.get("CommunityName"),
        postal_code=item.get("PostalCode"),
        cross_streets=prop.get("LocationDescription"),
        latitude=float(address["Latitude"]) if address.get("Latitude") else None,
        longitude=float(address["Longitude"]) if address.get("Longitude") else None,
        tax_annual=_money(prop.get("TaxAmountUnformattedValue") or prop.get("TaxAmount")),
        maintenance_fee_monthly=_money(prop.get("MaintenanceFee")),
        description=detail.get("PublicRemarks"),
        photos=[
            {"high": p["HighResPath"], "medium": p["MedResPath"], "low": p["LowResPath"]}
            for p in prop.get("Photo") or []
            if p.get("HighResPath")
        ],
        rooms=[
            {"type": r.get("Type"), "level": r.get("Level"), "dimension": r.get("Dimension")}
            for r in building.get("Room") or []
        ],
        raw=item,
        source_updated_at=_updated_at(detail.get("LastUpdated")),
    )


def load_items() -> list[dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    for path in sorted(SEED_DIR.glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for item in json.load(f):
                items[str(item["Id"])] = item  # Later files win on duplicates.
    return list(items.values())


def main() -> None:
    with SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(Listing)):
            print("seed: listings already present, skipping")
            return

        listings = [listing for item in load_items() if (listing := normalize(item))]
        session.add_all(listings)
        session.commit()
        print(f"seed: inserted {len(listings)} listings")


if __name__ == "__main__":
    main()
