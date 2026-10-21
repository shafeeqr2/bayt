import math

import pytest
from shapely.geometry import LineString, Polygon, box

from app.lot import floorplan
from app.lot.floorplan import NoPlan, parse_dimension, plan, street_aligned


def room(kind: str, level: str, dimension: str) -> dict:
    return {"type": kind, "level": level, "dimension": dimension}


def rects(level) -> dict[str, Polygon]:
    return {r.name: box(r.x, r.y, r.x + r.width, r.y + r.depth) for r in level.rooms}


HOUSE = box(0, 0, 8, 12)  # 8 m along the street, 12 m deep
MAIN = [
    room("Living room", "Main level", "3.50 m x 4.00 m"),
    room("Dining room", "Main level", "3.20 m x 3.60 m"),
    room("Kitchen", "Main level", "3.40 m x 3.80 m"),
]
UPPER = [
    room("Primary Bedroom", "Second level", "3.80 m x 3.60 m"),
    room("Bedroom 2", "Second level", "3.00 m x 3.10 m"),
]


def test_parse_metric_and_imperial_sizes():
    assert parse_dimension("3.38 m x 3.96 m") == (3.38, 3.96)
    a, b = parse_dimension("16'8'' x 13'10''")
    assert math.isclose(a, 5.08, abs_tol=0.01) and math.isclose(b, 4.216, abs_tol=0.01)
    assert parse_dimension("Measurements not available") is None
    assert parse_dimension("Measurements not available x 0.01 m") is None


def test_rooms_fit_inside_without_overlap():
    level = plan(HOUSE, MAIN).levels[0]
    shapes = rects(level)
    assert set(shapes) >= {"Living room", "Dining room", "Kitchen"}
    for shape in shapes.values():
        assert HOUSE.buffer(0.01).contains(shape)
    names = list(shapes)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            assert shapes[a].intersection(shapes[b]).area < 0.05, (a, b)


def test_living_room_at_the_front_and_kitchen_at_the_back():
    shapes = rects(plan(HOUSE, MAIN).levels[0])
    assert shapes["Living room"].centroid.y < shapes["Dining room"].centroid.y < shapes["Kitchen"].centroid.y


def test_kitchen_touches_dining_room():
    shapes = rects(plan(HOUSE, MAIN).levels[0])
    assert shapes["Kitchen"].distance(shapes["Dining room"]) < 0.15


def test_a_room_bigger_than_the_house_is_reported_not_placed():
    level = plan(HOUSE, MAIN + [room("Great room", "Main level", "9.00 m x 13.00 m")]).levels[0]
    assert "Great room (did not fit)" in level.not_placed


def test_rooms_without_size_or_level_are_reported():
    result = plan(HOUSE, MAIN + [room("Foyer", "Main level", "Measurements not available"), room("Den", "Other", "3 m x 3 m")])
    assert "Foyer (no size given)" in result.levels[0].not_placed
    assert any("Den" in note for note in result.notes)


def test_stairs_sit_in_the_same_place_on_every_level():
    result = plan(HOUSE, MAIN + UPPER)
    stairs = [next(r for r in level.rooms if r.kind == "stairs") for level in result.levels]
    assert len(stairs) == 2
    assert {(s.x, s.y, s.width, s.depth) for s in stairs} == {(stairs[0].x, stairs[0].y, stairs[0].width, stairs[0].depth)}
    assert all(s.assumed for s in stairs)


def test_missing_bathrooms_are_added_from_the_count():
    result = plan(HOUSE, MAIN + UPPER + [room("Bathroom", "Second level", "2.40 m x 1.50 m")], full_baths=2, half_baths=1)
    baths = [(level.name, r.assumed) for level in result.levels for r in level.rooms if r.kind == "bathroom"]
    assert ("Second level", False) in baths  # the listed one
    assert sum(1 for _, assumed in baths if assumed) == 2  # one more full bath and the powder room
    assert ("Main level", True) in baths


def test_attached_garage_is_carved_from_main_and_basement_only():
    rooms = MAIN + UPPER + [room("Recreational, Games room", "Basement", "4.00 m x 5.00 m")]
    result = plan(box(0, 0, 13, 14), rooms, attached_garage=True)
    by_name = {level.name: level for level in result.levels}
    garage = next(r for r in by_name["Main level"].rooms if r.kind == "garage")
    assert (garage.width, garage.depth) == (6.0, 6.0)  # a 13 m wide house gets a double garage
    assert garage.y < 1.0  # at the front
    assert by_name["Basement"].floor_area_m2 == pytest.approx(13 * 14 - 36, abs=0.5)
    assert by_name["Second level"].floor_area_m2 == pytest.approx(13 * 14, abs=0.5)


def test_no_rooms_with_levels_means_no_plan():
    with pytest.raises(NoPlan):
        plan(HOUSE, [room("Kitchen", "Other", "3 m x 3 m")])


def test_street_alignment_puts_the_front_wall_at_zero():
    # A 6 x 10 house rotated 30 degrees, with the street along its short side.
    house = Polygon([(0, 0), (6, 0), (6, 10), (0, 10)])
    street = LineString([(-2, -3), (8, -3)])
    turn = lambda g: __import__("shapely").affinity.rotate(g, 30, origin=(0, 0))  # noqa: E731
    outline, known = street_aligned(turn(house), turn(street))
    minx, miny, maxx, maxy = outline.bounds
    assert known
    assert (minx, miny) == pytest.approx((0, 0), abs=1e-6)
    assert (maxx, maxy) == pytest.approx((6, 10), abs=1e-6)


def test_condos_get_no_plan():
    class Condo:
        building_type = "Apartment"
        ownership_type = "Condominium/Strata"

    with pytest.raises(NoPlan, match="Condo"):
        floorplan.floor_plan_for(Condo(), None)  # type: ignore[arg-type]


def test_a_house_at_an_angle_to_the_street_is_drawn_square_to_its_walls():
    import shapely

    house = Polygon([(0, 0), (6, 0), (6, 10), (0, 10)])
    street = shapely.affinity.rotate(LineString([(-2, -3), (8, -3)]), 12, origin=(3, 5))  # street 12 degrees off
    outline, _ = street_aligned(house, street)
    minx, miny, maxx, maxy = outline.bounds
    assert (maxx - minx, maxy - miny) == pytest.approx((6, 10), abs=1e-6)


def test_stairs_do_not_block_the_room_that_needs_the_full_width():
    narrow = box(0, 0, 4.9, 18.6)
    rooms = [
        room("Recreational, Games room", "Basement", "7.67 m x 4.14 m"),
        room("Laundry room", "Basement", "2.13 m x 3.68 m"),
        room("Living room", "Main level", "3.80 m x 4.20 m"),
        room("Kitchen", "Main level", "3.60 m x 3.90 m"),
    ]
    result = plan(narrow, rooms)
    assert all(not level.not_placed for level in result.levels)


def test_a_room_slightly_wider_than_the_house_is_drawn_smaller_and_flagged():
    result = plan(box(0, 0, 3.72, 18.0), [room("Primary Bedroom", "Second level", "4.24 m x 3.99 m")])
    primary = next(r for r in result.levels[0].rooms if r.name == "Primary Bedroom")
    assert primary.scale is not None and primary.scale >= 0.85
    assert primary.size == "4.24 m x 3.99 m"
    assert any("smaller" in note for note in result.notes)


def test_a_tight_narrow_house_still_keeps_the_kitchen_behind_the_living_room():
    narrow = box(0, 0, 3.8, 17.5)
    rooms = [
        room("Living room", "Main level", "3.00 m x 3.60 m"),
        room("Dining room", "Main level", "3.30 m x 3.80 m"),
        room("Kitchen", "Main level", "2.80 m x 4.70 m"),
        room("Eating area", "Main level", "2.40 m x 3.20 m"),
    ]
    shapes = rects(plan(narrow, rooms).levels[0])
    assert shapes["Living room"].centroid.y < shapes["Kitchen"].centroid.y
