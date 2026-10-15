from pydantic import BaseModel, ConfigDict


class Photo(BaseModel):
    high: str
    medium: str
    low: str


class Room(BaseModel):
    type: str | None
    level: str | None
    dimension: str | None


class ListingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mls_number: str | None
    price: int
    building_type: str | None
    ownership_type: str | None
    bedrooms_text: str | None
    bedrooms_total: int | None
    bathrooms: int | None
    sqft_min: int | None
    sqft_max: int | None
    address: str | None
    city: str | None
    community: str | None
    cover_photo: str | None = None


class ListingDetail(ListingSummary):
    url: str | None
    property_type: str | None
    bedrooms_above: int | None
    bedrooms_below: int | None
    stories: str | None
    lot_size: str | None
    parking_spaces: int | None
    postal_code: str | None
    cross_streets: str | None
    latitude: float | None
    longitude: float | None
    tax_annual: float | None
    maintenance_fee_monthly: float | None
    description: str | None
    photos: list[Photo]
    rooms: list[Room]


class ListingPage(BaseModel):
    items: list[ListingSummary]
    total: int
    limit: int
    offset: int


class Facets(BaseModel):
    cities: list[str]
    building_types: list[str]
