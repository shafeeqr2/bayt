from app.models import Listing, ListingCityData
from app.strategy import estimate, rents


def listing(**overrides) -> Listing:
    fields = dict(
        id="1",
        price=1_000_000,
        building_type="House",
        ownership_type="Freehold",
        bedrooms_above=3,
        bedrooms_below=1,
        bedrooms_total=4,
        city="Toronto",
        tax_annual=5_000,
        maintenance_fee_monthly=None,
        description="",
        rooms=[],
        raw={"_details": {"Building": {}}},
    )
    fields.update(overrides)
    return Listing(**fields)


def with_basement(listing_: Listing, features: str) -> Listing:
    listing_.raw["_details"]["Building"]["BasementFeatures"] = features
    return listing_


# --- Stated rent ----------------------------------------------------------------------------


def test_whole_unit_rent_from_description():
    stated = estimate.stated_rent(listing(building_type="Apartment", description="Monthly rent is $2,350, plus utilities."))
    assert stated.monthly == 2350
    assert stated.whole_property is False
    assert "2,350" in stated.sentence


def test_total_income_is_annualised_when_it_says_so():
    stated = estimate.stated_rent(listing(building_type="Duplex", description="Total Annual Rental Income: $97,080."))
    assert stated.monthly == 8090
    assert stated.whole_property is True


def test_large_bare_amount_is_treated_as_yearly():
    stated = estimate.stated_rent(listing(description="Current Net Well Over $100k, $145k Gross, Easy 20% Upside."))
    assert stated.monthly == round(145_000 / 12)


def test_parking_rent_is_ignored():
    text = "Rental Parking Spot Arrangement For $100/Month Can Be Continued!"
    assert estimate.stated_rent(listing(building_type="Apartment", description=text)) is None


def test_basement_rent_does_not_count_as_whole_house_rent():
    text = "The one-bedroom basement suite is rented for $1,600/month, all-inclusive."
    assert estimate.stated_rent(listing(description=text)) is None


def test_basement_rent_counts_for_a_condo_where_suite_means_the_unit():
    text = "The suite is currently leased at $2,250 per month."
    assert estimate.stated_rent(listing(building_type="Apartment", description=text)).monthly == 2250


def test_stated_rent_far_from_market_falls_back_to_market():
    # "rented at $1950" on a 4+2 house is clearly the basement alone.
    row = estimate.estimate(listing(description="Currently rented at $1950/month to a great tenant."), None, None)
    assert row.rent_source == "market"


# --- Market rent ----------------------------------------------------------------------------


def test_condo_rent_follows_city_and_bedrooms():
    row = estimate.estimate(listing(building_type="Apartment", ownership_type="Condominium/Strata", bedrooms_above=2, bedrooms_below=0, city="Vaughan"), None, None)
    assert row.rent_monthly == rents.APARTMENT_RENTS["Vaughan"][2]
    assert "Vaughan" in row.rent_note and "2-bedroom" in row.rent_note


def test_house_rent_is_townhouse_rate_plus_premium():
    row = estimate.estimate(listing(), None, None)
    assert row.rent_monthly == round(rents.TOWNHOUSE_RENTS["Toronto"][1] * rents.HOUSE_OVER_TOWNHOUSE)


def test_house_with_basement_apartment_adds_suite_rent():
    row = estimate.estimate(with_basement(listing(), "Apartment in basement, Separate entrance"), None, None)
    base = round(rents.TOWNHOUSE_RENTS["Toronto"][1] * rents.HOUSE_OVER_TOWNHOUSE)
    assert row.has_suite is True
    assert row.rent_monthly == base + rents.BASEMENT_SUITE_RENT[1]


def test_unknown_city_uses_toronto_rates():
    row = estimate.estimate(listing(building_type="Apartment", bedrooms_above=1, city="Etobicoke"), None, None)
    assert row.rent_monthly == rents.APARTMENT_RENTS["Toronto"][1]


def test_multiplex_rent_is_per_unit():
    row = estimate.estimate(listing(building_type="Triplex", bedrooms_above=6, bedrooms_below=0, bedrooms_total=6), None, None)
    assert row.units == 3
    assert row.rent_monthly == 3 * rents.multiplex_unit_rent("Toronto", 2)


# --- Costs and returns ------------------------------------------------------------------------


def test_cap_rate_uses_published_tax_and_allowances():
    row = estimate.estimate(listing(), None, None)
    gross = row.rent_monthly * 12
    expected_costs = 5_000 + estimate.INSURANCE_FREEHOLD + 5_000 + round(gross * estimate.VACANCY_RATE)
    assert row.expenses_annual == expected_costs
    assert row.cap_rate_pct == round((gross - expected_costs) / 1_000_000 * 100, 2)
    assert row.gross_yield_pct == round(gross / 1_000_000 * 100, 2)


def test_condo_costs_include_fees_but_not_house_maintenance():
    row = estimate.estimate(
        listing(building_type="Apartment", ownership_type="Condominium/Strata", maintenance_fee_monthly=700, price=600_000),
        None,
        None,
    )
    costs = estimate.expenses(listing(building_type="Apartment", ownership_type="Condominium/Strata", maintenance_fee_monthly=700, price=600_000), row.gross_annual)
    assert costs.condo_fees == 8_400
    assert costs.insurance == estimate.INSURANCE_CONDO
    assert costs.maintenance == estimate.MAINTENANCE_CONDO


def test_missing_tax_is_estimated_from_price():
    costs = estimate.expenses(listing(tax_annual=None), 40_000)
    assert costs.tax_estimated is True
    assert costs.property_tax == 5_000


# --- Ways to add value ------------------------------------------------------------------------


def test_separate_entrance_without_apartment_is_suite_potential():
    row = estimate.estimate(with_basement(listing(), "Separate entrance"), None, None)
    assert (row.has_suite, row.suite_potential) == (False, True)
    assert "separate entrance" in row.suite_note


def test_separate_entrance_is_recorded_from_the_basement_features():
    row = estimate.estimate(with_basement(listing(), "Separate entrance, Walk out"), None, None)
    assert row.separate_entrance == "The listing records a separate entrance to the basement."


def test_separate_entrance_is_read_from_the_description():
    row = estimate.estimate(listing(description="Finished basement with a seperate side entrance."), None, None)
    assert row.separate_entrance == "The description mentions a separate entrance."
    assert estimate.estimate(listing(description="Bright and spacious."), None, None).separate_entrance is None


def test_apartment_with_separate_entrance_still_counts_as_a_suite_and_an_entrance():
    row = estimate.estimate(with_basement(listing(), "Apartment in basement, Separate entrance"), None, None)
    assert row.has_suite is True
    assert row.separate_entrance is not None


def test_condos_never_get_a_separate_entrance():
    row = estimate.estimate(
        listing(building_type="Apartment", ownership_type="Condominium/Strata", description="Separate entrance!"), None, None
    )
    assert row.separate_entrance is None


def test_second_kitchen_in_basement_means_a_suite():
    rooms = [{"type": "Kitchen", "level": "Main level", "dimension": "4 m x 3 m"}, {"type": "Kitchen", "level": "Basement", "dimension": "3 m x 3 m"}]
    row = estimate.estimate(listing(rooms=rooms), None, None)
    assert row.has_suite is True


def test_condos_never_get_suite_flags():
    row = estimate.estimate(listing(building_type="Apartment", ownership_type="Condominium/Strata", description="Great income suite!"), None, None)
    assert (row.has_suite, row.suite_potential) == (False, False)


def test_convertible_room_needs_bedroom_size():
    rooms = [
        {"type": "Den", "level": "Second level", "dimension": "2.2 m x 1.92 m"},  # too small
        {"type": "Office", "level": "Main level", "dimension": "3.5 m x 3 m"},
    ]
    assert estimate.convertible_room(listing(rooms=rooms)) == "Office, 3.5 m × 3 m, main level"
    assert estimate.convertible_room(listing(rooms=rooms[:1])) is None


def test_condo_den_does_not_count_as_a_bedroom():
    rooms = [{"type": "Den", "level": "Flat", "dimension": "3.5 m x 3 m"}]
    assert estimate.convertible_room(listing(building_type="Apartment", rooms=rooms)) is None


def test_lot_verdicts_and_zoning_are_copied():
    city = ListingCityData(listing_id="1", match_method="address", zone_category="RD")
    lot = {"garden_suite": {"verdict": "likely"}, "severance": {"verdict": "unlikely"}, "zoning": {"as_of_right_units": 6}}
    row = estimate.estimate(listing(), city, lot)
    assert (row.garden_suite, row.severance) == ("likely", "unlikely")
    assert row.multiplex_zone is True and row.as_of_right_units == 6


def test_condo_townhouse_in_residential_zone_is_not_a_multiplex_site():
    city = ListingCityData(listing_id="1", match_method="address", zone_category="RD")
    row = estimate.estimate(listing(building_type="Row / Townhouse", ownership_type="Condominium/Strata"), city, None)
    assert row.multiplex_zone is False
