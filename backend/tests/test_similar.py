"""Similar homes without the network: the prompt, the clean-up, the embedding client, the rerank guard."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.similar import embed as em
from app.similar import profile as hp
from app.similar import service as sv
from app.zoning import answer as llm


def listing(**over):
    base = dict(
        id="L1", address="82 Renault Crescent", community="Humber Heights", city="Toronto", building_type="House",
        property_type="Single Family", ownership_type="Freehold", price=1_270_000, bedrooms_text="3 + 1", bedrooms_total=4,
        bathrooms=2, sqft_min=1100, sqft_max=1500, stories="1", lot_size="50 x 111 FT", parking_spaces=4, parking_type="Attached Garage",
        tax_annual=5512.0, maintenance_fee_monthly=None, description="Move-in ready bungalow on Renault Crescent with a separate side entrance.",
        rooms=[{"type": "Kitchen", "level": "Main level", "dimension": "4 m x 3 m"}], photos=[{"high": "https://cdn/h1.jpg", "medium": "https://cdn/m1.jpg"}],
        latitude=43.7, longitude=-79.5,
    )
    base.update(over)
    return SimpleNamespace(**base)


def view(**over):
    base = dict(score=7, pitch="Two kitchens and a side entrance at 82 Renault Crescent in Humber Heights.", signals=["two kitchens", "separate side entrance"], concerns=["suite not stated as legal"])
    base.update(over)
    return hp.PersonaView(**base)


def profile(**over):
    facts = hp.Facts(summary="A bungalow on Renault Crescent with a finished basement.", kitchen_finish=9, overall_condition=0)
    base = dict(facts=facts, first_time_buyer=view(score=12), investor=view(), flipper=view(score=0), builder=view())
    base.update(over)
    return hp.Profile(**base)


def test_listing_block_carries_the_price_against_the_area_median():
    text = hp._listing_block(listing(), (1_000_000.0, "community, 12 listings"))
    assert "Price: $1,270,000" in text
    assert "+27% against it" in text
    assert "Kitchen (Main level, 4 m x 3 m)" in text


def test_city_block_without_data_says_so():
    assert hp._city_block(None, None).startswith("City and lot data: none")


def test_city_block_reads_the_lot_analysis_verdicts():
    lot = {"parcel": {"corner_lot": False, "abuts_laneway": True, "irregular": False}, "zoning": {"as_of_right_units": 4, "low_rise_residential": True},
           "severance": {"verdict": "unlikely", "split_frontage_m": 7.6, "nearby_median_frontage_m": 12.1}, "garden_suite": {"verdict": "likely", "max_footprint_m2": 40, "rear_yard_depth_m": 20},
           "coverage": {"coverage_pct": 31.1, "max_coverage_pct": 33, "remaining_buildable_footprint_m2": 9.9}}
    text = hp._city_block(None, lot)
    assert "abuts a laneway True" in text and "Severance verdict: unlikely" in text and "Garden suite verdict: likely" in text


def test_clean_clamps_scores_and_scrubs_the_address_and_street():
    out = hp.clean(profile(), listing())
    assert out.first_time_buyer.score == 10 and out.flipper.score == 1
    assert out.facts.kitchen_finish == 5 and out.facts.overall_condition == 1
    assert "Renault" not in out.investor.pitch and "Humber Heights" not in out.investor.pitch
    assert out.investor.pitch == "Two kitchens and a side entrance at the property in the area."
    assert "Renault" not in out.facts.summary


def test_embedding_client_sends_all_texts_and_checks_the_dimension():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        n = len(seen["body"]["input"])
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [0.1] * em.EMBEDDING_DIM} for i in reversed(range(n))]})

    client = em.EmbeddingClient("sk-or-v1-x", "https://openrouter.ai/api/v1", "nvidia/nemotron-3.5-embed-1b:free", "openrouter", transport=httpx.MockTransport(handler))
    vectors = client.embed(["a", "b", "c"])
    assert seen["body"] == {"model": "nvidia/nemotron-3.5-embed-1b:free", "input": ["a", "b", "c"]}
    assert len(vectors) == 3 and len(vectors[0]) == em.EMBEDDING_DIM


def test_embedding_client_rejects_a_wrong_dimension():
    client = em.EmbeddingClient("k", "https://x/v1", "m", "openrouter", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1] * 8}]})
    ))
    with pytest.raises(llm.ModelUnavailable, match="8-dimensional"):
        client.embed(["a"])


def test_nim_embeddings_say_which_side_of_the_search():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0] * em.EMBEDDING_DIM}]})

    em.EmbeddingClient("nvapi-x", "https://integrate.api.nvidia.com/v1", "m", "nvidia", transport=httpx.MockTransport(handler)).embed(["a"])
    assert seen["body"]["input_type"] == "passage"


def test_embed_text_is_the_pitch_and_the_signals_never_the_address():
    row = SimpleNamespace(pitch="Two doors today.", signals=["two kitchens", "side entrance"])
    assert em.text_for(row) == "Two doors today.\nSignals: two kitchens; side entrance"


def rows():
    src = SimpleNamespace(persona="investor", score=7, pitch="Two doors.", signals=["two kitchens", "separate side entrance"], concerns=[])
    cands = [
        (listing(id="C1", address="1 A St"), SimpleNamespace(score=6, pitch="One door.", signals=["two kitchens", "finished basement"]), 0.12),
        (listing(id="C2", address="2 B St"), SimpleNamespace(score=8, pitch="Three doors.", signals=["triplex"]), 0.20),
    ]
    return src, cands


def test_rerank_drops_invented_ids_and_duplicates():
    src, cands = rows()
    answer = sv.Rerank(picks=[sv.Pick(id="C2", reason="three doors  like the source"), sv.Pick(id="NOPE", reason="x"), sv.Pick(id="C2", reason="again"), sv.Pick(id="C1", reason="two kitchens")], distinct="The source has a side entrance.")
    client = SimpleNamespace(model="m", structured=lambda **kw: answer)
    picks, distinct = sv.rerank(client, listing(), src, {"summary": "s"}, cands)
    assert picks == [("C2", "three doors like the source"), ("C1", "two kitchens")]
    assert distinct == "The source has a side entrance."


def test_rerank_prompt_names_the_buyer_and_prices_relative_to_the_source():
    src, cands = rows()
    text = sv.rerank_prompt(listing(), src, {"summary": "A bungalow."}, cands)
    assert text.startswith("Buyer: Investor:")
    assert "id C1: House, 3 + 1 bed, 2 bath, price +0% vs source; score 6/10" in text
    assert "summary: A bungalow." in text


def test_fallback_reasons_use_the_shared_signals():
    src, cands = rows()
    assert sv.fallback_reasons(src, cands) == [("C1", "Shares: two kitchens"), ("C2", "triplex")]


def test_request_hash_changes_with_the_candidate_set():
    src, cands = rows()
    a = sv._request_hash("investor", cands, "m")
    b = sv._request_hash("investor", cands[:1], "m")
    assert a != b and a == sv._request_hash("investor", cands, "m")


def test_default_models_follow_the_provider(monkeypatch):
    monkeypatch.setattr(hp.settings, "profile_model", "")
    monkeypatch.setattr(em.settings, "embed_model", "")
    monkeypatch.setattr(hp.settings, "llm_api_key", "sk-or-v1-x")
    assert hp.model_name() == "nvidia/nemotron-3.5-super-vl:free"
    assert em.model_name() == "nvidia/nemotron-3.5-embed-1b:free"
    monkeypatch.setattr(hp.settings, "llm_api_key", "sk-ant-x")
    assert em.make_client() is None  # Anthropic serves no embedding model


# -- steering: the typed change and the facet chips ---------------------------------------------------

from app.similar import steer as st  # noqa: E402


def test_parse_steering_cleans_the_text_and_checks_the_facets():
    s = st.parse("  bigger   backyard ", None)
    assert s.text == "bigger backyard" and s.facets == st.FACETS and s.off == () and s.is_default is False
    s = st.parse("", "lot, layout")
    assert s.text is None and s.facets == ("layout", "lot") and s.off == ("finish", "location", "money")
    assert st.parse(None, None).is_default
    assert st.parse("x" * 300, None).text == "x" * 200
    with pytest.raises(ValueError, match="unknown facet 'view'"):
        st.parse(None, "layout,view")
    with pytest.raises(ValueError, match="at least 1"):
        st.parse(None, "")


def test_a_facet_off_drops_its_filter():
    def words(s):
        return [w for _, w in sv.filter_tiers(listing(), s)]

    band = "price within 25% of $1,270,000"
    assert words(st.DEFAULT) == [[band, "within 5 km"], [band, "any distance"], ["any price", "any distance"]]
    assert words(st.parse(None, "layout,finish,lot,money")) == [[band, "any distance (location off)"], ["any price", "any distance (location off)"]]
    assert words(st.parse(None, "layout,location")) == [["any price (money off)", "within 5 km"], ["any price (money off)", "any distance"]]
    assert words(st.parse(None, "layout")) == [["any price (money off)", "any distance (location off)"]]
    assert len(sv.filter_tiers(listing(latitude=None), st.DEFAULT)) == 2  # no location: no radius tier


def test_rerank_prompt_carries_the_ask_and_the_facets():
    src, cands = rows()
    s = st.parse("bigger backyard", "layout,lot")
    text = sv.rerank_prompt(listing(), src, {"summary": "A bungalow."}, cands, s, ("A bungalow with a deep yard.", ["deep fenced yard"]))
    assert "What the buyer is asking for" in text and "pitch: A bungalow with a deep yard." in text
    assert "Compare on: layout (" in text and "Ignore: finish, location, money." in text
    assert 'The buyer asked for a change: "bigger backyard"' in text
    assert "lot 50 x 111 FT, 4 parking (Attached Garage)" in text
    plain = sv.rerank_prompt(listing(), src, None, cands)
    assert "Ignore:" not in plain and "asked for" not in plain and "Compare on: layout" in plain


def test_rewrite_scrubs_the_address_and_drops_empty_signals():
    src, _ = rows()
    answer = st.Rewrite(pitch="Two doors  at 82 Renault Crescent with a deep yard.", signals=["deep yard", " ", "garage"])
    client = SimpleNamespace(model="m", structured=lambda **kw: answer)
    pitch, signals = st.rewrite(client, listing(), src, None, "bigger backyard")
    assert pitch == "Two doors at the property with a deep yard." and signals == ["deep yard", "garage"]


def test_ask_retries_once_on_a_dropped_connection_and_not_on_a_rate_limit():
    calls = []

    def flaky(**kw):
        calls.append(1)
        if len(calls) == 1:
            raise llm.ModelUnavailable("the model call failed: ReadError")
        return st.Rewrite(pitch="ok", signals=[])

    out = st.ask(SimpleNamespace(structured=flaky), system="s", user="u", schema=st.Rewrite, max_tokens=5)
    assert isinstance(out, st.Rewrite) and out.pitch == "ok" and len(calls) == 2

    def limited(**kw):
        calls.append(1)
        raise llm.ModelUnavailable("the model is rate limited")

    calls.clear()
    with pytest.raises(llm.ModelUnavailable, match="rate limited"):
        st.ask(SimpleNamespace(structured=limited), system="s", user="u", schema=st.Rewrite, max_tokens=5)
    assert len(calls) == 1


def test_request_hash_changes_with_the_steering():
    src, cands = rows()
    a = sv._request_hash("investor", cands, "m")
    assert a == sv._request_hash("investor", cands, "m", st.DEFAULT)
    assert a != sv._request_hash("investor", cands, "m", st.parse("bigger yard", None))
    assert a != sv._request_hash("investor", cands, "m", st.parse(None, "layout"))
