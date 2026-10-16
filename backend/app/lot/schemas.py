"""Response shapes for lot analysis. Everything in metres / square metres / percent."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Verdict = Literal["likely", "possible", "unlikely", "not_applicable", "unknown"]


class ParcelInfo(BaseModel):
    parcel_id: int | None
    address_number: str | None
    street: str | None
    area_m2: float
    stated_area_m2: float | None = Field(None, description="Area recorded by the city, if any")
    frontage_m: float | None = Field(
        None, description="Lot frontage as zoning measures it: width between the side lot lines 6 m back from the street"
    )
    front_lot_line_m: float | None = Field(None, description="Straight-line length of the front lot line along the street")
    depth_m: float | None
    frontage_confidence: Literal["high", "medium", "low"]
    corner_lot: bool
    abuts_laneway: bool
    irregular: bool = Field(description="True when the lot is far from rectangular, so frontage/depth are approximate")


class BuildingInfo(BaseModel):
    building_id: int | None
    kind: str = Field(description="City subtype, e.g. 'Building Outline', 'Garage'")
    footprint_m2: float
    height_m: float | None
    is_main: bool


class CoverageInfo(BaseModel):
    building_footprint_m2: float = Field(description="All structures, overlapping outlines unioned")
    main_building_m2: float
    ancillary_m2: float
    coverage_pct: float
    open_pct: float
    max_coverage_pct: float | None = Field(None, description="Zoning cap from the Lot Coverage Overlay; None = no cap")
    max_coverage_pct_with_houseplex: float | None
    remaining_buildable_footprint_m2: float | None = Field(
        None, description="How much more ground area could be built under the coverage cap"
    )


class ZoningInfo(BaseModel):
    zone_label: str | None = Field(None, description="Full label, e.g. 'RD (f15.0; a550) (x5)'")
    zone: str | None = Field(None, description="Zone category, e.g. RD, RS, R, RT, RM")
    low_rise_residential: bool
    min_lot_frontage_m: float | None
    min_lot_area_m2: float | None
    min_values_are_defaults: bool = Field(description="True when the label carries no f/a value and chapter defaults were used")
    has_site_exception: bool
    exception_link: str | None
    bylaw_link: str | None
    as_of_right_units: int | None = Field(None, description="4 across Neighbourhoods since 2023; 6 where the sixplex permission applies")


class SeveranceInfo(BaseModel):
    verdict: Verdict
    split_frontage_m: float | None = Field(None, description="Frontage of each lot after a side-by-side split")
    split_area_m2: float | None
    meets_min_frontage: bool | None
    meets_min_area: bool | None
    existing_house_fits_on_one_lot: bool | None
    nearby_lots_count: int
    nearby_median_frontage_m: float | None
    nearby_median_area_m2: float | None
    share_of_nearby_lots_at_or_below_split_frontage: float | None = Field(
        None, description="0-1; how common lots this narrow already are on the street"
    )
    notes: list[str]


class GardenSuiteInfo(BaseModel):
    verdict: Verdict
    rear_yard_depth_m: float | None
    rear_yard_area_m2: float | None
    buildable_depth_m: float | None = Field(None, description="Rear yard depth minus 5 m separation and 1.5 m rear setback")
    buildable_width_m: float | None
    max_footprint_m2: float | None = Field(None, description="Smallest of 40% of rear yard, 60 m2, the buildable box, and the 20% ancillary cap")
    max_height_m: float | None
    side_access_width_m: float | None = Field(None, description="Widest gap between the house and a side lot line; fire access needs 1.0 m")
    notes: list[str]


class BuildingProperties(BaseModel):
    building_id: int | None
    kind: str
    is_main: bool
    height_m: float | None = Field(None, description="LiDAR-derived height above ground")
    on_lot: bool = Field(description="True for footprints on this parcel (clipped to it); False for neighbours")


class BuildingFeature(BaseModel):
    """GeoJSON Feature: a footprint polygon with its height, ready to extrude."""

    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: BuildingProperties


class LotGeometry(BaseModel):
    """GeoJSON (WGS84) for drawing the lot in 2D and 3D."""

    parcel: dict[str, Any]
    buildings: list[BuildingFeature] = Field(description="Footprints on the parcel, clipped to it")
    nearby_buildings: list[BuildingFeature] = Field(description="Footprints within about 75 m, parts on the parcel removed")
    nearby_parcels: list[dict[str, Any]] = Field(description="Neighbouring parcel polygons within about 100 m")
    frontage: dict[str, Any] | None
    rear_yard: dict[str, Any] | None


class LotAnalysis(BaseModel):
    parcel: ParcelInfo
    buildings: list[BuildingInfo]
    coverage: CoverageInfo
    zoning: ZoningInfo
    severance: SeveranceInfo
    garden_suite: GardenSuiteInfo
    geometry: LotGeometry
    caveats: list[str]
    sources: list[str]
    computed_at: datetime
