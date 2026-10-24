"""Rule resolution against the numbers in Zoning By-law 569-2013 Chapter 10."""

from app.zoning.standards import ParcelFacts, resolve


def facts(**over) -> ParcelFacts:
    base = dict(
        zone="RD", zone_label="RD (f12.0; a370)", has_site_exception=False,
        lot_frontage_m=12.0, lot_depth_m=40.0, lot_area_m2=480.0,
        min_lot_frontage_m=12.0, min_lot_area_m2=370.0, max_coverage_pct=35.0, fsi_label=None,
    )
    base.update(over)
    return ParcelFacts(**base)


def by(rows):
    return {r.standard: r for r in rows}


def test_rd_defaults_single_house():
    r = by(resolve(facts()))
    assert r["lot_frontage"].value == 12.0 and "10.20.30.20(1)" in r["lot_frontage"].clause_ids
    assert r["lot_area"].value == 370.0
    assert r["lot_coverage"].value == 35.0 and r["lot_coverage"].clause_ids == ["10.20.30.40(1)(A)"]
    assert r["height"].value == 10.0 and r["height"].clause_ids == ["10.20.40.10(1)(B)"]
    assert r["storeys"].status == "unknown"  # overlay not read
    assert r["building_depth"].value == 19.0 and r["building_depth"].clause_ids == ["10.20.40.30(1)"]
    assert r["building_length"].value == 17.0
    assert r["fsi"].status == "not_applicable"  # no d value
    assert r["front_setback"].value == 6.0
    assert r["side_setback"].value == 1.2 and r["side_setback"].clause_ids == ["10.20.40.70(3)(C)"]
    assert r["rear_setback"].value == 10.0  # 25% of 40 m beats 7.5 m
    assert r["side_setback"].source_url.endswith("Chapter10_20.htm")


def test_rd_side_setback_table_uses_required_frontage_not_actual():
    assert by(resolve(facts(min_lot_frontage_m=6.0, lot_frontage_m=20.0)))["side_setback"].value == 0.9
    assert by(resolve(facts(min_lot_frontage_m=15.0)))["side_setback"].value == 1.5
    assert by(resolve(facts(min_lot_frontage_m=30.0)))["side_setback"].value == 3.0
    assert by(resolve(facts(min_lot_frontage_m=5.0)))["side_setback"].clause_ids == ["10.20.40.70(3)(A)"]


def test_houseplex_drops_fsi_and_raises_coverage_to_45():
    r = by(resolve(facts(fsi_label=0.6), proposed_units=2))
    assert r["fsi"].status == "not_applicable" and r["fsi"].clause_ids == ["10.20.40.40(1)(C)"]
    assert r["lot_coverage"].value == 45.0 and r["lot_coverage"].clause_ids == ["10.20.30.40(1)(D)"]
    assert r["storeys"].status == "not_applicable"
    single = by(resolve(facts(fsi_label=0.6), proposed_units=1))
    assert single["fsi"].value == 0.6 and single["lot_coverage"].value == 35.0


def test_height_overlay_when_read():
    r = by(resolve(facts(height_overlay_m=9.0, storeys_overlay=2, height_overlay_checked=True)))
    assert r["height"].value == 9.0 and r["height"].clause_ids == ["10.20.40.10(1)(A)"]
    assert r["storeys"].value == 2.0
    plex = by(resolve(facts(height_overlay_m=9.0, height_overlay_checked=True), proposed_units=3))
    assert plex["height"].value == 10.0  # greater of HT or 10.0 for a houseplex
    none = by(resolve(facts(height_overlay_checked=True)))
    assert none["storeys"].status == "not_applicable"


def test_rd_wide_lot_has_no_depth_or_length_limit():
    r = by(resolve(facts(min_lot_frontage_m=24.0)))
    assert r["building_depth"].status == "not_applicable"
    assert r["building_length"].status == "not_applicable"


def test_other_zones():
    rs = by(resolve(facts(zone="RS", min_lot_frontage_m=15.0)))
    assert rs["side_setback"].value == 1.5 and rs["side_setback"].clause_ids == ["10.40.40.70(3)(D)"]
    rt = by(resolve(facts(zone="RT", min_lot_frontage_m=6.0)))
    assert rt["side_setback"].value == 0.9 and rt["rear_setback"].value == 7.5
    assert rt["building_depth"].status == "unknown"
    rm = by(resolve(facts(zone="RM")))
    assert rm["side_setback"].value == 1.2 and rm["building_depth"].value == 19.0
    r = by(resolve(facts(zone="R", min_lot_frontage_m=6.0, max_coverage_pct=None)))
    assert r["fsi"].value == 0.6 and r["building_depth"].value == 17.0 and r["lot_coverage"].status == "not_applicable"
    cr = resolve(facts(zone="CR"))
    assert all(x.status == "unknown" for x in cr)


def test_site_exception_flags_every_row():
    for r in resolve(facts(has_site_exception=True)):
        assert "site-specific exception" in (r.note or "")
