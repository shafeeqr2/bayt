from app.strategy.parse import parse_strategy


def params(text: str, communities=()) -> dict:
    return parse_strategy(text, communities).params


def test_return_range_becomes_minimum_cap_rate():
    parsed = parse_strategy("Looking for property with 6-8% return.")
    assert parsed.params["min_cap_rate"] == "6"
    assert parsed.params["sort"] == "cap_rate_desc"
    assert any("6%" in line for line in parsed.understood)


def test_yield_wording_maps_to_gross_yield():
    assert params("at least a 5% yield")["min_gross_yield"] == "5"


def test_income_and_savings():
    p = params("I make $140k and have $150k saved")
    assert p["income"] == "140000"
    assert p["down_payment"] == "150000"


def test_income_written_as_a_year():
    assert params("household income is 180,000 a year")["income"] == "180000"


def test_budget_cues_set_max_price():
    assert params("something under 800k")["max_price"] == "800000"
    assert params("budget of $1.2M")["max_price"] == "1200000"
    assert params("1.2 million max")["max_price"] == "1200000"


def test_bedroom_conversion():
    parsed = parse_strategy("Might want to turn a 2-bed into a 3-bed.")
    assert parsed.params["min_beds"] == "2"
    assert parsed.params["potential"] == ["extra_bedroom"]


def test_value_add_phrases():
    assert params("a house where I could add a garden suite")["potential"] == ["garden_suite"]
    assert params("lot I can sever")["potential"] == ["severance"]
    assert params("convert into a fourplex")["potential"] == ["multiplex"]
    assert params("basement apartment with a tenant")["potential"] == ["suite"]
    assert params("could add a basement suite")["potential"] == ["suite_potential"]
    assert params("basement with a seperate entrance")["potential"] == ["separate_entrance"]


def test_cash_flow_wording():
    assert params("must be cash flow positive")["min_cash_flow"] == "0"
    assert params("cash flow of $500/month")["min_cash_flow"] == "500"
    assert params("pays for itself")["sort"] == "cash_flow_desc"


def test_home_type_and_city():
    p = params("a condo in Vaughan with 2 beds and 2 baths")
    assert p["building_type"] == "Apartment"
    assert p["city"] == "Vaughan"
    assert p["min_beds"] == "2"
    assert p["min_baths"] == "2"


def test_neighbourhood_becomes_keyword():
    assert params("townhouse in Leslieville", ["Leslieville", "South Riverdale"])["q"] == "Leslieville"


def test_financing_terms():
    p = params("20% down at 4.5% interest over 30 years")
    assert p["down_payment_pct"] == "20"
    assert p["interest_rate"] == "4.5"
    assert p["amortization"] == "30"


def test_living_in_it_changes_occupancy():
    assert params("I want to live in it and rent the basement")["occupancy"] == "live_in"
    assert params("a rental property")["occupancy"] == "rent_out"


def test_unmatched_text_is_reported():
    parsed = parse_strategy("close to good schools, under 900k")
    assert parsed.params["max_price"] == "900000"
    assert parsed.unmatched == ["close to good schools"]


def test_empty_text():
    parsed = parse_strategy("   ")
    assert parsed.params == {} and parsed.understood == []
