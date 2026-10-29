from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict


class Photo(BaseModel):
    high: str
    medium: str
    low: str


class Room(BaseModel):
    type: str | None
    level: str | None
    dimension: str | None


class Potential(BaseModel):
    """One way the buyer could add value, with the evidence for it."""

    key: str  # suite | suite_potential | separate_entrance | garden_suite | severance | multiplex | extra_bedroom
    label: str
    detail: str


class InvestmentSummary(BaseModel):
    """Enough of the investment estimate to label a search result."""

    rent_monthly: int
    rent_source: str  # "listing" or "market"
    gross_yield_pct: float
    cap_rate_pct: float
    cash_flow_monthly: int  # after the mortgage, at the financing in the request
    potential: list[Potential]


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
    investment: InvestmentSummary | None = None
    # Persona -> score 1 to 10 from the house profile (`app.similar.profile`); null until the profile is written.
    persona_scores: dict[str, int] | None = None


class ListingDetail(ListingSummary):
    url: str | None
    property_type: str | None
    bedrooms_above: int | None
    bedrooms_below: int | None
    stories: str | None
    lot_size: str | None
    parking_spaces: int | None
    parking_type: str | None
    postal_code: str | None
    cross_streets: str | None
    latitude: float | None
    longitude: float | None
    tax_annual: float | None
    maintenance_fee_monthly: float | None
    description: str | None
    photos: list[Photo]
    rooms: list[Room]


class MapPin(BaseModel):
    """Just enough of a listing to draw and label it on the search map."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    price: int
    latitude: float
    longitude: float
    building_type: str | None
    bedrooms_text: str | None
    bathrooms: int | None
    address: str | None
    community: str | None
    cover_photo: str | None = None


class ListingPage(BaseModel):
    items: list[ListingSummary]
    total: int
    limit: int
    offset: int


class Facets(BaseModel):
    cities: list[str]
    building_types: list[str]


class FinancingOut(BaseModel):
    down_payment_pct: float
    down_payment: int | None
    interest_rate: float
    amortization: int


class ExpenseBreakdown(BaseModel):
    property_tax: int
    condo_fees: int
    insurance: int
    maintenance: int
    vacancy: int
    total: int
    tax_estimated: bool


class InvestmentDetail(BaseModel):
    """The full investment picture for one listing at a given financing."""

    rent_monthly: int
    rent_source: str
    rent_note: str
    units: int
    gross_annual: int
    expenses: ExpenseBreakdown
    noi_annual: int
    gross_yield_pct: float
    cap_rate_pct: float

    financing: FinancingOut
    loan: int
    mortgage_monthly: int
    cash_flow_monthly: int
    land_transfer_tax: int
    closing_costs: int
    cash_needed: int
    cash_on_cash_pct: float | None
    qualifying_rate: float
    income_to_qualify: int

    potential: list[Potential]
    assumptions: list[str]


class StrategyDefaults(BaseModel):
    financing: FinancingOut
    assumptions: list[str]
    rent_source: str
    examples: list[str]


class ParsedStrategy(BaseModel):
    params: dict[str, str | list[str]]
    understood: list[str]
    unmatched: list[str]


class Permit(BaseModel):
    permit_num: str
    revision_num: str | None
    permit_type: str | None
    structure_type: str | None
    work: str | None
    status: str | None
    application_date: date | None
    issued_date: date | None
    completed_date: date | None
    description: str | None
    current_use: str | None
    proposed_use: str | None
    dwelling_units_created: int | None
    dwelling_units_lost: int | None
    est_construction_cost: float | None


class ZoneRule(BaseModel):
    label: str
    value: str


class CityData(BaseModel):
    """What City of Toronto open data says about a listing's address and lot."""

    model_config = ConfigDict(from_attributes=True)

    match_method: str
    match_distance_m: float | None
    address_full: str | None
    former_municipality: str | None
    ward: str | None

    parcel_id: int | None
    lot_area_m2: float | None
    lot_frontage_m: float | None
    lot_depth_m: float | None
    lot_geojson: dict[str, Any] | None

    zone_category: str | None
    zone_label: str | None = None
    zone_rules: list[ZoneRule] = []
    zone_string: str | None
    zone_exception: str | None
    zoning_bylaw_section: str | None
    height_limit_m: float | None
    height_limit_storeys: int | None
    lot_coverage_pct: float | None
    parking_zone: str | None
    # What Zoning By-law 569-2013 Chapter 200 says about parking for this zone and building type.
    parking_rules: list[ZoneRule] = []
    parking_note: str | None = None
    policy_area: str | None
    rooming_house_area: str | None
    heritage_status: str | None

    permits: list[Permit] = []
