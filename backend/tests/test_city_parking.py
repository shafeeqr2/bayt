from app.city.parking import parking_rules


def labels(rules):
    return {rule.label: rule.value for rule in rules}


def test_outside_bylaw_has_no_rules():
    assert parking_rules(None, "B", "House") == ([], None)


def test_house_has_no_minimum_or_maximum():
    rules, note = parking_rules("RD", "B", "House")
    assert labels(rules) == {
        "Parking zone": "Parking Zone B (inner suburbs near transit)",
        "Required parking": "None (Toronto removed minimums in 2022)",
        "Maximum parking": "No cap for houses and houseplexes",
    }
    assert "does not require adding parking" in note


def test_house_outside_parking_zones_has_no_zone_row():
    rules, _ = parking_rules("RD", None, "Row / Townhouse")
    assert "Parking zone" not in labels(rules)


def test_apartment_rates_follow_parking_zone():
    rules, note = parking_rules("RA", "A", "Apartment", bedrooms=2)
    assert labels(rules)["Maximum resident parking, two bedroom unit"] == "0.8 spaces per unit"
    assert labels(rules)["Minimum visitor parking"] == "2 spaces plus 0.01 per unit"
    assert "new apartment buildings" in note

    rules, _ = parking_rules("RA", None, "Apartment", bedrooms=3)
    assert labels(rules)["Maximum resident parking, three or more bedrooms unit"] == "1.2 spaces per unit"
    assert labels(rules)["Minimum visitor parking"] == "2 spaces plus 0.05 per unit"


def test_apartment_without_bedroom_count_skips_resident_rows():
    rules, _ = parking_rules("CR", "B", "Apartment", bedrooms=None)
    assert set(labels(rules)) == {"Parking zone", "Minimum visitor parking"}
