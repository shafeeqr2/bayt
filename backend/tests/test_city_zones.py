from app.city.zones import zone_label, zone_rules


def rules(zone_string):
    return {rule["label"]: rule["value"] for rule in zone_rules(zone_string)}


def test_detached_zone():
    assert rules("RD (f15.0; a555; d0.45)") == {
        "Minimum lot frontage": "15.0 m",
        "Minimum lot area": "555 m²",
        "Maximum floor space index (density)": "0.45 × lot area",
    }


def test_multiple_dwelling_zone_with_exception():
    assert rules("RM (f12.0; u4; d0.8) (x252)") == {
        "Minimum lot frontage": "12.0 m",
        "Maximum dwelling units": "4",
        "Maximum floor space index (density)": "0.8 × lot area",
        "Site-specific exception": "#252",
    }


def test_area_per_unit_is_not_read_as_lot_area():
    assert rules("RT (au220.0)") == {"Minimum lot area per unit": "220.0 m²"}


def test_commercial_residential_zone():
    assert rules("CR 3.0 (c2.0; r2.5) SS2 (x1)") == {
        "Maximum total floor space index": "3.0 × lot area",
        "Maximum commercial floor space index": "2.0 × lot area",
        "Maximum residential floor space index": "2.5 × lot area",
        "Standard set": "SS2",
        "Site-specific exception": "#1",
    }


def test_empty_zone():
    assert zone_rules(None) == []
    assert zone_label(None) is None
    assert zone_label("RD") == "Residential Detached"
