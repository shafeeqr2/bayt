"""Rule resolution: the required value of each zoning standard for one parcel.

Numbers and clause ids come from the City of Toronto office consolidation of
Zoning By-law 569-2013 (https://www.toronto.ca/zoning/bylaw_amendments/), read
on 2026-10-24. Each `Required` carries the clause ids it rests on so the answer
can cite them and a reviewer can check them.

Only the low-rise residential zones (R, RD, RS, RT, RM) are resolved. Other
zones return every standard as "unknown". Site-specific exceptions are not
read; when the zone label carries one, every standard is flagged so the answer
says the exception may change the number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

Kind = Literal["min", "max"]
Status = Literal["known", "unknown", "not_applicable"]

BYLAW_URL = "https://www.toronto.ca/zoning/bylaw_amendments/ZBL_NewProvision_Chapter10_{sec}.htm"


@dataclass
class Required:
    standard: str
    label: str
    kind: Kind
    unit: str
    value: float | None
    clause_ids: list[str] = field(default_factory=list)
    status: Status = "known"
    note: str | None = None

    @property
    def source_url(self) -> str | None:
        if not self.clause_ids:
            return None
        parts = self.clause_ids[0].split(".")
        if len(parts) >= 2 and parts[0] == "10":
            return BYLAW_URL.format(sec=parts[1])
        return None


@dataclass
class ParcelFacts:
    """The inputs rule resolution needs. Built from `LotAnalysis` plus city data."""

    zone: str | None  # RD, RS, ...
    zone_label: str | None  # "RD (f12.0; a370) (x5)"
    has_site_exception: bool
    lot_frontage_m: float | None
    lot_depth_m: float | None
    lot_area_m2: float | None
    min_lot_frontage_m: float | None  # from the label (f) or the chapter default
    min_lot_area_m2: float | None  # from the label (a) or frontage x 30
    max_coverage_pct: float | None  # Lot Coverage Overlay; None = no cap
    fsi_label: float | None  # "d" value in the label; None = no FSI limit
    height_overlay_m: float | None = None  # "HT" on the Height Overlay Map, when known
    storeys_overlay: int | None = None  # "ST" on the Height Overlay Map, when known
    height_overlay_checked: bool = False  # False = we could not read the overlay, use the default
    as_of_right_units: int | None = None
    corner_lot: bool = False
    major_street: bool | None = None  # Major Streets permissions; None = not checked


LOW_RISE = ("R", "RD", "RS", "RT", "RM")

# Section number inside Chapter 10 for each zone: 10.<sec>.
SECTION = {"R": "10", "RD": "20", "RS": "40", "RT": "60", "RM": "80"}

# Default minimum lot frontage when the label has no "f" value, with its clause.
DEFAULT_FRONTAGE = {
    "R": (6.0, "10.10.30.20(1)(B)"),
    "RD": (12.0, "10.20.30.20(1)(B)"),
    "RS": (15.0, "10.40.30.20(1)(B)"),
    "RT": (6.0, "10.60.30.20(1)(B)"),
    "RM": (12.0, "10.80.30.20(1)(B)(i)"),
}

# Side yard setback by *required* minimum lot frontage. (upper bound, setback, clause letter)
SIDE_TABLE_RD = [(6.0, 0.6, "A"), (12.0, 0.9, "B"), (15.0, 1.2, "C"), (18.0, 1.5, "D"), (24.0, 1.8, "E"), (30.0, 2.4, "F"), (math.inf, 3.0, "G")]
SIDE_TABLE_RS = [(6.0, 0.6, "A"), (12.0, 0.9, "B"), (15.0, 1.2, "C"), (math.inf, 1.5, "D")]

STANDARD_LABELS = {
    "lot_frontage": ("Minimum lot frontage", "min", "m"),
    "lot_area": ("Minimum lot area", "min", "m2"),
    "lot_coverage": ("Maximum lot coverage", "max", "%"),
    "height": ("Maximum height", "max", "m"),
    "storeys": ("Maximum number of storeys", "max", "storeys"),
    "building_depth": ("Maximum building depth (rear main wall from the required front yard setback)", "max", "m"),
    "building_length": ("Maximum building length", "max", "m"),
    "fsi": ("Maximum floor space index", "max", "x lot area"),
    "front_setback": ("Minimum front yard setback", "min", "m"),
    "side_setback": ("Minimum side yard setback", "min", "m"),
    "rear_setback": ("Minimum rear yard setback", "min", "m"),
    "units": ("Maximum dwelling units as of right", "max", "units"),
}
STANDARDS = list(STANDARD_LABELS)


def _req(standard: str, value: float | None, clause_ids: list[str], status: Status = "known", note: str | None = None) -> Required:
    label, kind, unit = STANDARD_LABELS[standard]
    if value is None and status == "known":
        status = "unknown"
    return Required(standard, label, kind, unit, value, clause_ids, status, note)


def side_setback(zone: str, required_frontage: float | None, units: int | None) -> Required:
    sec = SECTION[zone]
    if zone in ("RD", "RS"):
        table = SIDE_TABLE_RD if zone == "RD" else SIDE_TABLE_RS
        if required_frontage is None:
            return _req("side_setback", None, [f"10.{sec}.40.70(3)"], note="Needs the required minimum lot frontage")
        for limit, setback, letter in table:
            if required_frontage < limit:
                return _req("side_setback", setback, [f"10.{sec}.40.70(3)({letter})"])
    if zone == "RT":
        return _req("side_setback", 0.9, ["10.60.40.70(3)(B)"], note="0.9 m for a detached house, semi-detached house or houseplex")
    if zone == "RM":
        return _req("side_setback", 1.2, ["10.80.40.70(3)(A)"], note="1.2 m for a detached house or detached houseplex; 1.5 m for a semi-detached house (B)")
    if zone == "R":
        return _req("side_setback", 0.9, ["10.10.40.70(3)(A)(i)"], note="0.9 m for a detached house, semi-detached house or houseplex")
    return _req("side_setback", None, [])


def resolve(p: ParcelFacts, *, proposed_units: int | None = None) -> list[Required]:
    """Required value of every standard for this parcel and this many units."""
    zone = p.zone
    if zone not in LOW_RISE:
        note = f"Zone {zone or 'unknown'} is outside the low-rise residential chapter; rules not resolved"
        return [_req(s, None, [], "unknown", note) for s in STANDARDS]
    sec = SECTION[zone]
    units = proposed_units or 1
    houseplex = units >= 2  # a detached/semi-detached houseplex or a building with a secondary suite
    out: list[Required] = []

    # Lot frontage and area -----------------------------------------------
    f_default, f_clause = DEFAULT_FRONTAGE[zone]
    out.append(_req("lot_frontage", p.min_lot_frontage_m if p.min_lot_frontage_m is not None else f_default, [f"10.{sec}.30.20(1)"]))
    area = p.min_lot_area_m2
    if area is None and (p.min_lot_frontage_m or f_default):
        area = (p.min_lot_frontage_m or f_default) * 30.0
    out.append(_req("lot_area", area, [f"10.{sec}.30.10(1)"]))

    # Lot coverage ----------------------------------------------------------
    if p.max_coverage_pct is None:
        out.append(_req("lot_coverage", None, [f"10.{sec}.30.40(1)(B)"], "not_applicable", "Lot is outside the Lot Coverage Overlay; no coverage cap"))
    elif houseplex and p.max_coverage_pct < 45.0:
        out.append(_req("lot_coverage", 45.0, [f"10.{sec}.30.40(1)(D)"], note=f"Overlay says {p.max_coverage_pct:g}%; a houseplex or a building with a secondary suite may cover 45%"))
    else:
        out.append(_req("lot_coverage", p.max_coverage_pct, [f"10.{sec}.30.40(1)(A)"]))

    # Height and storeys ------------------------------------------------------
    default_height = 10.0
    if zone == "RM" and not houseplex:
        default_height = 10.0  # detached and semi-detached houses; other buildings 12.0 m (10.80.40.10(1)(B)(ii))
    if p.height_overlay_checked and p.height_overlay_m is not None:
        h = max(p.height_overlay_m, default_height) if houseplex else p.height_overlay_m
        out.append(_req("height", h, [f"10.{sec}.40.10(1)(A)"] + ([f"10.{sec}.40.10(1)(C)"] if houseplex else [])))
    else:
        out.append(_req("height", default_height, [f"10.{sec}.40.10(1)(B)"], note=None if p.height_overlay_checked else "Height Overlay Map not read; 10.0 m is the default where there is no HT value"))
    st_clause = "10.60.40.10(2)" if zone == "RT" else f"10.{sec}.40.10(3)"
    if houseplex:
        out.append(_req("storeys", None, [f"{st_clause}(C)"], "not_applicable", "No storey limit for a houseplex"))
    elif p.height_overlay_checked and p.storeys_overlay is not None:
        out.append(_req("storeys", float(p.storeys_overlay), [f"{st_clause}(A)"]))
    elif p.height_overlay_checked:
        out.append(_req("storeys", None, [f"{st_clause}(B)"], "not_applicable", "No ST value on the Height Overlay Map; no storey limit"))
    else:
        out.append(_req("storeys", None, [st_clause], "unknown", "Height Overlay Map not read"))

    # Depth and length --------------------------------------------------------
    req_f = p.min_lot_frontage_m if p.min_lot_frontage_m is not None else f_default
    if zone in ("RD", "RS", "RM"):
        depth_note = None if zone != "RD" else ("Applies where the required lot frontage is 18.0 m or less" if req_f <= 18.0 else None)
        if zone == "RD" and req_f > 18.0:
            out.append(_req("building_depth", None, ["10.20.40.30(1)"], "not_applicable", "Depth limit applies only where the required frontage is 18.0 m or less"))
            out.append(_req("building_length", None, ["10.20.40.20(1)"], "not_applicable", "Length limit applies only where the required frontage is 18.0 m or less"))
        else:
            out.append(_req("building_depth", 19.0, [f"10.{sec}.40.30(1)"], note=depth_note))
            out.append(_req("building_length", 17.0, [f"10.{sec}.40.20(1)"]))
    elif zone == "R":
        out.append(_req("building_depth", 17.0, ["10.10.40.30(1)(A)"]))
        out.append(_req("building_length", None, ["10.10.40.20(1)"], "not_applicable", "R zone sets a length only for townhouses and apartments on a major street"))
    else:
        out.append(_req("building_depth", None, [], "unknown", f"No depth standard read for the {zone} zone"))
        out.append(_req("building_length", None, [], "unknown", f"No length standard read for the {zone} zone"))

    # Floor space index -------------------------------------------------------
    if houseplex:
        out.append(_req("fsi", None, [f"10.{sec}.40.40(1)(C)"], "not_applicable", "FSI does not apply to a houseplex or a building with a secondary suite"))
    elif p.fsi_label is None and zone == "R":
        out.append(_req("fsi", 0.6, ["10.10.40.40(1)(B)"], note="No d value in the zone label; the R zone default is 0.6"))
    elif p.fsi_label is None:
        out.append(_req("fsi", None, [f"10.{sec}.40.40(1)(B)"], "not_applicable", "No d value in the zone label; no FSI limit"))
    else:
        out.append(_req("fsi", p.fsi_label, [f"10.{sec}.40.40(1)(A)"]))

    # Setbacks -------------------------------------------------------------------
    out.append(_req("front_setback", 6.0, [f"10.{sec}.40.70(1)"], note="6.0 m, or the average of the neighbours where 10.5.40.70(1) applies"))
    out.append(side_setback(zone, req_f, units))
    if zone in ("RT", "R"):
        out.append(_req("rear_setback", 7.5, [f"10.{sec}.40.70(2)"]))
    elif p.lot_depth_m is None:
        out.append(_req("rear_setback", 7.5, [f"10.{sec}.40.70(2)(A)"], note="Greater of 7.5 m or 25% of lot depth; lot depth unknown so 7.5 m shown"))
    else:
        quarter = 0.25 * p.lot_depth_m
        out.append(_req("rear_setback", round(max(7.5, quarter), 2), [f"10.{sec}.40.70(2)"], note=f"Greater of 7.5 m or 25% of lot depth ({quarter:.1f} m)"))

    # Units -----------------------------------------------------------------------
    out.append(_req("units", float(p.as_of_right_units) if p.as_of_right_units else None, [f"10.{sec}.20.10"], note="Permitted-use table; 4 units as of right in Neighbourhoods since 2023, 6 where the sixplex permission applies"))

    if p.has_site_exception:
        for r in out:
            r.note = (r.note + ". " if r.note else "") + "Zone has a site-specific exception that may change this value"
    return out
