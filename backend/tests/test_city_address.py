import pytest

from app.city.address import ParsedAddress, parse


@pytest.mark.parametrize(
    ("address", "expected"),
    [
        ("49 Winterton Drive", ParsedAddress(None, "49", "WINTERTON", "Dr", None)),
        ("610 - 1787 St. Clair Avenue W", ParsedAddress("610", "1787", "ST CLAIR", "Ave", "W")),
        ("52A Robinson Avenue", ParsedAddress(None, "52A", "ROBINSON", "Ave", None)),
        ("258 O'Connor Drive", ParsedAddress(None, "258", "OCONNOR", "Dr", None)),
        ("Th103 - 95 Mcmahon Drive", ParsedAddress("Th103", "95", "MCMAHON", "Dr", None)),
        ("219 Fort York Boulevard Unit# 2806", ParsedAddress("2806", "219", "FORT YORK", "Blvd", None)),
        ("2301 - 360 Ridelle Ave Avenue", ParsedAddress("2301", "360", "RIDELLE", "Ave", None)),
        # A type word that is the whole street name stays the name.
        ("100 Avenue Road", ParsedAddress(None, "100", "AVENUE", "Rd", None)),
        ("5 The Kingsway", ParsedAddress(None, "5", "THE KINGSWAY", None, None)),
        ("12 West Street", ParsedAddress(None, "12", "WEST", "St", None)),
    ],
)
def test_parse(address, expected):
    assert parse(address) == expected


@pytest.mark.parametrize("address", [None, "", "Address Not Available", "Lot 5 Concession Road"])
def test_parse_rejects_addresses_without_a_street_number(address):
    assert parse(address) is None
