"""Unit tests for lot analysis on synthetic geometry (no network, no database).

A toy block in Toronto: a straight east-west street with lots on its north side.
Lots are built in metres (EPSG:2952) and converted to WGS84, the way the GIS
client would deliver them.
"""

import math

import pytest
from shapely.geometry import LineString, Polygon, box

from app.lot import analysis
from app.lot.analysis import analyze, free_boundary_pieces, side_setback_for_frontage, to_deg
from app.lot.toronto import Feature, LotInputs

# Somewhere in central Toronto, in MTM zone 10 metres.
X0, Y0 = 313_000.0, 4_836_000.0


def lot(x: float, width: float, depth: float = 40.0) -> Polygon:
    """Rectangular lot whose front lot line is on y=Y0 (street to the south)."""
    return box(X0 + x, Y0, X0 + x + width, Y0 + depth)


def feature(geom, **props) -> Feature:
    return Feature(to_deg(geom), props)


def street(name="Test St", y=Y0 - 10.0, kind="Local") -> Feature:
    return feature(LineString([(X0 - 200, y), (X0 + 400, y)]), LINEAR_NAME_FULL=name, FEATURE_CODE_DESC=kind)


def house(x: float, width: float, depth: float, setback: float = 6.0, kind="Building Outline", **props) -> Feature:
    return feature(box(X0 + x, Y0 + setback, X0 + x + width, Y0 + setback + depth), SUBTYPE_DESC=kind, **props)


def zoning(zone="RD", frontage=12.0, area=370, coverage=None, **extra) -> Feature:
    props = dict(ZN_ZONE=zone, ZN_FRONTAGE=frontage, ZN_AREA=area, ZN_STRING=f"{zone} (f{frontage}; a{area})", ZN_EXCPTN="N")
    props.update(extra)
    return feature(box(X0 - 500, Y0 - 500, X0 + 500, Y0 + 500), **props)


def coverage_overlay(pct: float) -> Feature:
    return feature(box(X0 - 500, Y0 - 500, X0 + 500, Y0 + 500), ZN_COVERAGE=pct)


def block(widths: list[float], target: int, depth: float = 40.0) -> tuple[Feature, list[Feature]]:
    """Row of lots; returns (target parcel, neighbours)."""
    xs = [sum(widths[:i]) for i in range(len(widths))]
    parcels = [
        feature(lot(x, w, depth), PARCELID=i, FEATURE_TYPE="COMMON", ADDRESS_NUMBER=str(10 + 2 * i), LINEAR_NAME_FULL="Test St")
        for i, (x, w) in enumerate(zip(xs, widths))
    ]
    return parcels[target], [p for i, p in enumerate(parcels) if i != target]


def inputs(parcel, neighbours, buildings, zoning_f=None, cov=None, streets=None, sixplex=None) -> LotInputs:
    return LotInputs(
        parcel=parcel,
        neighbours=neighbours,
        buildings=buildings,
        zoning=zoning_f,
        lot_coverage=cov,
        centrelines=streets if streets is not None else [street()],
        sixplex=sixplex,
    )


def test_typical_toronto_lot_coverage_and_frontage():
    parcel, nbs = block([12.0] * 7, target=3)
    # 7.5 m wide, 12 m deep house, 2.25 m from each side; plus a 3x6 garage at the back.
    bld = [house(36 + 2.25, 7.5, 12.0, BUILDINGID=1, DERIVED_HEIGHT=7.2), house(36 + 8, 3.0, 6.0, setback=32, kind="Garage", BUILDINGID=2)]
    r = analyze(inputs(parcel, nbs, bld, zoning(), coverage_overlay(35)))

    assert r.parcel.frontage_m == pytest.approx(12.0, abs=0.1)
    assert r.parcel.front_lot_line_m == pytest.approx(12.0, abs=0.1)
    assert r.parcel.depth_m == pytest.approx(40.0, abs=0.1)
    assert r.parcel.area_m2 == pytest.approx(480.0, abs=1)
    assert r.parcel.frontage_confidence == "high"
    assert not r.parcel.corner_lot and not r.parcel.irregular and not r.parcel.abuts_laneway

    assert r.coverage.main_building_m2 == pytest.approx(90.0, abs=0.5)
    assert r.coverage.ancillary_m2 == pytest.approx(18.0, abs=0.5)
    assert r.coverage.coverage_pct == pytest.approx(108 / 480 * 100, abs=0.2)
    assert r.coverage.open_pct == pytest.approx(100 - 108 / 480 * 100, abs=0.2)
    assert r.coverage.max_coverage_pct == 35
    assert r.coverage.max_coverage_pct_with_houseplex == 45
    assert r.coverage.remaining_buildable_footprint_m2 == pytest.approx(0.35 * 480 - 108, abs=0.5)
    assert [b.kind for b in r.buildings] == ["Building Outline", "Garage"]

    assert r.zoning.zone == "RD" and r.zoning.low_rise_residential
    assert r.zoning.min_lot_frontage_m == 12.0 and r.zoning.min_lot_area_m2 == 370
    assert r.zoning.as_of_right_units == 4

    # 12 m lot cannot be split into two 12 m lots.
    assert r.severance.verdict == "unlikely"
    assert r.severance.split_frontage_m == pytest.approx(6.0, abs=0.1)
    assert r.severance.meets_min_frontage is False
    assert r.severance.nearby_lots_count == 6
    assert r.severance.nearby_median_frontage_m == pytest.approx(12.0, abs=0.1)

    # Rear yard: 40 - (6 + 12) = 22 m deep -> a 60 m2 suite fits.
    g = r.garden_suite
    assert g.verdict == "likely"
    assert g.rear_yard_depth_m == pytest.approx(22.0, abs=0.1)
    assert g.rear_yard_area_m2 == pytest.approx(22 * 12, abs=1)
    assert g.buildable_depth_m == pytest.approx(22 - 5 - 1.5, abs=0.1)
    assert g.max_footprint_m2 == 60.0
    assert g.max_height_m == 6.0
    assert g.side_access_width_m == pytest.approx(2.25, abs=0.1)
    assert r.geometry.frontage is not None and r.geometry.rear_yard is not None


def test_wide_lot_can_be_severed_and_house_fits_on_one_half():
    parcel, nbs = block([15.0, 15.0, 30.0, 15.0, 15.0], target=2)
    bld = [house(30 + 1.5, 9.0, 12.0, BUILDINGID=1)]  # house on the west half
    r = analyze(inputs(parcel, nbs, bld, zoning("RD", 12.0, 370), coverage_overlay(35)))
    s = r.severance
    assert s.split_frontage_m == pytest.approx(15.0, abs=0.1)
    assert s.split_area_m2 == pytest.approx(600, abs=2)
    assert s.meets_min_frontage and s.meets_min_area
    assert s.existing_house_fits_on_one_lot is True
    assert s.verdict == "likely"
    # neighbours are all 15 m, so a 15 m split is in keeping with the street
    assert s.share_of_nearby_lots_at_or_below_split_frontage == pytest.approx(1.0)


def test_split_within_ten_percent_is_possible_with_variance():
    parcel, nbs = block([11.0, 11.0, 22.0, 11.0, 11.0], target=2)
    r = analyze(inputs(parcel, nbs, [house(22 + 7, 8.0, 12.0)], zoning("RD", 12.0, 370)))
    assert r.severance.verdict == "possible"
    assert r.severance.meets_min_frontage is False
    assert r.severance.existing_house_fits_on_one_lot is False


def test_shallow_rear_yard_blocks_garden_suite():
    parcel, nbs = block([12.0] * 3, target=1, depth=30.0)
    r = analyze(inputs(parcel, nbs, [house(12 + 2, 8.0, 15.0)], zoning()))
    g = r.garden_suite
    assert g.rear_yard_depth_m == pytest.approx(9.0, abs=0.1)
    assert g.buildable_depth_m == pytest.approx(2.5, abs=0.1)
    assert g.verdict == "unlikely"


def test_semi_detached_without_side_path_is_only_possible():
    parcel, nbs = block([6.0] * 5, target=2)
    # house flush against the west lot line (shared wall), 0.6 m on the east
    r = analyze(inputs(parcel, nbs, [house(12.0, 5.4, 12.0)], zoning("RS", 15.0, 450)))
    g = r.garden_suite
    assert g.side_access_width_m == pytest.approx(0.6, abs=0.1)
    assert g.verdict == "possible"
    assert any("fire access" in n.lower() for n in g.notes)


def test_zone_defaults_when_label_has_no_values():
    parcel, nbs = block([12.0] * 3, target=1)
    r = analyze(inputs(parcel, nbs, [house(14, 8, 12)], zoning("RS", -1, -1)))
    assert r.zoning.min_lot_frontage_m == 15.0
    assert r.zoning.min_lot_area_m2 == 450.0
    assert r.zoning.min_values_are_defaults is True


def test_non_residential_zone_is_not_applicable():
    parcel, nbs = block([12.0] * 3, target=1)
    r = analyze(inputs(parcel, nbs, [house(14, 8, 12)], zoning("CR", -1, -1)))
    assert r.zoning.low_rise_residential is False
    assert r.severance.verdict == "not_applicable"
    assert r.garden_suite.verdict == "not_applicable"
    assert r.zoning.as_of_right_units is None
    assert r.coverage.coverage_pct > 0  # coverage is still reported


def test_sixplex_permission_and_laneway():
    parcel, nbs = block([12.0] * 3, target=1)
    lane = street("Lane", y=Y0 + 42.0, kind="Laneway")
    r = analyze(inputs(parcel, nbs, [house(14, 8, 12)], zoning("R", 6.0, 180), streets=[street(), lane], sixplex=feature(box(X0 - 50, Y0 - 50, X0 + 50, Y0 + 50))))
    assert r.zoning.as_of_right_units == 6
    assert r.parcel.abuts_laneway is True
    assert r.garden_suite.verdict == "possible"
    assert any("laneway" in n.lower() for n in r.garden_suite.notes)


def test_overlapping_outlines_are_unioned_and_slivers_dropped():
    parcel, nbs = block([12.0] * 3, target=1)
    # Two identical outlines (the city's data has stacked roof segments) + a neighbour's eave crossing the line.
    same = house(14, 8, 12, BUILDINGID=1)
    dup = house(14, 8, 12, BUILDINGID=1)
    eave = feature(box(X0 + 11.9, Y0 + 6, X0 + 12.05, Y0 + 18), SUBTYPE_DESC="Building Outline", BUILDINGID=9)
    r = analyze(inputs(parcel, nbs, [same, dup, eave], zoning()))
    assert r.coverage.building_footprint_m2 == pytest.approx(96.0, abs=0.5)
    assert len(r.buildings) == 2  # sliver dropped, duplicate still listed


def test_corner_lot_uses_shorter_street_line():
    # Lot at the end of the row: open to the south (Test St, 15 m) and the east (Side St, 40 m).
    parcel, nbs = block([12.0, 12.0, 15.0], target=2)
    side = feature(LineString([(X0 + 39 + 10, Y0 - 100), (X0 + 39 + 10, Y0 + 100)]), LINEAR_NAME_FULL="Side St", FEATURE_CODE_DESC="Local")
    r = analyze(inputs(parcel, nbs, [house(24 + 3, 9, 12)], zoning(), streets=[street(), side]))
    assert r.parcel.corner_lot is True
    assert r.parcel.frontage_m == pytest.approx(15.0, abs=0.1)
    assert r.parcel.depth_m == pytest.approx(40.0, abs=0.1)
    assert any("Corner lot" in n for n in r.severance.notes)


def test_corner_lot_with_address_on_the_long_street():
    # Same corner lot but addressed on Side St: the by-law still uses the shorter (Test St) line.
    parcel, nbs = block([12.0, 12.0, 15.0], target=2)
    parcel.properties["LINEAR_NAME_FULL"] = "Side St"
    side = feature(LineString([(X0 + 39 + 10, Y0 - 100), (X0 + 39 + 10, Y0 + 100)]), LINEAR_NAME_FULL="Side St", FEATURE_CODE_DESC="Local")
    r = analyze(inputs(parcel, nbs, [house(24 + 3, 9, 12)], zoning(), streets=[street(), side]))
    assert r.parcel.frontage_m == pytest.approx(15.0, abs=0.1)
    assert any("shorter street line" in c for c in r.caveats)


def test_vacant_lot():
    parcel, nbs = block([12.0] * 3, target=1)
    r = analyze(inputs(parcel, nbs, [], zoning()))
    assert r.coverage.coverage_pct == 0 and r.coverage.open_pct == 100
    assert r.garden_suite.verdict == "not_applicable"
    assert any("vacant" in c for c in r.caveats)


def test_corner_lot_with_rounded_corner_measures_frontage_at_setback():
    # 15 m corner lot whose street corner is cut by a 3 m daylighting triangle.
    parcel_geom = Polygon([(X0 + 24, Y0), (X0 + 36, Y0), (X0 + 39, Y0 + 3), (X0 + 39, Y0 + 40), (X0 + 24, Y0 + 40)])
    parcel = feature(parcel_geom, PARCELID=2, FEATURE_TYPE="COMMON", LINEAR_NAME_FULL="Test St")
    _, nbs = block([12.0, 12.0, 15.0], target=2)
    side = feature(LineString([(X0 + 49, Y0 - 100), (X0 + 49, Y0 + 100)]), LINEAR_NAME_FULL="Side St", FEATURE_CODE_DESC="Local")
    r = analyze(inputs(parcel, nbs, [house(27, 9, 12)], zoning(), streets=[street(), side]))
    assert r.parcel.corner_lot is True
    assert r.parcel.front_lot_line_m == pytest.approx(12.0, abs=0.2)  # curb-side line loses the triangle
    assert r.parcel.frontage_m == pytest.approx(15.0, abs=0.1)  # but zoning frontage is the full width


def test_free_boundary_pieces_split_at_corners():
    parcel = lot(0, 15.0)
    nbs = [lot(-12, 12.0)]  # only a west neighbour -> south, east and north edges are open
    pieces = free_boundary_pieces(parcel, nbs)
    lengths = sorted(round(p.length) for p in pieces)
    assert lengths == [15, 15, 40]  # south (front), north, east


def test_side_setback_table():
    assert side_setback_for_frontage(5.9) == 0.6
    assert side_setback_for_frontage(6.0) == 0.9
    assert side_setback_for_frontage(12.0) == 1.2
    assert side_setback_for_frontage(15.0) == 1.5
    assert side_setback_for_frontage(18.0) == 1.8
    assert side_setback_for_frontage(24.0) == 2.4
    assert side_setback_for_frontage(30.0) == 3.0


def test_parse_stated_area():
    assert analysis.parse_stated_area("464.3631592 sq.m") == pytest.approx(464.36, abs=0.01)
    assert analysis.parse_stated_area(None) is None


def test_geometry_carries_heights_and_splits_straddling_buildings():
    parcel, nbs = block([12.0] * 5, target=2)
    # A semi: one outline straddling the lot line with the west neighbour (x 18..30 over lots 1 and 2).
    semi = house(18, 12.0, 10.0, BUILDINGID=7, DERIVED_HEIGHT=8.1)
    far = house(60, 8.0, 10.0, BUILDINGID=8, DERIVED_HEIGHT=6.5)  # on a lot further east
    lot_inputs = inputs(parcel, nbs, [semi], zoning(), coverage_overlay(35))
    lot_inputs.nearby_buildings = [far]
    r = analyze(lot_inputs)

    (ours,) = r.geometry.buildings
    assert ours.properties.on_lot and ours.properties.height_m == 8.1 and ours.properties.building_id == 7
    assert r.coverage.main_building_m2 == pytest.approx(6.0 * 10.0, abs=0.5)  # only our half counts

    by_id = {b.properties.building_id: b for b in r.geometry.nearby_buildings}
    assert set(by_id) == {7, 8}
    assert not by_id[7].properties.on_lot and by_id[8].properties.height_m == 6.5
    assert len(r.geometry.nearby_parcels) == len(nbs)
