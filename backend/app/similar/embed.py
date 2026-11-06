"""Embeddings for the persona pitches: one vector per (listing, persona), stored next to the pitch.

Nebius Token Factory, OpenRouter and NVIDIA NIM serve embedding models on the
OpenAI-style `POST {base_url}/embeddings`. Token Factory's model returns 4,096 floats
by default and takes a `dimensions` parameter, so it is asked for `EMBEDDING_DIM`. The vectors go in `listing_persona_profiles.embedding`
(pgvector, `EMBEDDING_DIM` floats) with the model's name, so a model change
re-embeds and a search never mixes two models' spaces.

The text embedded is the pitch plus its signals, never the address, so location
stays out of the vector (the search applies it as a filter instead). Several
pitches go in one request: the free listings on OpenRouter count requests per day,
not tokens, so the backfill embeds in batches of `BATCH` texts.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EMBEDDING_DIM, ListingPersonaProfile
from app.zoning import answer as llm

BATCH = 200  # texts per request; 50 listings x 4 personas
DEFAULT_MODELS = {
    "nebius": "Qwen/Qwen3-Embedding-8B",  # Token Factory serves no NVIDIA embedding model; the pitches are text either way
    "openrouter": "nvidia/nemotron-3.5-embed-1b:free",
    "nvidia": "nvidia/llama-3.2-nv-embedqa-1b-v2",
    "anthropic": "",  # Anthropic serves no embedding model
}


class EmbeddingClient:
    """`POST {base_url}/embeddings` with a list of texts; returns one vector per text, in order."""

    def __init__(self, api_key: str, base_url: str, model: str, provider: str = "openai", transport: httpx.BaseTransport | None = None):
        self.model = model
        self.provider = provider
        self._url = base_url.rstrip("/") + "/embeddings"
        headers = {"authorization": f"Bearer {api_key}", "content-type": "application/json"}
        if provider == "openrouter":
            headers["x-title"] = "Bayt similar homes"
        self._http = httpx.Client(headers=headers, timeout=120.0, transport=transport)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        body: dict[str, Any] = {"model": self.model, "input": texts}
        if self.provider == "nvidia":
            body["input_type"] = "passage"  # NIM's retrieval models need to know which side of the search this is
        if self.provider == "nebius" or (self.provider == "openrouter" and _matryoshka(self.model)):
            body["dimensions"] = EMBEDDING_DIM
        try:
            response = self._http.post(self._url, json=body)
        except httpx.HTTPError as exc:
            raise llm.ProviderDown(f"the embedding call failed: {exc.__class__.__name__}") from exc
        if response.status_code in (401, 403):
            raise llm.ProviderDown("the API key was rejected", sticky=True)
        if response.status_code == 429:
            raise llm.ProviderDown("the embedding model is rate limited; try again in a minute")
        if response.status_code == 402:  # no credit left on the account
            raise llm.ProviderDown(f"the embedding call failed: HTTP 402 {response.text[:120]}", sticky=True)
        if response.status_code in (404, 408) or response.status_code >= 500:
            raise llm.ProviderDown(f"the embedding call failed: HTTP {response.status_code} {response.text[:120]}")
        if response.status_code >= 400:
            raise llm.ModelUnavailable(f"the embedding call failed: HTTP {response.status_code} {response.text[:120]}")
        try:
            rows = sorted(response.json()["data"], key=lambda d: d["index"])
            vectors = [[float(x) for x in r["embedding"]] for r in rows]
        except (ValueError, KeyError, TypeError) as exc:
            raise llm.ModelUnavailable("the embedding model returned no vectors") from exc
        if len(vectors) != len(texts):
            raise llm.ModelUnavailable(f"the embedding model returned {len(vectors)} vectors for {len(texts)} texts")
        if _matryoshka(self.model):
            # A host that ignores `dimensions` returns the full vector. For a Matryoshka model the
            # first EMBEDDING_DIM floats, renormalised, are the vector `dimensions` would have given.
            vectors = [_shorten(v) if len(v) > EMBEDDING_DIM else v for v in vectors]
        for v in vectors:
            if len(v) != EMBEDDING_DIM:
                raise llm.ModelUnavailable(f"{self.model} returns {len(v)}-dimensional vectors; the table holds {EMBEDDING_DIM}")
        return vectors


def _matryoshka(model: str) -> bool:
    """Qwen3-Embedding is trained so that a prefix of the vector is itself a usable embedding."""
    return "qwen3-embedding" in model.lower()


def _shorten(vector: list[float]) -> list[float]:
    head = vector[:EMBEDDING_DIM]
    norm = sum(x * x for x in head) ** 0.5
    return [x / norm for x in head] if norm else head


class FallbackEmbeddingClient:
    """Tries the first provider; on `ProviderDown` asks the second one for the same embedding model.

    `model` stays the first provider's name, which labels the stored vectors: the fallback serves
    the same weights, so the vectors live in the same space and nothing is re-embedded.
    """

    def __init__(self, primary: EmbeddingClient, secondary: EmbeddingClient) -> None:
        self.primary = primary
        self.secondary = secondary
        self.model = primary.model
        self.provider = primary.provider

    def embed(self, texts: list[str]) -> list[list[float]]:
        if llm.primary_paused():
            llm.count_fallback()
            return self.secondary.embed(texts)
        try:
            return self.primary.embed(texts)
        except llm.ProviderDown as exc:
            llm.note_fallback(exc, "this embedding")
            return self.secondary.embed(texts)


def model_name() -> str:
    if settings.embed_model:
        return settings.embed_model
    p = llm.resolve_provider()
    return DEFAULT_MODELS.get(p.name, "") if p else ""


def make_client() -> EmbeddingClient | FallbackEmbeddingClient | None:
    p = llm.resolve_provider()
    model = model_name()
    if p is None or not p.base_url or not model:
        return None
    primary = EmbeddingClient(settings.llm_api_key or "", p.base_url, model, p.name)
    f = llm.resolve_fallback(p)
    if f is None or not f.base_url:
        return primary
    secondary = EmbeddingClient(settings.llm_fallback_api_key or "", f.base_url, llm.fallback_model(model, f.name), f.name)
    return FallbackEmbeddingClient(primary, secondary)


def text_for(row: ListingPersonaProfile) -> str:
    signals = "; ".join(row.signals or [])
    return row.pitch + (f"\nSignals: {signals}" if signals else "")


def pending(session: Session, model: str, *, listing_id: str | None = None, limit: int | None = None) -> list[ListingPersonaProfile]:
    """Persona rows with no embedding, or one from another model."""
    stmt = select(ListingPersonaProfile).where(
        or_(ListingPersonaProfile.embedding.is_(None), ListingPersonaProfile.embed_model != model)
    )
    if listing_id:
        stmt = stmt.where(ListingPersonaProfile.listing_id == listing_id)
    stmt = stmt.order_by(ListingPersonaProfile.listing_id, ListingPersonaProfile.persona)
    if limit:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


def embed_rows(session: Session, rows: list[ListingPersonaProfile], client: EmbeddingClient) -> int:
    """Embed `rows` in batches and store the vectors. Returns how many rows were embedded."""
    done = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        vectors = client.embed([text_for(r) for r in chunk])
        for r, v in zip(chunk, vectors):
            r.embedding = v
            r.embed_model = client.model
        session.commit()
        done += len(chunk)
    return done


def embed_listing(session: Session, listing_id: str, client: EmbeddingClient | None = None) -> int:
    """Embed the persona rows of one listing that lack a current vector. Silently does nothing without a client."""
    client = client or make_client()
    if client is None:
        return 0
    rows = pending(session, client.model, listing_id=listing_id)
    return embed_rows(session, rows, client) if rows else 0
