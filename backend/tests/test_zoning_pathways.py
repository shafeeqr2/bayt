"""End to end on synthetic geometry: lot analysis -> gaps -> facts -> cards -> response.

The toy block is the one in test_lot_analysis: 12 m wide, 40 m deep lots in an
RD (f12.0; a370) zone with a 35% coverage overlay, street to the south.
"""

import pytest

from app.lot.analysis import analyze
from app.zoning import cards as playbook
from app.zoning.facts import FACT_PATHS, build_facts
from app.zoning.gaps import analyze_gaps
from app.zoning.intent import Intent
from app.zoning.predicate import Truth, parse, paths
from app.zoning.pathways import analyze_pathways
from tests.test_lot_analysis import block, coverage_overlay, house, inputs, zoning


def gaps_by(rows):
    return {g.standard: g for g in rows}


@pytest.fixture
def narrow_house_lot():
    """12 m lot, 7.5 m wide house set 0.6 m from the west line (short of the 1.2 m RD setback)."""
    parcel, nbs = block([12.0] * 7, target=3)
    bld = [house(36 + 0.6, 7.5, 12.0, setback=6.0, BUILDINGID=1, DERIVED_HEIGHT=7.2)]
    return analyze(inputs(parcel, nbs, bld, zoning(), coverage_overlay(35)))


def test_envelope_measures_existing_setbacks(narrow_house_lot):
    e = narrow_house_lot.envelope
    assert e is not None
    assert e.side_setback_left_m == pytest.approx(0.6, abs=0.05)
    assert e.side_setback_right_m == pytest.approx(12.0 - 0.6 - 7.5, abs=0.05)
    assert e.side_setback_min_m == pytest.approx(0.6, abs=0.05)
    assert e.front_setback_m == pytest.approx(6.0, abs=0.05)
    assert e.rear_setback_m == pytest.approx(40.0 - 18.0, abs=0.05)
    assert e.building_length_m == pytest.approx(12.0, abs=0.05)
    assert e.building_depth_m == pytest.approx(12.0, abs=0.05)  # rear wall 18 m from the front line, 12 m past the 6 m setback
    assert e.height_m == 7.2
    assert e.existing_side_setback_required_m == 1.2


def test_two_walls_case_gets_the_alteration_card_first(narrow_house_lot):
    """Keep the side walls, push the rear wall out: the side setback is short but the retention card applies."""
    intent = Intent(mode="buyer", keep_existing_walls=True, proposed_rear_setback_m=8.0, proposed_storeys=2)
    rows = analyze_gaps(narrow_house_lot, intent)
    g = gaps_by(rows)
    assert g["side_setback"].status == "short" and g["side_setback"].proposed_source == "existing"
    assert g["side_setback"].required == 1.2 and g["side_setback"].delta == pytest.approx(0.6, abs=0.05)
    assert g["side_setback"].existing_status == "short"
    assert g["rear_setback"].status == "short"  # 8.0 m against max(7.5, 25% of 40 m) = 10.0 m
    assert g["rear_setback"].required == 10.0
    assert g["height"].status == "unknown"  # storeys given, height not
    assert g["fsi"].status == "not_applicable"

    facts = build_facts(narrow_house_lot, intent, rows)
    assert set(facts) <= set(FACT_PATHS)
    cands = playbook.match(facts)
    ids = [c.card.id for c in cands]
    assert ids[0] == "keep-existing-walls-alteration"
    top = cands[0]
    assert top.result is Truth.TRUE
    assert "side_setback" in top.covers_gaps and "rear_setback" in top.covers_gaps
    assert "narrow-lot-addition-keeps-side-setback" in ids
    assert "minor-variance-setbacks" in ids
    assert "new-building-loses-existing-rights" not in ids  # walls stay
    assert "severance-consent" not in ids
    # Every surviving card is TRUE or UNKNOWN, never FALSE.
    assert all(c.result is not Truth.FALSE for c in cands)


def test_rebuild_loses_the_existing_setback(narrow_house_lot):
    intent = Intent(project="new_build", proposed_side_setback_m=0.6, proposed_height_m=9.5)
    out = analyze_pathways(narrow_house_lot, intent)
    ids = [c.card_id for c in out.candidates]
    assert "new-building-loses-existing-rights" in ids
    assert "keep-existing-walls-alteration" not in ids
    assert "narrow-lot-addition-keeps-side-setback" not in ids
    assert "minor-variance-setbacks" in ids
    assert "side_setback" in out.short_standards
    assert "height" not in out.short_standards


def test_houseplex_pathway_when_fsi_is_short():
    """A d0.6 zone label: 320 m2 of floor area on a 480 m2 lot is FSI 0.67, short as a house, fine as a houseplex."""
    parcel, nbs = block([12.0] * 7, target=3)
    bld = [house(36 + 2.25, 7.5, 12.0, BUILDINGID=1, DERIVED_HEIGHT=7.2)]
    lot = analyze(inputs(parcel, nbs, bld, zoning(ZN_STRING="RD (f12.0; a370; d0.6)"), coverage_overlay(35)))
    out = analyze_pathways(lot, Intent(mode="professional", keep_existing_walls=True, proposed_gfa_m2=320))
    g = {x.standard: x for x in out.gaps}
    assert g["fsi"].status == "short" and g["fsi"].required == 0.6 and g["fsi"].proposed == pytest.approx(0.667, abs=0.001)
    ids = [c.card_id for c in out.candidates]
    assert "houseplex-removes-fsi-and-raises-coverage" in ids
    assert "minor-variance-coverage-fsi" in ids
    plex = next(c for c in out.candidates if c.card_id == "houseplex-removes-fsi-and-raises-coverage")
    assert plex.result == "applies" and "fsi" in plex.covers_gaps
    assert plex.questions  # professional notes in professional mode
    # As a 2-unit plan the FSI limit is gone.
    out2 = analyze_pathways(lot, Intent(keep_existing_walls=True, proposed_gfa_m2=320, proposed_units=2))
    assert {x.standard: x for x in out2.gaps}["fsi"].status == "not_applicable"
    assert "houseplex-removes-fsi-and-raises-coverage" not in [c.card_id for c in out2.candidates]


def test_severance_intent_runs_split_values():
    parcel, nbs = block([12.0] * 7, target=3)
    bld = [house(36 + 2.25, 7.5, 12.0, BUILDINGID=1)]
    lot = analyze(inputs(parcel, nbs, bld, zoning(), coverage_overlay(35)))
    out = analyze_pathways(lot, Intent(sever_lot=True))
    g = {x.standard: x for x in out.gaps}
    assert g["lot_frontage"].proposed == pytest.approx(6.0, abs=0.1) and g["lot_frontage"].status == "short"
    assert g["lot_area"].proposed == pytest.approx(240.0, abs=2) and g["lot_area"].status == "short"
    sev = next(c for c in out.candidates if c.card_id == "severance-consent")
    assert sev.result == "applies" and set(sev.covers_gaps) == {"lot_frontage", "lot_area"}


def test_unknown_facts_are_reported_not_guessed(narrow_house_lot):
    out = analyze_pathways(narrow_house_lot, Intent())  # nothing proposed
    assert "side_setback" in out.unknown_standards or "side_setback" in out.short_standards
    assert "height" in out.unknown_standards
    assert all(c.result in ("applies", "may_apply") for c in out.candidates)
    assert out.disclaimer
    assert any("Height Overlay" in c for c in out.caveats)


def test_heritage_constraint_and_overlay():
    parcel, nbs = block([12.0] * 7, target=3)
    bld = [house(36 + 2.25, 7.5, 12.0, BUILDINGID=1, DERIVED_HEIGHT=7.2)]
    lot = analyze(inputs(parcel, nbs, bld, zoning(), coverage_overlay(35)))
    out = analyze_pathways(lot, Intent(proposed_height_m=9.5), height_limit_m=9.0, height_limit_storeys=2, overlay_checked=True, heritage_listed=True)
    g = {x.standard: x for x in out.gaps}
    assert g["height"].required == 9.0 and g["height"].status == "short"
    assert g["storeys"].required == 2.0
    assert out.candidates[0].card_id == "heritage-register-constraint"  # constraints come first
    assert not any("Height Overlay" in c for c in out.caveats)


def test_every_card_is_well_formed():
    cards = playbook.load_cards()
    assert len(cards) >= 10
    for c in cards:
        assert c.risks and c.legal_basis and c.mechanics
        assert paths(parse(c.trigger)) <= set(FACT_PATHS)
        assert c.category != "constraint" or c.covers == []
    assert len({c.id for c in cards}) == len(cards)


def test_analysis_carries_the_lot_shape_for_the_model(narrow_house_lot):
    """The page draws a schematic lot from these numbers; they must be the by-law measurements, not guesses."""
    out = analyze_pathways(narrow_house_lot, Intent(mode="buyer", project="addition", keep_existing_walls=True))
    assert out.lot.frontage_m == pytest.approx(12.0, abs=0.05)
    assert out.lot.depth_m == pytest.approx(40.0, abs=0.05)
    assert out.lot.area_m2 == pytest.approx(480.0, rel=0.01)
    e = out.lot.existing
    assert e is not None
    assert e.front_setback_m == pytest.approx(6.0, abs=0.05)
    assert e.rear_setback_m == pytest.approx(22.0, abs=0.05)
    assert e.side_setback_left_m == pytest.approx(0.6, abs=0.05)
    assert e.building_length_m == pytest.approx(12.0, abs=0.05)
    assert e.height_m == 7.2
    assert e.footprint_m2 == pytest.approx(7.5 * 12.0, rel=0.02)
