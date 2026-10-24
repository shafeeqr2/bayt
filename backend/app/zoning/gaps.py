"""Gap analysis: the required value of each standard against the proposal and the existing building.

One `GapRow` per standard. `status` says whether the proposal complies, is short,
is unknown (a value is missing) or has no limit. `existing_status` says the same
for the building that stands today, which is what decides whether a legal
non-conforming pathway exists.

Nothing here guesses. A proposed value comes from the intent, from the existing
building (when the intent says the walls stay) or from a simple derivation such
as floor area divided by lot area. The source is recorded on the row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.lot.schemas import LotAnalysis
from app.zoning.intent import Intent
from app.zoning.standards import STANDARDS, ParcelFacts, Required, resolve

GapStatus = Literal["complies", "short", "unknown", "not_applicable"]
Source = Literal["intent", "existing", "derived"]

TOL = 0.01


@dataclass
class GapRow:
    standard: str
    label: str
    kind: str  # min | max
    unit: str
    required: float | None
    required_status: str  # known | unknown | not_applicable
    proposed: float | None
    proposed_source: Source | None
    existing: float | None
    status: GapStatus
    existing_status: GapStatus
    delta: float | None  # relief the proposal needs; positive when short
    relief_pct: float | None  # delta / required
    clause_ids: list[str]
    source_url: str | None
    note: str | None


def parcel_facts(lot: LotAnalysis, *, height_limit_m: float | None = None, height_limit_storeys: int | None = None, overlay_checked: bool = False) -> ParcelFacts:
    z = lot.zoning
    fsi = _label_value(z.zone_label, "d")
    return ParcelFacts(
        zone=z.zone,
        zone_label=z.zone_label,
        has_site_exception=z.has_site_exception,
        lot_frontage_m=lot.parcel.frontage_m,
        lot_depth_m=lot.parcel.depth_m,
        lot_area_m2=lot.parcel.area_m2,
        min_lot_frontage_m=z.min_lot_frontage_m,
        min_lot_area_m2=z.min_lot_area_m2,
        max_coverage_pct=lot.coverage.max_coverage_pct,
        fsi_label=fsi,
        height_overlay_m=height_limit_m,
        storeys_overlay=height_limit_storeys,
        height_overlay_checked=overlay_checked,
        as_of_right_units=z.as_of_right_units,
        corner_lot=lot.parcel.corner_lot,
    )


def _label_value(label: str | None, code: str) -> float | None:
    """Read e.g. the d value out of 'RD (f12.0; a370; d0.6) (x5)'."""
    import re

    if not label:
        return None
    m = re.search(rf"\b{code}(\d+(?:\.\d+)?)\b", label)
    return float(m.group(1)) if m else None


def existing_values(lot: LotAnalysis) -> dict[str, float | None]:
    e = lot.envelope
    area = lot.parcel.area_m2
    return {
        "lot_frontage": lot.parcel.frontage_m,
        "lot_area": area,
        "lot_coverage": lot.coverage.coverage_pct if lot.buildings else None,
        "height": e.height_m if e else None,
        "storeys": None,
        "building_depth": e.building_depth_m if e else None,
        "building_length": e.building_length_m if e else None,
        "fsi": None,  # interior floor area is not in any city layer
        "front_setback": e.front_setback_m if e else None,
        "side_setback": e.side_setback_min_m if e else None,
        "rear_setback": e.rear_setback_m if e else None,
        "units": None,
    }


def proposed_values(intent: Intent, lot: LotAnalysis) -> dict[str, tuple[float | None, Source | None]]:
    """Proposed value per standard and where it came from."""
    ex = existing_values(lot)
    area = lot.parcel.area_m2 or None
    keep = intent.keep_existing_walls is True
    convert = intent.project == "convert"
    out: dict[str, tuple[float | None, Source | None]] = {}

    if intent.sever_lot:
        out["lot_frontage"] = (lot.severance.split_frontage_m, "derived")
        out["lot_area"] = (lot.severance.split_area_m2, "derived")
    else:
        out["lot_frontage"] = (ex["lot_frontage"], "existing")
        out["lot_area"] = (ex["lot_area"], "existing")

    if intent.proposed_footprint_m2 is not None and area:
        out["lot_coverage"] = (round(100.0 * intent.proposed_footprint_m2 / area, 1), "derived")
    elif convert:
        out["lot_coverage"] = (ex["lot_coverage"], "existing")
    else:
        out["lot_coverage"] = (None, None)

    out["height"] = (intent.proposed_height_m, "intent") if intent.proposed_height_m is not None else ((ex["height"], "existing") if convert else (None, None))
    out["storeys"] = (float(intent.proposed_storeys), "intent") if intent.proposed_storeys is not None else (None, None)
    out["building_depth"] = (intent.proposed_building_depth_m, "intent") if intent.proposed_building_depth_m is not None else ((ex["building_depth"], "existing") if convert else (None, None))
    out["building_length"] = (intent.proposed_building_length_m, "intent") if intent.proposed_building_length_m is not None else ((ex["building_length"], "existing") if convert else (None, None))
    out["fsi"] = (round(intent.proposed_gfa_m2 / area, 3), "derived") if intent.proposed_gfa_m2 is not None and area else (None, None)

    # Setbacks: an addition that keeps the walls is assumed to keep the front and side walls
    # where they are. The rear wall usually moves, so it needs a value.
    for key, given in (("front_setback", intent.proposed_front_setback_m), ("side_setback", intent.proposed_side_setback_m)):
        if given is not None:
            out[key] = (given, "intent")
        elif keep or convert:
            out[key] = (ex[key], "existing")
        else:
            out[key] = (None, None)
    if intent.proposed_rear_setback_m is not None:
        out["rear_setback"] = (intent.proposed_rear_setback_m, "intent")
    elif convert:
        out["rear_setback"] = (ex["rear_setback"], "existing")
    else:
        out["rear_setback"] = (None, None)

    out["units"] = (float(intent.proposed_units), "intent") if intent.proposed_units is not None else (None, None)
    return out


def _status(req: Required, value: float | None) -> tuple[GapStatus, float | None, float | None]:
    if req.status == "not_applicable":
        return "not_applicable", None, None
    if req.status == "unknown" or req.value is None or value is None:
        return "unknown", None, None
    delta = (req.value - value) if req.kind == "min" else (value - req.value)
    status: GapStatus = "short" if delta > TOL else "complies"
    relief = (delta / req.value) if (status == "short" and req.value) else (0.0 if status == "complies" else None)
    return status, round(max(delta, 0.0), 3), (round(relief, 3) if relief is not None else None)


def analyze_gaps(lot: LotAnalysis, intent: Intent, *, height_limit_m: float | None = None, height_limit_storeys: int | None = None, overlay_checked: bool = False) -> list[GapRow]:
    facts = parcel_facts(lot, height_limit_m=height_limit_m, height_limit_storeys=height_limit_storeys, overlay_checked=overlay_checked)
    required = {r.standard: r for r in resolve(facts, proposed_units=intent.proposed_units)}
    # The existing building is judged against the rules for what stands today (1 unit unless told otherwise).
    required_existing = {r.standard: r for r in resolve(facts, proposed_units=None)}
    proposed = proposed_values(intent, lot)
    existing = existing_values(lot)
    rows: list[GapRow] = []
    for std in STANDARDS:
        req = required[std]
        value, source = proposed[std]
        status, delta, relief = _status(req, value)
        ex_status, _, _ = _status(required_existing[std], existing[std])
        rows.append(
            GapRow(
                standard=std, label=req.label, kind=req.kind, unit=req.unit,
                required=req.value, required_status=req.status,
                proposed=value, proposed_source=source, existing=existing[std],
                status=status, existing_status=ex_status, delta=delta, relief_pct=relief,
                clause_ids=req.clause_ids, source_url=req.source_url, note=req.note,
            )
        )
    return rows
