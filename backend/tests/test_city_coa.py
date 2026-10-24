"""Normalization of Committee of Adjustment open-data rows (no database)."""

from datetime import date

import pytest

from app.city.coa import (
    dedupe,
    normalize_appeal,
    normalize_decision,
    normalize_number,
    normalize_row,
    outcome_of,
    parse_date,
)


@pytest.mark.parametrize(
    ("raw", "status", "expected"),
    [
        ("Approved", "Closed", "approved"),
        ("approved", "Closed", "approved"),
        ("Granted", "Closed", "approved"),
        ("Approved wih Conditions", "Closed", "approved_with_conditions"),
        ("conditional approval", "Closed", "approved_with_conditions"),
        ("APPROVED ON CONDITION", "Closed", "approved_with_conditions"),
        ("Granted with condition", "Closed", "approved_with_conditions"),
        ("Partial Approval", "Closed", "approved_in_part"),
        ("Partially Granted", "Closed", "approved_in_part"),
        ("Refused", "Closed", "refused"),
        ("REFUSED", "Closed", "refused"),
        ("Not Granted", "Closed", "refused"),
        ("Withdrawn", "Closed", "withdrawn"),
        ("application withdrawn", "Application Withdrawn", "withdrawn"),
        ("Deferred", "Closed", "deferred"),
        ("Something else", "Closed", "unknown"),
        # Blank decision: the status decides.
        ("", "Closed", "unknown"),
        (None, "Cancelled", "withdrawn"),
        (None, "Application Withdrawn", "withdrawn"),
        (None, "Hearing Scheduled", "pending"),
        (None, "TLAB Appeal", "pending"),
        (None, "Approved with Conditions", "approved_with_conditions"),
        (None, "Conditional Consent", "approved_with_conditions"),
        (None, "Refused", "refused"),
        (None, "Postponed", "deferred"),
    ],
)
def test_normalize_decision(raw, status, expected):
    assert normalize_decision(raw, status) == expected


@pytest.mark.parametrize(
    ("raw", "status", "expected"),
    [
        ("OMB Approved", "Closed", ("approved", "OMB")),
        ("OMB Refused", "Closed", ("refused", "OMB")),
        ("TLAB Approved", "Closed", ("approved", "TLAB")),
        ("CofA Decision Overturned - TLAB Approved with Conditions", "Closed", ("approved", "TLAB")),
        ("Appeal Dismissed", "Closed", ("dismissed", None)),
        ("Appeal Withdrawn", "Closed", ("dismissed", None)),
        ("Dec 9, 2018", "Closed", ("unknown", None)),
        (None, "TLAB Appeal", ("pending", "TLAB")),
        (None, "OMB Appeal", ("pending", "OMB")),
        (None, "Closed", (None, None)),
    ],
)
def test_normalize_appeal(raw, status, expected):
    assert normalize_appeal(raw, status) == expected


def test_outcome_prefers_the_board_when_it_decided_the_file():
    assert outcome_of("refused", "approved") == "approved"
    assert outcome_of("approved", "refused") == "refused"
    assert outcome_of("approved_with_conditions", "dismissed") == "approved"
    assert outcome_of("refused", "dismissed") == "refused"
    assert outcome_of("approved", "pending") == "pending"
    assert outcome_of("approved_in_part", None) == "approved"
    assert outcome_of("withdrawn", None) == "withdrawn"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-02", date(2026, 9, 2)),
        ("2026-07-08T00:00:00", date(2026, 7, 8)),
        ("Jun 12, 2009", date(2009, 6, 12)),
        ("", None),
        (None, None),
        ("not a date", None),
        ("0227-11-21", None),  # typo years in the city's data
        ("3008-12-03", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("155", ("155", 155)),
        ("12 A", ("12A", 12)),
        ("3345-3347", ("3345-3347", 3345)),
        ("10 1/2", ("101/2", 10)),
        ("", (None, None)),
        (None, (None, None)),
    ],
)
def test_normalize_number(raw, expected):
    assert normalize_number(raw) == expected


def raw_row(**over):
    row = {
        "sys_id": "5873824",
        "source": "closed",
        "application_type": "MV",
        "in_date": "2026-07-08T00:00:00",
        "planning_district": "Toronto East York",
        "ward_number": "9",
        "ward_name": "Davenport",
        "street_num": "155",
        "street_name": "D'ARCY",
        "street_type": "St",
        "street_direction": " ",
        "postal": "M6H",
        "reference_file": "A0498/26TEY",
        "sub_type": "New Res dwellings <= 3 units",
        "work_type": "New R Building",
        "zoning_designation": "R (d0.6) (x735) (ZAP)",
        "description": "To construct a new laneway suite.",
        "hearing_date": "2026-09-02",
        "c_of_a_descision": "Approved",
        "omb_descision": None,
        "statusdesc": "Closed",
        "finaldate": "2026-09-23T00:00:00",
        "number_of_lots_created": None,
    }
    row.update(over)
    return row


def test_normalize_row_builds_the_join_keys_and_the_outcome():
    app = normalize_row(raw_row())
    assert app is not None
    assert app.street_name_norm == "DARCY"  # same normalization as the listing matcher
    assert app.street_type == "ST"
    assert app.street_direction is None  # a blank direction is "no direction", not " "
    assert app.street_num_norm == "155" and app.street_num_int == 155
    assert app.ward == "Davenport (9)"
    assert app.hearing_date == date(2026, 9, 2)
    assert app.final_date == date(2026, 9, 23)
    assert app.decision == "approved" and app.appeal is None and app.outcome == "approved"


def test_normalize_row_without_sys_id_is_dropped():
    assert normalize_row(raw_row(sys_id="")) is None


def test_dedupe_keeps_the_decided_row():
    pending = normalize_row(raw_row(c_of_a_descision="", statusdesc="Hearing Scheduled", finaldate=""))
    decided = normalize_row(raw_row())
    assert pending is not None and decided is not None
    kept = dedupe([pending, decided])
    assert len(kept) == 1 and kept[0].outcome == "approved"
    assert dedupe([decided, pending])[0].outcome == "approved"
