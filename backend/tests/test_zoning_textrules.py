"""The rule-based reader of plan text: what it reads, what it leaves alone."""

import pytest

from app.zoning.textrules import describe, extract


def test_addition_with_storey_height_and_rear_yard():
    out = extract("Keep the house and add a third storey about 10.5 m high, then push the back wall out so the rear yard is 6.5 m.")
    assert out["project"] == "addition" and out["keep_existing_walls"] is True
    assert out["proposed_storeys"] == 3
    assert out["proposed_height_m"] == 10.5
    assert out["proposed_rear_setback_m"] == 6.5


def test_tear_down_and_feet():
    out = extract("Tear it down and build a new 2 storey house, 30 feet high, with a 25 ft rear yard and a floor area of 2,500 sq ft")
    assert out["project"] == "new_build" and out["keep_existing_walls"] is False
    assert out["proposed_storeys"] == 2
    assert out["proposed_height_m"] == pytest.approx(9.14, abs=0.01)
    assert out["proposed_rear_setback_m"] == pytest.approx(7.62, abs=0.01)
    assert out["proposed_gfa_m2"] == pytest.approx(232.3, abs=0.1)


def test_units_and_plex_words():
    assert extract("Convert it into a fourplex")["proposed_units"] == 4
    assert extract("Convert it into a fourplex")["project"] == "convert"
    assert extract("I want 3 units in the house")["proposed_units"] == 3


def test_sever_and_suites():
    assert extract("Split the lot in two and build on both") == {"project": "sever", "sever_lot": True}
    assert extract("A garden suite in the back") == {"project": "garden_suite"}
    assert extract("laneway house behind the garage")["project"] == "laneway_suite"


def test_setbacks_and_areas():
    out = extract("side yard 0.6 m, front setback of 6 m, footprint 120 m2, building depth of 17 m")
    assert out["proposed_side_setback_m"] == 0.6
    assert out["proposed_front_setback_m"] == 6.0
    assert out["proposed_footprint_m2"] == 120.0
    assert out["proposed_building_depth_m"] == 17.0


def test_nothing_is_guessed():
    assert extract("Hello, what can I do with this place?") == {}
    assert "proposed_height_m" not in extract("a tall order")


def test_describe_lines():
    lines = describe({"project": "addition", "keep_existing_walls": True, "proposed_storeys": 3, "proposed_height_m": 10.5, "proposed_rear_setback_m": 6.5})
    assert lines == ["Addition, main walls kept", "Storeys 3", "Height 10.5 m", "Rear yard 6.5 m"]
    assert describe({}) == []
    assert describe({"keep_existing_walls": False}) == ["Main walls removed"]
