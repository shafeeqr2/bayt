"""The fact bundle: one flat dict of dotted paths that card triggers read.

Every path a card may use is declared in FACT_PATHS with a one-line meaning.
Card loading checks triggers against this list, so a typo in a card fails at
start-up, not at query time. Missing values are None; the predicate engine turns
them into "unknown" and names the path.
"""

from __future__ import annotations

from typing import Any

from app.lot.schemas import LotAnalysis
from app.zoning.gaps import GapRow
from app.zoning.intent import Intent
from app.zoning.standards import STANDARDS

GAP_FIELDS = {
    "status": "complies | short | unknown | not_applicable for the proposal",
    "delta": "Relief the proposal needs, in the standard's unit; 0 when it complies",
    "relief_pct": "delta divided by the required value",
    "required": "The required value",
    "proposed": "The proposed value",
    "existing": "The value of the building that stands today",
    "existing_status": "complies | short | unknown | not_applicable for the existing building",
}

FACT_PATHS: dict[str, str] = {
    "parcel.frontage_m": "Lot frontage as the by-law measures it",
    "parcel.depth_m": "Lot depth",
    "parcel.area_m2": "Lot area",
    "parcel.corner_lot": "True on a corner lot",
    "parcel.abuts_laneway": "True when the lot abuts a public lane",
    "parcel.irregular": "True when frontage and depth are approximate",
    "zoning.zone": "Zone category: R, RD, RS, RT, RM, ...",
    "zoning.low_rise": "True for R, RD, RS, RT, RM",
    "zoning.has_site_exception": "True when the zone label carries an (x...) exception",
    "zoning.min_lot_frontage_m": "Required minimum lot frontage",
    "zoning.min_lot_area_m2": "Required minimum lot area",
    "zoning.as_of_right_units": "Units permitted without a variance (4, or 6 with the sixplex permission)",
    "zoning.max_coverage_pct": "Lot Coverage Overlay value; None = no cap",
    "building.exists": "True when a main building stands on the lot",
    "building.footprint_m2": "Footprint of all buildings",
    "building.height_m": "LiDAR height of the main building",
    "building.front_setback_m": "Existing front yard",
    "building.side_setback_min_m": "Existing smaller side yard",
    "building.rear_setback_m": "Existing rear yard",
    "building.length_m": "Existing front wall to rear wall",
    "building.depth_m": "Existing rear wall from the required front setback",
    "coverage.coverage_pct": "Existing lot coverage",
    "severance.verdict": "likely | possible | unlikely | not_applicable | unknown",
    "severance.split_frontage_m": "Frontage of each lot after a side-by-side split",
    "garden_suite.verdict": "likely | possible | unlikely | not_applicable | unknown",
    "garden_suite.max_footprint_m2": "Largest garden suite footprint that fits",
    "heritage.listed": "True when the city heritage register lists the property",
    "intent.mode": "buyer | professional",
    "intent.project": "addition | new_build | convert | garden_suite | laneway_suite | sever | unknown",
    "intent.keep_existing_walls": "True when the main walls stay",
    "intent.sever_lot": "True when the plan divides the lot (False when not mentioned)",
    "intent.proposed_units": "Units after the work",
    "intent.proposed_storeys": "Storeys after the work",
    "intent.proposed_height_m": "Height after the work",
    "intent.proposed_gfa_m2": "Gross floor area after the work",
    "gaps.count_short": "How many standards the proposal is short on",
    "gaps.count_unknown": "How many standards could not be judged",
    "existing.count_short": "How many standards the existing building is short on",
}
for _std in STANDARDS:
    for _f, _desc in GAP_FIELDS.items():
        FACT_PATHS[f"gap.{_std}.{_f}"] = f"{_std}: {_desc}"


def build_facts(lot: LotAnalysis, intent: Intent, gaps: list[GapRow], *, heritage_listed: bool | None = None) -> dict[str, Any]:
    e = lot.envelope
    f: dict[str, Any] = {
        "parcel.frontage_m": lot.parcel.frontage_m,
        "parcel.depth_m": lot.parcel.depth_m,
        "parcel.area_m2": lot.parcel.area_m2,
        "parcel.corner_lot": lot.parcel.corner_lot,
        "parcel.abuts_laneway": lot.parcel.abuts_laneway,
        "parcel.irregular": lot.parcel.irregular,
        "zoning.zone": lot.zoning.zone,
        "zoning.low_rise": lot.zoning.low_rise_residential,
        "zoning.has_site_exception": lot.zoning.has_site_exception,
        "zoning.min_lot_frontage_m": lot.zoning.min_lot_frontage_m,
        "zoning.min_lot_area_m2": lot.zoning.min_lot_area_m2,
        "zoning.as_of_right_units": lot.zoning.as_of_right_units,
        "zoning.max_coverage_pct": lot.coverage.max_coverage_pct,
        "building.exists": e is not None,
        "building.footprint_m2": lot.coverage.building_footprint_m2,
        "building.height_m": e.height_m if e else None,
        "building.front_setback_m": e.front_setback_m if e else None,
        "building.side_setback_min_m": e.side_setback_min_m if e else None,
        "building.rear_setback_m": e.rear_setback_m if e else None,
        "building.length_m": e.building_length_m if e else None,
        "building.depth_m": e.building_depth_m if e else None,
        "coverage.coverage_pct": lot.coverage.coverage_pct,
        "severance.verdict": lot.severance.verdict,
        "severance.split_frontage_m": lot.severance.split_frontage_m,
        "garden_suite.verdict": lot.garden_suite.verdict,
        "garden_suite.max_footprint_m2": lot.garden_suite.max_footprint_m2,
        "heritage.listed": heritage_listed,
        "intent.mode": intent.mode,
        "intent.project": intent.project,
        "intent.keep_existing_walls": intent.keep_existing_walls,
        # Not mentioning a severance means no severance; "unknown" here would surface the consent card on every answer.
        "intent.sever_lot": bool(intent.sever_lot),
        "intent.proposed_units": intent.proposed_units,
        "intent.proposed_storeys": intent.proposed_storeys,
        "intent.proposed_height_m": intent.proposed_height_m,
        "intent.proposed_gfa_m2": intent.proposed_gfa_m2,
        "gaps.count_short": sum(1 for g in gaps if g.status == "short"),
        "gaps.count_unknown": sum(1 for g in gaps if g.status == "unknown"),
        "existing.count_short": sum(1 for g in gaps if g.existing_status == "short"),
    }
    for g in gaps:
        f[f"gap.{g.standard}.status"] = g.status
        f[f"gap.{g.standard}.delta"] = g.delta
        f[f"gap.{g.standard}.relief_pct"] = g.relief_pct
        f[f"gap.{g.standard}.required"] = g.required
        f[f"gap.{g.standard}.proposed"] = g.proposed
        f[f"gap.{g.standard}.existing"] = g.existing
        f[f"gap.{g.standard}.existing_status"] = g.existing_status
    unknown = set(f) - set(FACT_PATHS)
    assert not unknown, f"facts not declared in FACT_PATHS: {sorted(unknown)}"
    return f
