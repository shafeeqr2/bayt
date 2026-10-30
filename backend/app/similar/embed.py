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
        if self.provider == "nebius":
            body["dimensions"] = EMBEDDING_DIM
        try:
            response = self._http.post(self._url, json=body)
        except httpx.HTTPError as exc:
            raise llm.ModelUnavailable(f"the embedding call failed: {exc.__class__.__name__}") from exc
        if response.status_code in (401, 403):
            raise llm.ModelUnavailable("the API key was rejected")
        if response.status_code == 429:
            raise llm.ModelUnavailable("the embedding model is rate limited; try again in a minute")
        if response.status_code >= 400:
            raise llm.ModelUnavailable(f"the embedding call failed: HTTP {response.status_code} {response.text[:120]}")
        try:
            rows = sorted(response.json()["data"], key=lambda d: d["index"])
            vectors = [[float(x) for x in r["embedding"]] for r in rows]
        except (ValueError, KeyError, TypeError) as exc:
            raise llm.ModelUnavailable("the embedding model returned no vectors") from exc
        if len(vectors) != len(texts):
            raise llm.ModelUnavailable(f"the embedding model returned {len(vectors)} vectors for {len(texts)} texts")
        for v in vectors:
            if len(v) != EMBEDDING_DIM:
                raise llm.ModelUnavailable(f"{self.model} returns {len(v)}-dimensional vectors; the table holds {EMBEDDING_DIM}")
        return vectors


def model_name() -> str:
    if settings.embed_model:
        return settings.embed_model
    p = llm.resolve_provider()
    return DEFAULT_MODELS.get(p.name, "") if p else ""


def make_client() -> EmbeddingClient | None:
    p = llm.resolve_provider()
    model = model_name()
    if p is None or not p.base_url or not model:
        return None
    return EmbeddingClient(settings.llm_api_key or "", p.base_url, model, p.name)


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
