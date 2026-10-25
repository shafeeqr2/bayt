"""Phase 2 without the network: a fake client stands in for Claude.

Covers the intent merge (form fields win), invalid numbers from the model, the
citation check (unknown or missing citations drop the paragraph), the cache key
and the no-credentials path.
"""

from types import SimpleNamespace

import pytest

from app.lot.analysis import analyze
from app.zoning import answer as m
from app.zoning.intent import Intent
from app.zoning.pathways import analyze_pathways
from app.zoning.precedents import Precedent
from tests.test_lot_analysis import block, coverage_overlay, house, inputs, zoning
from tests.test_zoning_precedents import precedent


class FakeClient:
    """Returns the queued parsed objects in order; records what it was asked."""

    def __init__(self, *outputs, stop_reason="end_turn"):
        self.outputs = list(outputs)
        self.calls = []
        self.stop_reason = stop_reason
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self.outputs.pop(0), stop_reason=self.stop_reason)


@pytest.fixture
def analysis():
    parcel, nbs = block([12.0] * 7, target=3)
    bld = [house(36 + 0.6, 7.5, 12.0, setback=6.0, BUILDINGID=1, DERIVED_HEIGHT=7.2)]
    lot = analyze(inputs(parcel, nbs, bld, zoning(), coverage_overlay(35)))
    intent = Intent(mode="buyer", project="addition", keep_existing_walls=True, proposed_rear_setback_m=8.0, proposed_storeys=3)
    files = [precedent(sys_id="1", reference_file="A0001/24TEY"), precedent(sys_id="2", reference_file="A0002/24TEY", outcome="refused")]
    return analyze_pathways(lot, intent, overlay_checked=True, precedents=files, precedent_radius_m=500)


# -- intent ------------------------------------------------------------------


def test_parse_intent_builds_an_intent_and_drops_invalid_numbers():
    parsed = m.ParsedIntent(project="addition", keep_existing_walls=True, proposed_storeys=3, proposed_height_m=-2.0, understood=["3 storeys"])
    client = FakeClient(parsed)
    out, intent = m.parse_intent(client, "add a third storey, keep the walls", "buyer")
    assert out.understood == ["3 storeys"]
    assert intent.project == "addition" and intent.keep_existing_walls is True and intent.proposed_storeys == 3
    assert intent.proposed_height_m is None  # negative height from the model is not a fact
    assert intent.text == "add a third storey, keep the walls"
    assert client.calls[0]["output_format"] is m.ParsedIntent
    assert client.calls[0]["output_config"] == {"effort": "low"}


def test_parse_intent_without_a_client_raises():
    with pytest.raises(m.ModelUnavailable):
        m.parse_intent(None, "anything", "buyer")


def test_parse_intent_refusal_raises():
    client = FakeClient(m.ParsedIntent(), stop_reason="refusal")
    with pytest.raises(m.ModelUnavailable):
        m.parse_intent(client, "anything", "buyer")


def test_merge_form_fields_win_over_the_model():
    parsed = Intent(project="new_build", proposed_storeys=2, proposed_height_m=9.0)
    details = Intent(mode="professional", proposed_storeys=3)
    merged = m.merge_intent(parsed, details, "text")
    assert merged.mode == "professional"
    assert merged.proposed_storeys == 3  # the form
    assert merged.proposed_height_m == 9.0  # the model filled the blank
    assert merged.project == "new_build"  # "unknown" in the form does not override
    assert merged.text == "text"


def test_merge_without_a_parse_keeps_the_details():
    merged = m.merge_intent(None, Intent(project="sever"), None)
    assert merged.project == "sever" and merged.sever_lot is True


# -- citations -----------------------------------------------------------------


def test_valid_citations_cover_gaps_cards_clauses_and_files(analysis):
    ids = m.valid_citations(analysis)
    assert "gap:rear_setback" in ids
    assert "card:keep-existing-walls-alteration" in ids
    assert any(c.startswith("clause:10.20.40.70") for c in ids)
    assert "file:A0001/24TEY" in ids


def test_check_citations_drops_uncited_and_unknown_paragraphs(analysis):
    draft = m.Draft(
        headline="The plan is short on the rear yard.",
        sections=[
            m.Section(heading="Gaps", paragraphs=[
                m.Paragraph(text="The rear yard is short.", citations=["gap:rear_setback"]),
                m.Paragraph(text="Made up rule.", citations=["clause:99.99"]),
                m.Paragraph(text="No source.", citations=[]),
            ]),
            m.Section(heading="Empty", paragraphs=[m.Paragraph(text="x", citations=["card:nope"])]),
        ],
        questions=["Ask about the rear yard."],
        unknowns=[],
    )
    out = m.check_citations(draft, analysis, "test-model")
    assert [s.heading for s in out.sections] == ["Gaps"]
    assert [p.text for p in out.sections[0].paragraphs] == ["The rear yard is short."]
    assert len(out.dropped) == 3
    assert out.model == "test-model" and out.questions == ["Ask about the rear yard."]


def test_write_answer_passes_the_compact_analysis(analysis):
    draft = m.Draft(headline="h", sections=[], questions=[], unknowns=[])
    client = FakeClient(draft)
    out = m.write_answer(client, analysis)
    assert out.sections == []
    sent = client.calls[0]["messages"][0]["content"]
    assert "card:keep-existing-walls-alteration" in sent
    assert "file:A0001/24TEY" in sent
    assert client.calls[0]["output_format"] is m.Draft


def test_compact_analysis_has_no_prose_only_fields(analysis):
    data = m._compact_analysis(analysis)
    assert data["short_standards"] == ["rear_setback"] or "rear_setback" in data["short_standards"]
    assert all(c["id"].startswith("card:") for c in data["pathways"])


# -- cache key -----------------------------------------------------------------


def test_request_hash_ignores_the_text_but_not_the_fields():
    a = Intent(project="addition", text="one wording")
    b = Intent(project="addition", text="other wording")
    c = Intent(project="addition", proposed_storeys=3)
    assert m.request_hash(a, "v1") == m.request_hash(b, "v1")
    assert m.request_hash(a, "v1") != m.request_hash(c, "v1")
    assert m.request_hash(a, "v1") != m.request_hash(a, "v2")


def test_make_client_is_none_without_a_key(monkeypatch):
    monkeypatch.setattr(m.settings, "llm_api_key", None)
    assert m.make_client() is None
    monkeypatch.setattr(m.settings, "llm_api_key", "")
    assert m.make_client() is None
