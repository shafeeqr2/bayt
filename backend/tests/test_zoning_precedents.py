"""Precedent counting and the card filter, on in-memory rows (no database)."""

from datetime import date

from app.zoning import cards as playbook
from app.zoning.precedents import Precedent, PrecedentSummary, for_card, matches_card, summarize


def precedent(**over) -> Precedent:
    base = dict(
        sys_id="1",
        reference_file="A0001/24TEY",
        application_type="MV",
        work_type="R Addition",
        sub_type="Add/Alt to Existing Res <= 3 units",
        description="To alter the existing dwelling by constructing a rear addition.",
        zoning_designation="RD (f12.0; a370) (x5)",
        address="12 Example Ave",
        planning_district="Toronto East York",
        in_date=date(2024, 1, 10),
        hearing_date=date(2024, 3, 6),
        decision="approved",
        decision_raw="Approved",
        appeal=None,
        appeal_body=None,
        outcome="approved",
        status="Closed",
        distance_m=120.0,
        lat=43.7,
        lon=-79.4,
    )
    base.update(over)
    return Precedent(**base)


def test_summarize_counts_outcomes_and_rates():
    items = [
        precedent(sys_id="1", outcome="approved"),
        precedent(sys_id="2", outcome="approved", work_type="New R Building", appeal="dismissed"),
        precedent(sys_id="3", outcome="refused", hearing_date=date(2019, 5, 1)),
        precedent(sys_id="4", outcome="withdrawn", hearing_date=None),
        precedent(sys_id="5", outcome="pending", hearing_date=date(2026, 11, 4)),
    ]
    s = summarize(items)
    assert s.total == 5 and s.approved == 2 and s.refused == 1 and s.withdrawn == 1 and s.pending == 1
    assert s.approval_rate == 0.67
    assert s.appealed == 1
    assert s.by_work_type == {"R Addition": 4, "New R Building": 1}
    assert s.oldest_hearing == date(2019, 5, 1) and s.newest_hearing == date(2026, 11, 4)


def test_summarize_empty():
    s = summarize([])
    assert s == PrecedentSummary(
        total=0, approved=0, refused=0, withdrawn=0, deferred=0, pending=0, unknown=0,
        approval_rate=None, appealed=0, by_work_type={}, oldest_hearing=None, newest_hearing=None,
    )


def card(card_id: str):
    return next(c for c in playbook.playbook() if c.id == card_id)


def test_card_filter_by_work_type_and_keyword():
    garden = card("garden-suite-as-of-right")
    sever = card("severance-consent")
    assert matches_card(precedent(work_type="Other", description="To construct a new garden suite in the rear yard."), garden)
    assert not matches_card(precedent(work_type="R Addition", description="A rear addition."), garden)
    assert matches_card(precedent(application_type="CO", work_type="Sever Lot", description="To sever the lot."), sever)
    assert not matches_card(precedent(work_type="R Addition"), sever)
    # Case does not matter.
    assert matches_card(precedent(work_type="SEVER LOT"), sever)


def test_for_card_returns_none_for_cards_that_name_no_comparable_work():
    assert for_card([precedent()], card("heritage-register-constraint")) is None


def test_for_card_examples_are_decided_files_most_recent_first():
    items = [
        precedent(sys_id="old", hearing_date=date(2015, 1, 1), outcome="refused"),
        precedent(sys_id="new", hearing_date=date(2025, 6, 1), outcome="approved"),
        precedent(sys_id="pending", hearing_date=date(2026, 1, 1), outcome="pending"),
        precedent(sys_id="other", work_type="Sever Lot", description="To sever.", outcome="approved"),
    ]
    out = for_card(items, card("minor-variance-setbacks"))
    assert out is not None
    assert out.summary.total == 3  # the severance is not comparable to a setback variance
    assert [p.sys_id for p in out.examples] == ["new", "old"]


def test_every_card_filter_uses_real_work_types():
    """WORK_TYPE values as the open data spells them, so the filter can match."""
    known = {"R Addition", "New R Building", "Sever Lot", "Lot Addition", "Other", "NR Addition", "New NR Building", "Recognize Existing"}
    for c in playbook.playbook():
        assert set(c.precedent_work_types) <= known, c.id


def test_for_card_examples_put_keyword_matches_first():
    houseplex = card("houseplex-removes-fsi-and-raises-coverage")
    items = [
        precedent(sys_id="recent-addition", hearing_date=date(2026, 1, 1)),
        precedent(sys_id="older-fourplex", hearing_date=date(2024, 1, 1), description="To convert the dwelling into a fourplex."),
    ]
    out = for_card(items, houseplex)
    assert out is not None
    assert [p.sys_id for p in out.examples] == ["older-fourplex", "recent-addition"]
