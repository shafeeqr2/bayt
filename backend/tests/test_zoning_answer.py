"""Phase 2 without the network: a fake client stands in for Claude.

Covers the intent merge (form fields win), invalid numbers from the model, the
citation check (unknown or missing citations drop the paragraph), the cache key
and the no-credentials path.
"""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.lot.analysis import analyze
from app.zoning import answer as m
from app.zoning.intent import Intent
from app.zoning.pathways import analyze_pathways
from app.zoning.precedents import Precedent
from tests.test_lot_analysis import block, coverage_overlay, house, inputs, zoning
from tests.test_zoning_precedents import precedent


class FakeClient:
    """A Backend that returns the queued parsed objects in order and records what it was asked."""

    model = "fake-model"

    def __init__(self, *outputs, fail: str | None = None):
        self.outputs = list(outputs)
        self.calls = []
        self.fail = fail

    def structured(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise m.ModelUnavailable(self.fail)
        return self.outputs.pop(0)


class FakeAnthropic:
    """Stands in for anthropic.Anthropic: `.messages.parse` returns a parsed object."""

    def __init__(self, parsed, stop_reason="end_turn"):
        self.messages = self
        self.parsed, self.stop_reason = parsed, stop_reason
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self.parsed, stop_reason=self.stop_reason)


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
    assert out.understood == ["Addition, main walls kept", "Storeys 3"]  # from the final fields, not the model's prose
    assert intent.project == "addition" and intent.keep_existing_walls is True and intent.proposed_storeys == 3
    assert intent.proposed_height_m is None  # negative height from the model is not a fact
    assert intent.text == "add a third storey, keep the walls"
    assert client.calls[0]["schema"] is m.ParsedIntent
    assert client.calls[0]["effort"] == "low"


def test_unclear_drops_lines_that_only_name_empty_fields():
    client = FakeClient(m.ParsedIntent(unclear=["proposed_units", "No information about proposed_gfa_m2", "Mentions a pool, which no field holds"]))
    parsed, _ = m.parse_intent(client, "a pool in the back", "buyer")
    assert parsed.unclear == ["Mentions a pool, which no field holds"]


def test_parse_intent_rules_fill_what_the_model_missed():
    client = FakeClient(m.ParsedIntent(project="addition", proposed_storeys=3))
    _, intent = m.parse_intent(client, "add a third storey 10.5 m high and leave a rear yard of 6.5 m", "buyer")
    assert intent.proposed_height_m == 10.5 and intent.proposed_rear_setback_m == 6.5


def test_rules_intent_without_a_model():
    parsed, intent = m.rules_intent("Tear down and rebuild, 3 storeys, 10 m high", "professional")
    assert intent.project == "new_build" and intent.keep_existing_walls is False and intent.proposed_storeys == 3
    assert parsed.understood[0] == "New building, main walls removed"


def test_backfill_takes_assignments_the_model_wrote_only_in_understood():
    parsed = m.ParsedIntent(
        proposed_storeys=3,
        understood=[
            "Third storey implies proposed_storeys = 2",  # the field is set, so the line does not override it
            "Rear yard implies proposed_rear_setback_m = 6.5",
            "Keep the house implies keep_existing_walls = true",
            "Units: proposed_units = many",  # not a number: ignored
        ],
    )
    m.backfill_from_understood(parsed)
    assert parsed.proposed_storeys == 3
    assert parsed.proposed_rear_setback_m == 6.5
    assert parsed.keep_existing_walls is True
    assert parsed.proposed_units is None


def test_parse_intent_without_a_client_raises():
    with pytest.raises(m.ModelUnavailable):
        m.parse_intent(None, "anything", "buyer")


def test_parse_intent_refusal_raises():
    client = FakeClient(fail="the model declined the request")
    with pytest.raises(m.ModelUnavailable):
        m.parse_intent(client, "anything", "buyer")


def test_anthropic_backend_uses_parse_and_handles_refusal():
    parsed = m.ParsedIntent(project="sever")
    backend = m.AnthropicBackend("k", "claude-opus-5-5", client=FakeAnthropic(parsed))
    out = backend.structured(system="s", user="u", schema=m.ParsedIntent, effort="low", max_tokens=100)
    assert out is parsed
    call = backend._client.calls[0]
    assert call["output_format"] is m.ParsedIntent and call["output_config"] == {"effort": "low"} and call["model"] == "claude-opus-5-5"
    refusing = m.AnthropicBackend("k", "claude-opus-5-5", client=FakeAnthropic(parsed, stop_reason="refusal"))
    with pytest.raises(m.ModelUnavailable):
        refusing.structured(system="s", user="u", schema=m.ParsedIntent, effort="low", max_tokens=100)


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
    sent = client.calls[0]["user"]
    assert "card:keep-existing-walls-alteration" in sent
    assert "file:A0001/24TEY" in sent
    assert client.calls[0]["schema"] is m.Draft


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


# -- providers -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "provider", "kind", "model"),
    [
        ("sk-ant-abc", "anthropic", "anthropic", "claude-opus-5-5"),
        ("sk-or-v1-abc", "openrouter", "openai", "nvidia/nemotron-3-super-120b-a12b"),
        ("nvapi-abc", "nvidia", "openai", "nvidia/nemotron-3-super-120b-a12b"),
    ],
)
def test_provider_from_key_prefix(monkeypatch, key, provider, kind, model):
    monkeypatch.setattr(m.settings, "llm_api_key", key)
    monkeypatch.setattr(m.settings, "llm_provider", "auto")
    monkeypatch.setattr(m.settings, "llm_base_url", None)
    monkeypatch.setattr(m.settings, "zoning_model", "")
    p = m.resolve_provider()
    assert p is not None and p.name == provider and p.kind == kind
    assert m.model_name(p) == model
    client = m.make_client()
    assert client is not None and client.model == model


def test_unknown_key_prefix_needs_an_explicit_provider(monkeypatch):
    monkeypatch.setattr(m.settings, "llm_api_key", "whatever")
    monkeypatch.setattr(m.settings, "llm_provider", "auto")
    assert m.resolve_provider() is None and m.make_client() is None
    monkeypatch.setattr(m.settings, "llm_provider", "openai")
    monkeypatch.setattr(m.settings, "llm_base_url", "https://example.test/v1")
    monkeypatch.setattr(m.settings, "zoning_model", "some/model")
    client = m.make_client()
    assert isinstance(client, m.OpenAIBackend) and client.model == "some/model"


def test_zoning_model_overrides_the_default(monkeypatch):
    monkeypatch.setattr(m.settings, "llm_api_key", "sk-or-v1-abc")
    monkeypatch.setattr(m.settings, "zoning_model", "nvidia/nemotron-3-ultra-550b-a55b")
    assert m.model_name() == "nvidia/nemotron-3-ultra-550b-a55b"


# -- OpenAI-style backend over a mock transport --------------------------------


def openai_backend(handler):
    return m.OpenAIBackend("sk-or-v1-x", "https://openrouter.ai/api/v1", "nvidia/nemotron-3-super-120b-a12b", "openrouter", transport=httpx.MockTransport(handler))


def test_openai_backend_sends_json_schema_and_parses_the_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "```json\n{\"project\": \"addition\", \"keep_existing_walls\": true, \"understood\": [\"keeps the walls\"], \"unclear\": []}\n```"}}]})

    out = openai_backend(handler).structured(system="sys", user="usr", schema=m.ParsedIntent, effort="low", max_tokens=500)
    assert isinstance(out, m.ParsedIntent) and out.project == "addition" and out.keep_existing_walls is True
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-or-v1-x"
    body = seen["body"]
    assert body["model"] == "nvidia/nemotron-3-super-120b-a12b" and body["max_tokens"] == 500
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["name"] == "ParsedIntent"
    assert "properties" in body["response_format"]["json_schema"]["schema"]
    assert body["messages"][0]["role"] == "system" and body["messages"][0]["content"].startswith("sys")
    assert body["messages"][1] == {"role": "user", "content": "usr"}


@pytest.mark.parametrize(
    ("status", "payload", "message"),
    [
        (401, {"error": "bad key"}, "rejected"),
        (429, {"error": "slow down"}, "rate limited"),
        (500, {"error": "boom"}, "HTTP 500"),
        (200, {"choices": [{"finish_reason": "stop", "message": {"content": "not json at all"}}]}, "does not fit"),
        (200, {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}, "out of output tokens"),
        (200, {"nope": 1}, "no structured output"),
    ],
)
def test_openai_backend_failures_become_model_unavailable(status, payload, message):
    backend = openai_backend(lambda request: httpx.Response(status, json=payload))
    with pytest.raises(m.ModelUnavailable, match=message):
        backend.structured(system="s", user="u", schema=m.ParsedIntent, effort="low", max_tokens=100)
