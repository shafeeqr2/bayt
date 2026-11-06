"""The fallback model provider: Token Factory first, OpenRouter only when the provider itself fails."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.similar import embed as em
from app.zoning import answer as llm


class Out(BaseModel):
    ok: bool


GOOD = {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok": true}'}}]}


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(llm, "_paused_until", 0.0)
    monkeypatch.setattr(llm, "_fallback_calls", 0)
    monkeypatch.setattr(llm, "_last_reason", None)
    monkeypatch.setattr(llm.settings, "llm_api_key", "v1.primary")
    monkeypatch.setattr(llm.settings, "llm_provider", "auto")
    monkeypatch.setattr(llm.settings, "llm_base_url", None)
    monkeypatch.setattr(llm.settings, "llm_fallback_api_key", "sk-or-v1-second")
    monkeypatch.setattr(llm.settings, "llm_fallback_provider", "auto")
    monkeypatch.setattr(llm.settings, "zoning_model", "")
    monkeypatch.setattr(llm.settings, "embed_model", "")


def pair(primary_handler, secondary_handler):
    seen = {"primary": [], "secondary": []}

    def wrap(name, handler):
        def inner(request: httpx.Request) -> httpx.Response:
            seen[name].append(json.loads(request.content))
            return handler(request)

        return httpx.MockTransport(inner)

    primary = llm.OpenAIBackend("v1.x", "https://api.tokenfactory.nebius.com/v1", "nvidia/Nemotron-3.5-Super-VL", "nebius", transport=wrap("primary", primary_handler))
    secondary = llm.OpenAIBackend("sk-or-x", "https://openrouter.ai/api/v1", "nvidia/nemotron-3.5-super-vl", "openrouter", transport=wrap("secondary", secondary_handler))
    return llm.FallbackBackend(primary, secondary), seen


def call(client):
    return client.structured(system="s", user="u", schema=Out, effort="low", max_tokens=50)


def test_fallback_is_resolved_from_the_second_key(monkeypatch):
    primary = llm.resolve_provider()
    assert primary.name == "nebius" and llm.resolve_fallback(primary).name == "openrouter"
    monkeypatch.setattr(llm.settings, "llm_fallback_api_key", None)
    assert llm.resolve_fallback(primary) is None
    monkeypatch.setattr(llm.settings, "llm_fallback_api_key", "v1.another-nebius-key")
    assert llm.resolve_fallback(primary) is None  # the same provider is not a fallback
    monkeypatch.setattr(llm.settings, "llm_fallback_api_key", "sk-ant-x")
    assert llm.resolve_fallback(primary) is None  # only OpenAI-style providers


def test_make_client_wraps_both_and_keeps_the_primary_model_name():
    client = llm.make_client("nvidia/Nemotron-3.5-Super-VL")
    assert isinstance(client, llm.FallbackBackend)
    assert client.model == "nvidia/Nemotron-3.5-Super-VL"  # keys the caches; unchanged by the fallback
    assert client.primary.provider == "nebius" and client.secondary.provider == "openrouter"
    assert client.secondary.model == "nvidia/nemotron-3.5-super-vl"


def test_no_fallback_key_means_a_bare_backend(monkeypatch):
    monkeypatch.setattr(llm.settings, "llm_fallback_api_key", "")
    assert isinstance(llm.make_client(), llm.OpenAIBackend)


def test_primary_answers_and_the_fallback_is_never_called():
    client, seen = pair(lambda r: httpx.Response(200, json=GOOD), lambda r: httpx.Response(500))
    assert call(client).ok is True
    assert len(seen["primary"]) == 1 and seen["secondary"] == []
    assert llm.provider_stats()["fallback_calls"] == 0


def test_out_of_credit_goes_to_the_fallback_and_pauses_the_primary():
    client, seen = pair(lambda r: httpx.Response(402, json={"error": {"type": "insufficient_quota"}}), lambda r: httpx.Response(200, json=GOOD))
    assert call(client).ok is True and call(client).ok is True
    assert len(seen["primary"]) == 1  # the 2nd call skipped the paused provider
    assert len(seen["secondary"]) == 2
    assert seen["secondary"][0]["model"] == "nvidia/nemotron-3.5-super-vl" and seen["secondary"][0]["reasoning"] == {"enabled": False}
    stats = llm.provider_stats()
    assert stats == {"primary": "nebius", "fallback": "openrouter", "fallback_calls": 2, "primary_paused": True, "last_fallback_reason": stats["last_fallback_reason"]}
    assert "HTTP 402" in stats["last_fallback_reason"]


def test_a_transient_failure_falls_back_once_without_a_pause():
    answers = iter([httpx.Response(503), httpx.Response(200, json=GOOD)])
    client, seen = pair(lambda r: next(answers), lambda r: httpx.Response(200, json=GOOD))
    assert call(client).ok is True and call(client).ok is True
    assert len(seen["primary"]) == 2 and len(seen["secondary"]) == 1
    assert llm.provider_stats()["primary_paused"] is False


def test_a_bad_model_answer_does_not_go_to_the_fallback():
    bad = {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]}
    client, seen = pair(lambda r: httpx.Response(200, json=bad), lambda r: httpx.Response(200, json=GOOD))
    with pytest.raises(llm.ModelUnavailable, match="does not fit"):
        call(client)
    assert seen["secondary"] == []


def test_both_down_raises_the_fallback_error():
    client, _ = pair(lambda r: httpx.Response(402), lambda r: httpx.Response(401))
    with pytest.raises(llm.ModelUnavailable, match="rejected"):
        call(client)


def test_embedding_fallback_asks_for_the_same_model_and_size():
    seen = {}

    def second(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        full = [3.0, 4.0] + [0.0] * (2 * em.EMBEDDING_DIM - 2)  # a host that ignored `dimensions`
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": full}]})

    primary = em.EmbeddingClient("v1.x", "https://api.tokenfactory.nebius.com/v1", "Qwen/Qwen3-Embedding-8B", "nebius", transport=httpx.MockTransport(lambda r: httpx.Response(402)))
    secondary = em.EmbeddingClient("sk-or-x", "https://openrouter.ai/api/v1", "qwen/qwen3-embedding-8b", "openrouter", transport=httpx.MockTransport(second))
    client = em.FallbackEmbeddingClient(primary, secondary)
    vectors = client.embed(["a"])
    assert client.model == "Qwen/Qwen3-Embedding-8B"  # labels the stored vectors; unchanged
    assert seen["body"] == {"model": "qwen/qwen3-embedding-8b", "input": ["a"], "dimensions": em.EMBEDDING_DIM}
    assert len(vectors[0]) == em.EMBEDDING_DIM and vectors[0][:2] == [0.6, 0.8]  # cut to size and renormalised
    assert llm.provider_stats()["fallback_calls"] == 1


def test_embed_make_client_wraps_both():
    client = em.make_client()
    assert isinstance(client, em.FallbackEmbeddingClient)
    assert client.model == "Qwen/Qwen3-Embedding-8B" and client.secondary.model == "qwen/qwen3-embedding-8b"
