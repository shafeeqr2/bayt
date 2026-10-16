"""Pure lot geometry + zoning arithmetic. No I/O; see `toronto.py` for data access.

Coordinates arrive in WGS84 and are projected to EPSG:2952 (NAD83(CSRS) / MTM
zone 10, metres) for all measurements.

Zoning numbers come from Toronto Zoning By-law 569-2013:
- Chapter 10 (R, RD, RS, RT, RM zones): lot frontage/area defaults, side-yard
  table, lot coverage via the Lot Coverage Overlay.
- Chapter 150.7 (garden suites): footprint <= min(40% of rear yard, 60 m2),
  all ancillary buildings <= 20% of lot, 5.0 m separation for 4.0 m height
  (7.5 m for 6.0 m), 1.5 m rear setback, side setback max(0.6 m, 10% of
  frontage) capped at 3.0 m. Fire access needs a 1.0 m wide path from the street.
"""

from __future__ import annotations

import math
import re
import statistics
from datetime import datetime, timezone

from pyproj import Transformer
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, Point, Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, transform, unary_union

from app.lot.schemas import (
    BuildingFeature,
    BuildingInfo,
    BuildingProperties,
    CoverageInfo,
    GardenSuiteInfo,
    LotAnalysis,
    LotGeometry,
    ParcelInfo,
    SeveranceInfo,
    ZoningInfo,
)
from app.lot.toronto import LANEWAY_CODE, STREET_CODES, Feature, LotInputs

_FWD = Transformer.from_crs("EPSG:4326", "EPSG:2952", always_xy=True)
_INV = Transformer.from_crs("EPSG:2952", "EPSG:4326", always_xy=True)


def to_m(geom: BaseGeometry) -> BaseGeometry:
    return transform(_FWD.transform, geom)


def to_deg(geom: BaseGeometry) -> BaseGeometry:
    return transform(_INV.transform, geom)


# Zoning By-law 569-2013 defaults when the zone label has no "f" value.
DEFAULT_MIN_FRONTAGE = {"R": 6.0, "RD": 12.0, "RS": 15.0, "RT": 6.0, "RM": 12.0}
LOW_RISE_ZONES = set(DEFAULT_MIN_FRONTAGE)
MIN_AREA_DEPTH_FACTOR = 30.0  # min lot area = min frontage x 30 m when no "a" value

# 10.20.40.70: required side yard setback by minimum lot frontage.
SIDE_SETBACK_TABLE = [(6.0, 0.6), (12.0, 0.9), (15.0, 1.2), (18.0, 1.5), (24.0, 1.8), (30.0, 2.4), (math.inf, 3.0)]

GARDEN_SEPARATION_M = 5.0
GARDEN_SEPARATION_TALL_M = 7.5
GARDEN_REAR_SETBACK_M = 1.5
GARDEN_MAX_FOOTPRINT_M2 = 60.0
GARDEN_MAX_REAR_YARD_SHARE = 0.40
ANCILLARY_MAX_LOT_SHARE = 0.20
FIRE_ACCESS_WIDTH_M = 1.0
FIRE_TRAVEL_MAX_M = 45.0
MIN_USEFUL_SUITE_M2 = 20.0
MIN_USEFUL_SUITE_SIDE_M = 3.5

CORNER_TURN_DEG = 35.0  # boundary direction change that counts as a lot corner
NEIGHBOUR_TOUCH_M = 0.25  # tolerance when deciding a boundary edge is shared with a neighbour
SLIVER_M2 = 2.0  # building pieces smaller than this inside the parcel are eave/survey noise

SOURCES = [
    "City of Toronto Property Boundaries (municipal parcel fabric)",
    "City of Toronto Topographic Mapping - Building Outlines",
    "City of Toronto Zoning By-law 569-2013 (Zoning Area, Lot Coverage Overlay, Sixplex Permission)",
    "City of Toronto Centreline",
]


def side_setback_for_frontage(frontage: float) -> float:
    for limit, setback in SIDE_SETBACK_TABLE:
        if frontage < limit:
            return setback
    return 3.0


def parse_stated_area(text: str | None) -> float | None:
    m = re.search(r"([\d.]+)\s*sq\.?\s*m", text or "", re.I)
    return float(m.group(1)) if m else None


def _norm_street(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def _r(x: float | None, nd: int = 1) -> float | None:
    return None if x is None else round(x, nd)


# -- boundary analysis ---------------------------------------------------------


def free_boundary_pieces(parcel_m: Polygon, neighbours_m: list[BaseGeometry]) -> list[LineString]:
    """Parts of the parcel boundary not shared with a neighbouring parcel.

    What is left faces a street, lane, park or other unparcelled land. Pieces are
    split at corners so a corner lot yields one piece per street.
    """
    ring = LineString(parcel_m.exterior.coords)
    free: BaseGeometry = ring
    if neighbours_m:
        shared = unary_union([n.buffer(NEIGHBOUR_TOUCH_M) for n in neighbours_m])
        free = ring.difference(shared)
    if free.is_empty:
        return []
    merged = linemerge(free) if isinstance(free, MultiLineString) else free
    lines = list(merged.geoms) if isinstance(merged, MultiLineString) else [merged]
    pieces: list[LineString] = []
    for line in lines:
        pieces.extend(_split_at_corners(line))
    return [p for p in pieces if p.length >= 2.0]


def _split_at_corners(line: LineString) -> list[LineString]:
    coords = list(line.coords)
    if len(coords) < 3:
        return [line]
    out: list[LineString] = []
    start = 0
    heading_ref = None
    for i in range(1, len(coords) - 1):
        (x0, y0), (x1, y1), (x2, y2) = coords[i - 1], coords[i], coords[i + 1]
        if heading_ref is None:
            heading_ref = math.atan2(y1 - y0, x1 - x0)
        h = math.atan2(y2 - y1, x2 - x1)
        turn = abs((h - heading_ref + math.pi) % (2 * math.pi) - math.pi)
        if turn > math.radians(CORNER_TURN_DEG):
            seg = coords[start : i + 1]
            if len(seg) >= 2:
                out.append(LineString(seg))
            start = i
            heading_ref = h
    tail = coords[start:]
    if len(tail) >= 2:
        out.append(LineString(tail))
    return out or [line]


STREET_EDGE_MAX_M = 22.0  # a lot line running along a street sits within ~half a right-of-way of its centreline


def street_facing_edges(
    pieces: list[LineString], centrelines_m: list[tuple[BaseGeometry, dict]]
) -> dict[str, tuple[LineString, str]]:
    """Longest open boundary piece along each street the lot abuts, keyed by street name.

    A piece runs along a street when both its ends are within half a
    right-of-way of that street's centreline. Short corner-rounding pieces are
    skipped in favour of the long edge on the same street.
    """
    streets = [(g, p) for g, p in centrelines_m if p.get("FEATURE_CODE_DESC") in STREET_CODES]
    best: dict[str, tuple[LineString, str]] = {}
    for piece in pieces:
        if piece.length < 3.0 or not streets:
            continue
        a, b = Point(piece.coords[0]), Point(piece.coords[-1])
        road, props = min(streets, key=lambda gp: max(a.distance(gp[0]), b.distance(gp[0])))
        if max(a.distance(road), b.distance(road)) > STREET_EDGE_MAX_M:
            continue
        name = props.get("LINEAR_NAME_FULL") or "street"
        key = _norm_street(name)
        if key not in best or piece.length > best[key][0].length:
            best[key] = (piece, name)
    return best


def _piece_facing(pieces: list[LineString], road: BaseGeometry) -> LineString:
    """The boundary piece that runs along the road.

    A piece parallel to the road has both ends about equally close to it, while a
    side lot line has one end far away, so rank by the farther endpoint. Short
    corner-rounding pieces are ignored when a longer candidate exists.
    """
    candidates = [p for p in pieces if p.length >= 3.0] or pieces

    def score(p: LineString) -> float:
        a, b = Point(p.coords[0]), Point(p.coords[-1])
        return max(a.distance(road), b.distance(road))

    return min(candidates, key=score)


def _full_front_line(piece: LineString, parcel_m: Polygon) -> LineString:
    """Straight front lot line from lot corner to lot corner.

    `free_boundary_pieces` trims ~0.25 m where neighbours touch, so extend the
    chord and clip it back to the parcel outline.
    """
    chord = LineString([piece.coords[0], piece.coords[-1]])
    if chord.length < 0.5:
        return chord
    ext = affinity.scale(chord, 1.5, 1.5).intersection(parcel_m.buffer(0.05))
    if ext.geom_type == "MultiLineString":
        ext = max(ext.geoms, key=lambda g: g.length)
    if ext.geom_type == "LineString" and chord.length <= ext.length <= chord.length + 3.0:
        return LineString([ext.coords[0], ext.coords[-1]])
    return chord


def pick_street(parcel_m: Polygon, street_name: str | None, centrelines_m: list[tuple[BaseGeometry, dict]]):
    """The street centreline the lot fronts on: same name as the parcel's address, else nearest."""
    streets = [(g, p) for g, p in centrelines_m if p.get("FEATURE_CODE_DESC") in STREET_CODES]
    if not streets:
        return None
    want = _norm_street(street_name)
    named = [(g, p) for g, p in streets if want and _norm_street(p.get("LINEAR_NAME_FULL")) == want]
    pool = named or streets
    return min(pool, key=lambda gp: gp[0].distance(parcel_m))


# -- main entry ---------------------------------------------------------------


def analyze(inputs: LotInputs) -> LotAnalysis:
    caveats: list[str] = []
    pprops = inputs.parcel.properties
    parcel_m = to_m(inputs.parcel.geometry)
    if parcel_m.geom_type == "MultiPolygon":
        parcel_m = max(parcel_m.geoms, key=lambda g: g.area)
        caveats.append("Parcel has several parts; only the largest was analyzed.")
    lot_area = parcel_m.area
    neighbours_m = [to_m(f.geometry) for f in inputs.neighbours]
    centrelines_m = [(to_m(f.geometry), f.properties) for f in inputs.centrelines]
    street_name = pprops.get("LINEAR_NAME_FULL")

    # Frontage ---------------------------------------------------------------
    pieces = free_boundary_pieces(parcel_m, neighbours_m)
    street_edges = street_facing_edges(pieces, centrelines_m)
    corner_lot = len(street_edges) > 1
    frontage_line: LineString | None = None
    confidence = "low"
    if street_edges:
        # By-law 569-2013: on a corner lot the front lot line is the shorter street line.
        front_piece, street_name_used = min(street_edges.values(), key=lambda e: e[0].length)
        if corner_lot and street_name and _norm_street(street_name_used) != _norm_street(street_name):
            caveats.append(f"Corner lot: frontage measured on {street_name_used}, the shorter street line, although the address is on {street_name}.")
        frontage_line = _full_front_line(front_piece, parcel_m)
        confidence = "high"
        if front_piece.length > frontage_line.length * 1.15:
            caveats.append("Front lot line is curved; frontage is the straight-line width.")
            confidence = "medium"
    elif (street := pick_street(parcel_m, street_name, centrelines_m)) is not None and pieces:
        front_piece = _piece_facing(pieces, street[0])
        frontage_line = _full_front_line(front_piece, parcel_m)
        confidence = "medium"
    elif pieces:
        # No street data: take the longest free edge.
        front_piece = max(pieces, key=lambda s: s.length)
        frontage_line = _full_front_line(front_piece, parcel_m)
        caveats.append("No street centreline found; frontage assumed on the longest open edge.")
    else:
        caveats.append("Could not find an open edge of the lot; frontage estimated from the lot's bounding rectangle.")
        mrr = parcel_m.minimum_rotated_rectangle
        c = list(mrr.exterior.coords)
        sides = sorted((LineString([c[i], c[i + 1]]) for i in range(4)), key=lambda s: s.length)
        frontage_line = sides[0]

    # Lot axes: u along the front lot line, n pointing into the lot.
    (fx0, fy0), (fx1, fy1) = frontage_line.coords[0], frontage_line.coords[-1]
    flen = math.hypot(fx1 - fx0, fy1 - fy0) or 1.0
    ux, uy = (fx1 - fx0) / flen, (fy1 - fy0) / flen
    nx, ny = -uy, ux
    probe = affinity.translate(frontage_line, nx * 2, ny * 2)
    if probe.intersection(parcel_m).length < frontage_line.intersection(parcel_m.buffer(0.1)).length * 0.5:
        nx, ny = -nx, -ny

    def along(x: float, y: float) -> float:
        return (x - fx0) * ux + (y - fy0) * uy

    def depth(x: float, y: float) -> float:
        return (x - fx0) * nx + (y - fy0) * ny

    parcel_depths = [depth(x, y) for x, y in parcel_m.exterior.coords]
    lot_depth = max(parcel_depths) - min(0.0, min(parcel_depths))
    frontage = frontage_line.length

    # Zoning By-law 569-2013 measures lot frontage between the side lot lines at
    # the front yard setback (6 m in RD), not along the curb. On corner lots the
    # rounded corner makes the front lot line a few metres shorter than that.
    front_lot_line = frontage
    cut = affinity.translate(affinity.scale(frontage_line, 6, 6), nx * 6, ny * 6).intersection(parcel_m)
    if cut.geom_type == "MultiLineString":
        cut = max(cut.geoms, key=lambda g: g.length)
    width_at_setback = cut.length if not cut.is_empty else None
    if width_at_setback and width_at_setback > 1.0:
        frontage = width_at_setback
    irregular = lot_area / parcel_m.minimum_rotated_rectangle.area < 0.8 or (
        width_at_setback is not None and abs(width_at_setback - front_lot_line) > 0.2 * front_lot_line
    )
    if irregular:
        caveats.append("Lot is not rectangular; frontage and depth are approximate.")
        confidence = "medium" if confidence == "high" else confidence

    abuts_laneway = any(
        p.get("FEATURE_CODE_DESC") == LANEWAY_CODE and g.distance(parcel_m) < 4 for g, p in centrelines_m
    )

    # Buildings --------------------------------------------------------------
    building_infos: list[BuildingInfo] = []
    main_pieces: list[BaseGeometry] = []
    ancillary_pieces: list[BaseGeometry] = []
    on_lot_features: list[BuildingFeature] = []
    nearby_features: list[BuildingFeature] = []

    def building_feature(geom_m: BaseGeometry, f: Feature, *, on_lot: bool) -> BuildingFeature:
        h = f.properties.get("DERIVED_HEIGHT")
        kind = f.properties.get("SUBTYPE_DESC") or "Building"
        return BuildingFeature(
            geometry=mapping(to_deg(geom_m)),
            properties=BuildingProperties(
                building_id=f.properties.get("BUILDINGID"),
                kind=kind,
                is_main=kind == "Building Outline",
                height_m=_r(float(h)) if h not in (None, "") else None,
                on_lot=on_lot,
            ),
        )

    for f in inputs.buildings:
        geom_m = to_m(f.geometry)
        clip = geom_m.intersection(parcel_m)
        if clip.is_empty or clip.area < SLIVER_M2:
            continue
        feature = building_feature(clip, f, on_lot=True)
        (main_pieces if feature.properties.is_main else ancillary_pieces).append(clip)
        building_infos.append(
            BuildingInfo(
                building_id=feature.properties.building_id,
                kind=feature.properties.kind,
                footprint_m2=round(clip.area, 1),
                height_m=feature.properties.height_m,
                is_main=feature.properties.is_main,
            )
        )
        on_lot_features.append(feature)
        # A semi or row house straddles the lot line: the neighbour's half is context, not coverage.
        rest = geom_m.difference(parcel_m)
        if not rest.is_empty and rest.area >= SLIVER_M2:
            nearby_features.append(building_feature(rest, f, on_lot=False))
    for f in inputs.nearby_buildings:
        nearby_features.append(building_feature(to_m(f.geometry), f, on_lot=False))
    main = unary_union(main_pieces) if main_pieces else None
    ancillary = unary_union(ancillary_pieces) if ancillary_pieces else None
    footprint = unary_union([g for g in (main, ancillary) if g is not None]) if (main or ancillary) else None
    footprint_area = footprint.area if footprint else 0.0
    coverage_pct = 100.0 * footprint_area / lot_area if lot_area else 0.0
    if not building_infos:
        caveats.append("No building footprint found on this parcel; it may be vacant or recently built.")

    # Zoning -----------------------------------------------------------------
    z = inputs.zoning.properties if inputs.zoning else {}
    zone = (z.get("ZN_ZONE") or "").strip() or None
    low_rise = zone in LOW_RISE_ZONES
    zf = z.get("ZN_FRONTAGE")
    za = z.get("ZN_AREA")
    min_frontage = float(zf) if zf and zf > 0 else (DEFAULT_MIN_FRONTAGE.get(zone) if zone else None)
    min_area = float(za) if za and za > 0 else (min_frontage * MIN_AREA_DEPTH_FACTOR if min_frontage else None)
    defaults_used = low_rise and not ((zf and zf > 0) and (za and za > 0))
    cov_overlay = inputs.lot_coverage.properties.get("ZN_COVERAGE") if inputs.lot_coverage else None
    max_cov = float(cov_overlay) if cov_overlay else (float(z["ZN_COVERAGE"]) if z.get("ZN_COVERAGE") else None)
    max_cov_houseplex = 45.0 if (max_cov is not None and max_cov < 45 and low_rise) else max_cov
    remaining = max(0.0, max_cov / 100 * lot_area - footprint_area) if max_cov is not None else None
    has_exc = (z.get("ZN_EXCPTN") or "N") == "Y"
    if has_exc:
        caveats.append("Zone carries a site-specific exception; minimums and permissions may differ from the chapter rules.")
    if inputs.zoning is None:
        caveats.append("No zoning polygon found at this location.")
    units = None
    if low_rise:
        units = 6 if inputs.sixplex is not None else 4

    zoning_info = ZoningInfo(
        zone_label=z.get("ZN_STRING"),
        zone=zone,
        low_rise_residential=low_rise,
        min_lot_frontage_m=_r(min_frontage),
        min_lot_area_m2=_r(min_area),
        min_values_are_defaults=bool(defaults_used),
        has_site_exception=has_exc,
        exception_link=z.get("BYLAW_EXCPTNLINK") or None,
        bylaw_link=z.get("BYLAW_SECTIONLINK") or z.get("BYLAW_CHAPTERLINK") or None,
        as_of_right_units=units,
    )

    # House position along the lot ------------------------------------------
    house_t = house_d = None
    if main is not None:
        pts = [(x, y) for geom in getattr(main, "geoms", [main]) for x, y in geom.exterior.coords]
        ts = [along(x, y) for x, y in pts]
        ds = [depth(x, y) for x, y in pts]
        house_t = (min(ts), max(ts))
        house_d = (min(ds), max(ds))

    # Severance --------------------------------------------------------------
    severance = _severance(
        low_rise, frontage, lot_area, min_frontage, min_area, house_t, inputs, neighbours_m, street_name, confidence
    )
    if corner_lot and severance.verdict in ("unlikely", "possible"):
        severance.notes.append("Corner lot: a split with the new lot fronting the side street may also be worth checking.")

    # Garden suite -----------------------------------------------------------
    garden, rear_yard_m = _garden_suite(
        low_rise, parcel_m, lot_area, lot_depth, frontage, house_t, house_d, ancillary, abuts_laneway, nx, ny, fx0, fy0, ux, uy
    )

    stated = parse_stated_area(pprops.get("STATEDAREA"))
    if stated and abs(stated - lot_area) > 0.1 * lot_area:
        caveats.append("Mapped parcel area differs from the city's stated area by more than 10%.")

    return LotAnalysis(
        parcel=ParcelInfo(
            parcel_id=pprops.get("PARCELID"),
            address_number=pprops.get("ADDRESS_NUMBER"),
            street=street_name,
            area_m2=round(lot_area, 1),
            stated_area_m2=_r(stated),
            frontage_m=_r(frontage),
            front_lot_line_m=_r(front_lot_line),
            depth_m=_r(lot_depth),
            frontage_confidence=confidence,
            corner_lot=corner_lot,
            abuts_laneway=abuts_laneway,
            irregular=irregular,
        ),
        buildings=sorted(building_infos, key=lambda b: -b.footprint_m2),
        coverage=CoverageInfo(
            building_footprint_m2=round(footprint_area, 1),
            main_building_m2=round(main.area if main else 0.0, 1),
            ancillary_m2=round(ancillary.area if ancillary else 0.0, 1),
            coverage_pct=round(coverage_pct, 1),
            open_pct=round(100 - coverage_pct, 1),
            max_coverage_pct=max_cov,
            max_coverage_pct_with_houseplex=max_cov_houseplex,
            remaining_buildable_footprint_m2=_r(remaining),
        ),
        zoning=zoning_info,
        severance=severance,
        garden_suite=garden,
        geometry=LotGeometry(
            parcel=mapping(to_deg(parcel_m)),
            buildings=on_lot_features,
            nearby_buildings=nearby_features,
            nearby_parcels=[mapping(f.geometry) for f in inputs.neighbours],
            frontage=mapping(to_deg(frontage_line)) if frontage_line else None,
            rear_yard=mapping(to_deg(rear_yard_m)) if rear_yard_m is not None and not rear_yard_m.is_empty else None,
        ),
        caveats=caveats
        + [
            "Parcel mapping is for planning purposes and is not a survey.",
            "Zoning figures are the general chapter rules; site-specific exceptions, heritage, ravine and tree protection are not checked.",
        ],
        sources=SOURCES,
        computed_at=datetime.now(timezone.utc),
    )


def _severance(low_rise, frontage, lot_area, min_frontage, min_area, house_t, inputs, neighbours_m, street_name, confidence):
    notes: list[str] = []
    want = _norm_street(street_name)
    same_street = [
        g for g, f in zip(neighbours_m, inputs.neighbours)
        if not want or _norm_street(f.properties.get("LINEAR_NAME_FULL")) == want
    ] or neighbours_m
    nb_front: list[float] = []
    nb_area: list[float] = []
    for g in same_street:
        if g.is_empty or g.area < 50:
            continue
        mrr = g.minimum_rotated_rectangle
        c = list(mrr.exterior.coords)
        nb_front.append(min(Point(c[i]).distance(Point(c[i + 1])) for i in range(4)))
        nb_area.append(g.area)
    split_f = frontage / 2
    split_a = lot_area / 2
    share = (sum(1 for f in nb_front if f <= split_f + 0.3) / len(nb_front)) if nb_front else None

    if not low_rise:
        return SeveranceInfo(
            verdict="not_applicable", split_frontage_m=_r(split_f), split_area_m2=_r(split_a),
            meets_min_frontage=None, meets_min_area=None, existing_house_fits_on_one_lot=None,
            nearby_lots_count=len(nb_front), nearby_median_frontage_m=_median(nb_front),
            nearby_median_area_m2=_median(nb_area), share_of_nearby_lots_at_or_below_split_frontage=share,
            notes=["Severance analysis only covers low-rise residential zones (R, RD, RS, RT, RM)."],
        )
    meets_f = split_f >= min_frontage if min_frontage else None
    meets_a = split_a >= min_area if min_area else None
    fits = None
    if house_t is not None and min_frontage:
        setback = side_setback_for_frontage(split_f)
        t0, t1 = house_t
        fits = (t0 >= setback and t1 <= split_f - setback) or (t0 >= split_f + setback and t1 <= frontage - setback)
        notes.append(
            "Existing house sits within one half of the lot." if fits
            else "Existing house straddles the split line; severance would mean demolishing or rebuilding."
        )
    if meets_f and meets_a:
        verdict = "likely"
        notes.append("Each new lot meets the zone's minimum frontage and area.")
    elif (meets_f or (min_frontage and split_f >= 0.9 * min_frontage)) and (meets_a or (min_area and split_a >= 0.9 * min_area)):
        verdict = "possible"
        notes.append("Each new lot is within 10% of the zone minimums; a minor variance would be needed.")
    else:
        verdict = "unlikely"
        if min_frontage:
            notes.append(f"Each new lot would have {split_f:.1f} m frontage against a {min_frontage:.1f} m minimum.")
        if min_area:
            notes.append(f"Each new lot would be {split_a:.0f} m2 against a {min_area:.0f} m2 minimum.")
    if share is not None and verdict != "unlikely":
        if share < 0.2:
            verdict = "possible" if verdict == "likely" else verdict
            notes.append("Lots this narrow are rare on this street; the Committee of Adjustment weighs the prevailing lot pattern.")
        else:
            notes.append("Lots this narrow are already common on this street.")
    if confidence == "low":
        verdict = "unknown" if verdict == "likely" else verdict
        notes.append("Frontage could not be measured reliably.")
    return SeveranceInfo(
        verdict=verdict, split_frontage_m=_r(split_f), split_area_m2=_r(split_a),
        meets_min_frontage=meets_f, meets_min_area=meets_a, existing_house_fits_on_one_lot=fits,
        nearby_lots_count=len(nb_front), nearby_median_frontage_m=_median(nb_front),
        nearby_median_area_m2=_median(nb_area), share_of_nearby_lots_at_or_below_split_frontage=_r(share, 2),
        notes=notes,
    )


def _garden_suite(low_rise, parcel_m, lot_area, lot_depth, frontage, house_t, house_d, ancillary, abuts_laneway, nx, ny, fx0, fy0, ux, uy):
    notes: list[str] = []
    empty = GardenSuiteInfo(
        verdict="not_applicable", rear_yard_depth_m=None, rear_yard_area_m2=None, buildable_depth_m=None,
        buildable_width_m=None, max_footprint_m2=None, max_height_m=None, side_access_width_m=None, notes=notes,
    )
    if not low_rise:
        notes.append("Garden suites are permitted in R, RD, RS, RT and RM zones only.")
        return empty, None
    if house_d is None:
        notes.append("No main building found, so there is no rear yard to measure; the lot may be vacant.")
        return empty, None

    rear_wall = house_d[1]
    rear_depth = lot_depth - rear_wall
    # Rear yard = parcel beyond the rear main wall (half-plane in lot coordinates).
    big = 10_000.0
    px, py = fx0 + nx * rear_wall, fy0 + ny * rear_wall
    half_plane = Polygon([
        (px + ux * big, py + uy * big), (px - ux * big, py - uy * big),
        (px - ux * big + nx * big, py - uy * big + ny * big), (px + ux * big + nx * big, py + uy * big + ny * big),
    ])
    rear_yard = parcel_m.intersection(half_plane)
    rear_area = rear_yard.area
    side_setback = min(3.0, max(0.6, 0.1 * frontage))
    mid = rear_wall + rear_depth / 2
    cutline = LineString([(fx0 - ux * big, fy0 - uy * big), (fx0 + ux * big, fy0 + uy * big)])
    rear_width = affinity.translate(cutline, nx * mid, ny * mid).intersection(parcel_m).length
    buildable_depth = rear_depth - GARDEN_SEPARATION_M - GARDEN_REAR_SETBACK_M
    buildable_width = rear_width - 2 * side_setback
    existing_anc = ancillary.area if ancillary is not None else 0.0
    anc_room = ANCILLARY_MAX_LOT_SHARE * lot_area - existing_anc
    footprint = min(
        GARDEN_MAX_REAR_YARD_SHARE * rear_area,
        GARDEN_MAX_FOOTPRINT_M2,
        max(0.0, buildable_depth) * max(0.0, buildable_width),
        max(0.0, anc_room),
    )
    access = max(0.0, house_t[0], frontage - house_t[1]) if house_t else None
    tall_ok = rear_depth - GARDEN_SEPARATION_TALL_M - GARDEN_REAR_SETBACK_M >= MIN_USEFUL_SUITE_SIDE_M
    max_height = 6.0 if tall_ok else 4.0

    if abuts_laneway:
        notes.append("Lot abuts a laneway, so laneway-suite rules (Chapter 150.8) apply instead of garden-suite rules.")
    if existing_anc > 0:
        notes.append(f"Existing garage/shed covers {existing_anc:.0f} m2 of the rear; it counts toward the 20% ancillary cap and could be replaced.")
    if access is not None and access < FIRE_ACCESS_WIDTH_M:
        notes.append(f"Widest side path is {access:.1f} m; fire access needs 1.0 m clear from the street.")
    if rear_wall + GARDEN_SEPARATION_M > FIRE_TRAVEL_MAX_M:
        notes.append("Suite entrance would be more than 45 m from the street (Building Code travel limit).")

    if footprint >= MIN_USEFUL_SUITE_M2 and buildable_depth >= MIN_USEFUL_SUITE_SIDE_M and buildable_width >= MIN_USEFUL_SUITE_SIDE_M:
        verdict = "likely" if (access is None or access >= FIRE_ACCESS_WIDTH_M) and not abuts_laneway else "possible"
        notes.insert(0, f"Room for roughly a {footprint:.0f} m2 footprint up to {max_height:.0f} m tall.")
    elif footprint > 0 and buildable_depth > 0:
        verdict = "unlikely"
        notes.insert(0, f"Only about {footprint:.0f} m2 fits after setbacks and separation; too small for a useful suite.")
    else:
        verdict = "unlikely"
        notes.insert(0, "Rear yard is too shallow once the 5 m separation and 1.5 m rear setback are applied.")

    return GardenSuiteInfo(
        verdict=verdict,
        rear_yard_depth_m=_r(rear_depth),
        rear_yard_area_m2=_r(rear_area),
        buildable_depth_m=_r(buildable_depth),
        buildable_width_m=_r(buildable_width),
        max_footprint_m2=_r(footprint),
        max_height_m=max_height,
        side_access_width_m=_r(access),
        notes=notes,
    ), rear_yard
