"""Similar homes for one listing and one persona: hard filters, nearest pitches, one rerank call.

A tap on "more like this" runs:

1. Hard filters. The same persona's rows with a current embedding, inside a price
   band around the source and within `RADIUS_M` of it. Price and location are
   filters, not part of the vector, so they never dominate the comparison. When
   the band and the radius leave fewer than `MIN_CANDIDATES`, the radius is dropped,
   then the band, and the answer says so.
2. Nearest neighbours. Cosine distance between the source's persona pitch and the
   candidates', `CANDIDATES` of them. At a few thousand listings this is an exact
   scan in a few milliseconds.
3. Rerank. One model call reads the source's pitch and signals and the candidates'
   and returns the best `RESULTS` in order with one reason line each, in the
   persona's words, plus one line on what makes the source house distinct. Ids
   the model invents are dropped. Without a model (or when it fails) the answer
   is the nearest-neighbour order with reasons built from the shared signals.

The buyer can steer the answer (`steer`): a typed change rewrites the source pitch
and the search runs from the rewritten text, and 5 facet chips say what to compare
on. Location and money are also the 2 hard filters, so a chip off drops its filter.

The reranked answer is cached in `similar_results` for `CACHE_TTL`, keyed by the
persona, the steering and the candidate set, so a new neighbour (the backfill
writing more profiles) makes a new answer and a repeat tap costs nothing. A
steering rewrite and its vector are cached the same way.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Listing, ListingPersonaProfile, ListingProfile, SimilarResult
from app.schemas import ListingSummary
from app.similar import embed as embedder
from app.similar import profile as hp
from app.similar import steer as steering_mod
from app.similar.steer import DEFAULT, Steering, ask, facet_block
from app.strategy import search as strategy
from app.strategy.finance import Financing
from app.zoning import answer as llm

PROMPT_VERSION = 1
CANDIDATES = 30
RESULTS = 8
MIN_CANDIDATES = 5
PRICE_BAND = 0.25
RADIUS_M = 5000
CACHE_TTL = timedelta(hours=24)
MAX_TOKENS = 1500
REASON_WORDS = 22


class NoProfile(Exception):
    """The source listing has no searchable profile for this persona yet."""


# -- response shapes ---------------------------------------------------------------------------------


class SimilarHome(BaseModel):
    listing: ListingSummary
    score: int = Field(description="This listing's score for the persona, 1 to 10")
    reason: str = Field(description="One line on what it shares with the source, in the persona's words")
    distance: float = Field(description="Cosine distance between the two pitches; smaller is closer")
    signals: list[str]


class SimilarHomes(BaseModel):
    listing_id: str
    persona: str
    label: str
    source_score: int | None
    source_signals: list[str]
    distinct: str | None = Field(None, description="One line on what sets the source house apart from its neighbours")
    items: list[SimilarHome]
    candidates: int = Field(description="How many listings passed the filters and went to the rerank")
    filters: list[str] = Field(description="The filters applied, in plain words, including which were dropped")
    model: str | None
    reranked: bool
    cached: bool
    note: str | None = Field(None, description="Why the list is empty or not reranked")
    steer: str | None = Field(None, description="The buyer's typed change, as applied")
    facets: list[str] = Field(default_factory=lambda: list(steering_mod.FACETS), description="The facets the comparison used")
    target: str | None = Field(None, description="With `steer`: the rewritten pitch the search ran from")
    steered: bool = Field(False, description="True when the search ran from the rewritten pitch")


# -- 1 + 2: filters and nearest neighbours -----------------------------------------------------------


def _summary(listing: Listing) -> ListingSummary:
    cover = listing.photos[0]["high"] if listing.photos else None
    return ListingSummary.model_validate(listing, from_attributes=True).model_copy(
        update={"cover_photo": cover, "investment": strategy.summary(listing.investment_estimate, listing.price, Financing())}
    )


def filter_tiers(listing: Listing, steering: Steering = DEFAULT) -> list[tuple[list[Any], list[str]]]:
    """The filter sets to try, strictest first, each with its plain words. A facet turned off drops its filter."""
    lo, hi = int(listing.price * (1 - PRICE_BAND)), int(listing.price * (1 + PRICE_BAND))
    price = Listing.price.between(lo, hi)
    located = listing.latitude is not None and listing.longitude is not None
    near = (
        func.ST_DistanceSphere(
            func.ST_MakePoint(Listing.longitude, Listing.latitude), func.ST_MakePoint(listing.longitude, listing.latitude)
        )
        <= RADIUS_M
    )
    use_price, use_near = "money" in steering.facets, "location" in steering.facets and located
    price_words = f"price within {PRICE_BAND:.0%} of ${listing.price:,}" if use_price else "any price" + ("" if "money" in steering.facets else " (money off)")
    near_words = f"within {RADIUS_M / 1000:.0f} km" if use_near else "any distance" + ("" if "location" in steering.facets else " (location off)")
    tiers: list[tuple[list[Any], list[str]]] = []
    if use_price and use_near:
        tiers.append(([price, near], [price_words, near_words]))
    if use_price:
        tiers.append(([price], [price_words, "any distance" if use_near else near_words]))
    elif use_near:
        tiers.append(([near], [price_words, near_words]))
    tiers.append(([], ["any price" if use_price else price_words, "any distance" if use_near else near_words]))
    return tiers


def candidates(
    session: Session, listing: Listing, source: ListingPersonaProfile, *, vector: list[float] | None = None, steering: Steering = DEFAULT
) -> tuple[list[tuple[Listing, ListingPersonaProfile, float]], list[str]]:
    """The nearest `CANDIDATES` persona rows to `vector` (default: the source's own) inside the filters, and the filters that held."""
    distance = ListingPersonaProfile.embedding.cosine_distance(vector if vector is not None else source.embedding).label("distance")
    for where, words in filter_tiers(listing, steering):
        stmt = (
            select(Listing, ListingPersonaProfile, distance)
            .join(ListingPersonaProfile, ListingPersonaProfile.listing_id == Listing.id)
            .where(
                ListingPersonaProfile.persona == source.persona,
                ListingPersonaProfile.embedding.is_not(None),
                ListingPersonaProfile.embed_model == source.embed_model,
                ListingPersonaProfile.listing_id != listing.id,
                *where,
            )
            .order_by(distance)
            .limit(CANDIDATES)
        )
        rows = [(l, p, float(d)) for l, p, d in session.execute(stmt)]
        if len(rows) >= MIN_CANDIDATES:
            return rows, words
    return rows, words


# -- 3: the rerank ----------------------------------------------------------------------------------


class Pick(BaseModel):
    id: str = Field(description="The candidate's id, copied exactly")
    reason: str = Field(description=f"At most {REASON_WORDS} words: the facts it shares with the source house that this persona cares about")


class Rerank(BaseModel):
    picks: list[Pick] = Field(description=f"The best {RESULTS} candidates for this persona, most similar first; fewer when fewer fit")
    distinct: str = Field(description="One sentence: what the source house has that most of these candidates do not, for this persona")


RERANK_SYSTEM = """You rank houses for sale by how similar they are to one source house, for one kind of buyer.

Similar means: the same reasons this buyer would want the source house also apply to the candidate. A first-time buyer compares condition, layout, cost and parking; an investor compares doors, rent, yield and suites; a flipper compares the spread and the work; a builder compares the lot and the zoning. Looks, address and exact price are not the point: the candidates already sit in the same price band and area.

Rules:
- Pick from the candidates only, by their ids, copied exactly. Never invent an id.
- Order by similarity for this buyer, best first. Leave out a candidate that shares little with the source.
- Each reason names facts the candidate shares with the source (or one thing it does better), in at most %d words, in plain words. No marketing words.
- Compare only on the facets listed; when the buyer asked for a change, candidates that deliver it come first and their reason says how.
- `distinct` is one sentence on what the real source house has that most candidates do not. It is about the source house as it is, never about the asked-for change.""" % REASON_WORDS


def _lot(l: Listing) -> str:
    # The pitches rarely mention the lot or the parking; a typed ask often does ("bigger backyard", "a garage").
    parking = f"{l.parking_spaces} parking" if l.parking_spaces is not None else "parking ?"
    return f"lot {l.lot_size or '?'}, {parking}" + (f" ({l.parking_type})" if l.parking_type else "")


def _pct(price: int, base: int) -> str:
    return f"{(price - base) / base * 100:+.0f}%" if base else "?"


def rerank_prompt(
    listing: Listing, source: ListingPersonaProfile, facts: dict[str, Any] | None, rows: list[tuple[Listing, ListingPersonaProfile, float]],
    steering: Steering = DEFAULT, target: tuple[str, list[str]] | None = None,
) -> str:
    def one(l: Listing, p: ListingPersonaProfile) -> str:
        return (
            f"- id {l.id}: {l.building_type or '?'}, {l.bedrooms_text or l.bedrooms_total or '?'} bed, {l.bathrooms or '?'} bath, price {_pct(l.price, listing.price)} vs source; score {p.score}/10; {_lot(l)}\n"
            f"  pitch: {p.pitch}\n  signals: {'; '.join(p.signals or [])}"
        )

    rubric = hp.RUBRICS[source.persona].split("\n", 1)[0]
    head = (
        f"Buyer: {rubric}\n\n"
        f"Source house: {listing.building_type or '?'}, {listing.bedrooms_text or listing.bedrooms_total or '?'} bed, {listing.bathrooms or '?'} bath; score {source.score}/10; {_lot(listing)}\n"
        f"  summary: {(facts or {}).get('summary') or ''}\n  pitch: {source.pitch}\n  signals: {'; '.join(source.signals or [])}\n  concerns: {'; '.join(source.concerns or [])}\n\n"
    )
    if target is not None:
        head += f"What the buyer is asking for (the source with the change applied):\n  pitch: {target[0]}\n  signals: {'; '.join(target[1])}\n\n"
    head += facet_block(steering) + f"\n\nCandidates ({len(rows)}), nearest first by the pitch:\n"
    return head + "\n".join(one(l, p) for l, p, _ in rows) + f"\n\nPick the best {RESULTS} for this buyer, in order, with a reason each."


def fallback_reasons(source: ListingPersonaProfile, rows: list[tuple[Listing, ListingPersonaProfile, float]]) -> list[tuple[str, str]]:
    """Without a model: the nearest-neighbour order, with the shared signals as the reason."""
    mine = {s.lower() for s in source.signals or []}
    out = []
    for l, p, _ in rows[:RESULTS]:
        shared = [s for s in (p.signals or []) if s.lower() in mine]
        words = shared[:3] or list(p.signals or [])[:2]
        out.append((l.id, ("Shares: " if shared else "") + ", ".join(words) if words else "Close in the persona's terms"))
    return out


def rerank(
    client: llm.Backend, listing: Listing, source: ListingPersonaProfile, facts: dict[str, Any] | None, rows: list[tuple[Listing, ListingPersonaProfile, float]],
    steering: Steering = DEFAULT, target: tuple[str, list[str]] | None = None,
) -> tuple[list[tuple[str, str]], str | None]:
    """The model's order and reasons, with invented ids dropped; raises ModelUnavailable on failure."""
    user = rerank_prompt(listing, source, facts, rows, steering, target)
    out = ask(client, system=RERANK_SYSTEM, user=user, schema=Rerank, max_tokens=MAX_TOKENS)
    assert isinstance(out, Rerank)
    known = {l.id for l, _, _ in rows}
    picks: list[tuple[str, str]] = []
    seen: set[str] = set()
    for p in out.picks:
        pid = p.id.strip()
        if pid in known and pid not in seen:
            seen.add(pid)
            picks.append((pid, " ".join(p.reason.split())))
    return picks[:RESULTS], " ".join(out.distinct.split()) or None


# -- the answer ---------------------------------------------------------------------------------------


def make_client() -> llm.Backend | None:
    # The profile model is a text-and-vision model that answers in under a second; the rerank is a short text call.
    return llm.make_client(hp.model_name() or None, json_mode="object")


def _request_hash(persona: str, rows: list[tuple[Listing, ListingPersonaProfile, float]], model: str, steering: Steering = DEFAULT) -> str:
    key = json.dumps({"persona": persona, "ids": [l.id for l, _, _ in rows], "v": [PROMPT_VERSION, hp.PROMPT_VERSION], "model": model, "steer": steering.key()})
    return hashlib.sha256(key.encode()).hexdigest()


def _rewrite_hash(source: ListingPersonaProfile, text: str, model: str, embed_model: str) -> str:
    key = json.dumps({"rewrite": text, "persona": source.persona, "pitch": source.pitch, "v": PROMPT_VERSION, "model": model, "embed": embed_model})
    return hashlib.sha256(key.encode()).hexdigest()


def _cached(session: Session, listing_id: str, key: str) -> SimilarResult | None:
    hit = session.get(SimilarResult, (listing_id, key))
    return hit if hit is not None and datetime.now(timezone.utc) - hit.created_at < CACHE_TTL else None


def _store(session: Session, listing_id: str, key: str, model: str, result: dict[str, Any]) -> None:
    hit = session.get(SimilarResult, (listing_id, key)) or SimilarResult(listing_id=listing_id, request_hash=key)
    session.add(hit)
    hit.model, hit.result, hit.created_at = model, result, datetime.now(timezone.utc)
    session.commit()


def steer_vector(
    session: Session, client: llm.Backend, listing: Listing, source: ListingPersonaProfile, facts: dict[str, Any] | None, text: str,
    embed_client: embedder.EmbeddingClient | None = None,
) -> tuple[tuple[str, list[str]], list[float]]:
    """The rewritten pitch, its signals and its vector for a typed change; cached for `CACHE_TTL`. Raises ModelUnavailable."""
    embed_client = embed_client or embedder.make_client()
    if embed_client is None:
        raise llm.ModelUnavailable("no embedding model configured")
    if source.embed_model and embed_client.model != source.embed_model:
        raise llm.ModelUnavailable(f"the embedding model changed to {embed_client.model}; run the profiles job to re-embed")
    key = _rewrite_hash(source, text, client.model, embed_client.model)
    hit = _cached(session, listing.id, key)
    if hit is not None and hit.result.get("vector"):
        return (hit.result["pitch"], list(hit.result.get("signals") or [])), [float(x) for x in hit.result["vector"]]
    pitch, signals = steering_mod.rewrite(client, listing, source, facts, text)
    vector = embed_client.embed([pitch + (f"\nSignals: {'; '.join(signals)}" if signals else "")])[0]
    _store(session, listing.id, key, client.model, {"pitch": pitch, "signals": signals, "vector": vector})
    return (pitch, signals), vector


def similar(
    session: Session, listing: Listing, persona: str, *, client: llm.Backend | None = None, use_model: bool = True, limit: int = RESULTS,
    steering: Steering = DEFAULT, embed_client: embedder.EmbeddingClient | None = None,
) -> SimilarHomes:
    if persona not in hp.PERSONAS:
        raise ValueError(f"unknown persona {persona}")
    source = session.get(ListingPersonaProfile, (listing.id, persona))
    label = hp.PERSONA_LABELS[persona]
    base: dict[str, Any] = dict(listing_id=listing.id, persona=persona, label=label, steer=steering.text, facets=list(steering.facets))
    if source is None or source.embedding is None:
        row = session.get(ListingProfile, listing.id)
        note = "the profile is not written yet" if source is None else "the pitch is not embedded yet"
        if row is not None and row.facts is None and row.note:
            note = f"the profile could not be written: {row.note}"
        return SimilarHomes(**base, source_score=None, source_signals=[], items=[], candidates=0, filters=[], model=None, reranked=False, cached=False, note=note)
    base.update(source_score=source.score, source_signals=list(source.signals or []))
    facts = (session.get(ListingProfile, listing.id) or ListingProfile()).facts
    client = client or (make_client() if use_model else None)
    model = client.model if client else ""
    notes: list[str] = []

    # The typed change: rewrite the pitch and search from it. Without a model the ask still reaches nothing, so say so.
    target: tuple[str, list[str]] | None = None
    vector: list[float] | None = None
    if steering.text:
        if client is None:
            notes.append("not steered: no model configured" if use_model else "not steered: the model is off")
        else:
            try:
                target, vector = steer_vector(session, client, listing, source, facts, steering.text, embed_client)
            except llm.ModelUnavailable as exc:
                notes.append(f"not steered: {exc}; the ask went to the ranking only")

    rows, filters = candidates(session, listing, source, vector=vector, steering=steering)
    if not rows:
        return SimilarHomes(**base, items=[], candidates=0, filters=filters, model=None, reranked=False, cached=False, note="no other listing has a profile for this persona yet")

    picks: list[tuple[str, str]] | None = None
    distinct: str | None = None
    reranked = cached = False
    key = _request_hash(persona, rows, model, steering)
    if client is not None:
        hit = _cached(session, listing.id, key)
        if hit is not None and "picks" in hit.result:
            picks = [(p["id"], p["reason"]) for p in hit.result["picks"]]
            distinct = hit.result.get("distinct")
            reranked, cached = True, True
        else:
            try:
                picks, distinct = rerank(client, listing, source, facts, rows, steering, target)
                reranked = len(picks) >= 1
                if reranked:
                    _store(session, listing.id, key, model, {"picks": [{"id": i, "reason": r} for i, r in picks], "distinct": distinct})
                else:
                    notes.append("the model picked none of the candidates; showing the nearest instead")
            except llm.ModelUnavailable as exc:
                notes.append(f"not reranked: {exc}")
    elif use_model:
        notes.append("not reranked: no model configured")
    if not reranked:
        picks = fallback_reasons(source, rows)

    by_id = {l.id: (l, p, d) for l, p, d in rows}
    items = [
        SimilarHome(listing=_summary(l), score=p.score, reason=reason, distance=round(d, 4), signals=list(p.signals or []))
        for pid, reason in (picks or [])[:limit]
        for l, p, d in [by_id[pid]]
    ]
    return SimilarHomes(
        **base, distinct=distinct, items=items, candidates=len(rows), filters=filters, model=model or None, reranked=reranked, cached=cached,
        note="; ".join(notes) or None, target=target[0] if target else None, steered=target is not None,
    )
