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

The reranked answer is cached in `similar_results` for `CACHE_TTL`, keyed by the
persona and the candidate set, so a new neighbour (the backfill writing more
profiles) makes a new answer and a repeat tap costs nothing.
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
from app.similar import profile as hp
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
RETRY_ONCE = ("HTTP 502", "HTTP 503", "HTTP 504", "ReadError", "ReadTimeout", "RemoteProtocolError")  # the free hosts drop a call now and then
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


# -- 1 + 2: filters and nearest neighbours -----------------------------------------------------------


def _summary(listing: Listing) -> ListingSummary:
    cover = listing.photos[0]["high"] if listing.photos else None
    return ListingSummary.model_validate(listing, from_attributes=True).model_copy(
        update={"cover_photo": cover, "investment": strategy.summary(listing.investment_estimate, listing.price, Financing())}
    )


def candidates(session: Session, listing: Listing, source: ListingPersonaProfile) -> tuple[list[tuple[Listing, ListingPersonaProfile, float]], list[str]]:
    """The nearest `CANDIDATES` persona rows inside the filters, and the filters that held."""
    lo, hi = int(listing.price * (1 - PRICE_BAND)), int(listing.price * (1 + PRICE_BAND))
    price = Listing.price.between(lo, hi)
    located = listing.latitude is not None and listing.longitude is not None
    near = (
        func.ST_DistanceSphere(
            func.ST_MakePoint(Listing.longitude, Listing.latitude), func.ST_MakePoint(listing.longitude, listing.latitude)
        )
        <= RADIUS_M
    )
    tiers: list[tuple[list[Any], list[str]]] = []
    if located:
        tiers.append(([price, near], [f"price within {PRICE_BAND:.0%} of ${listing.price:,}", f"within {RADIUS_M / 1000:.0f} km"]))
    tiers.append(([price], [f"price within {PRICE_BAND:.0%} of ${listing.price:,}", "any distance"]))
    tiers.append(([], ["any price", "any distance"]))
    distance = ListingPersonaProfile.embedding.cosine_distance(source.embedding).label("distance")
    for where, words in tiers:
        stmt = (
            select(Listing, ListingPersonaProfile, distance)
            .join(ListingPersonaProfile, ListingPersonaProfile.listing_id == Listing.id)
            .where(
                ListingPersonaProfile.persona == source.persona,
                ListingPersonaProfile.embedding.is_not(None),
                ListingPersonaProfile.embed_model == source.embed_model,
                ListingPersonaProfile.listing_id != listing.id,
                Listing.latitude.is_not(None) if located and near in where else True,
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
- `distinct` is one sentence on what the source house has that most candidates do not.""" % REASON_WORDS


def _pct(price: int, base: int) -> str:
    return f"{(price - base) / base * 100:+.0f}%" if base else "?"


def rerank_prompt(listing: Listing, source: ListingPersonaProfile, facts: dict[str, Any] | None, rows: list[tuple[Listing, ListingPersonaProfile, float]]) -> str:
    def one(l: Listing, p: ListingPersonaProfile) -> str:
        return (
            f"- id {l.id}: {l.building_type or '?'}, {l.bedrooms_text or l.bedrooms_total or '?'} bed, {l.bathrooms or '?'} bath, price {_pct(l.price, listing.price)} vs source; score {p.score}/10\n"
            f"  pitch: {p.pitch}\n  signals: {'; '.join(p.signals or [])}"
        )

    rubric = hp.RUBRICS[source.persona].split("\n", 1)[0]
    head = (
        f"Buyer: {rubric}\n\n"
        f"Source house: {listing.building_type or '?'}, {listing.bedrooms_text or listing.bedrooms_total or '?'} bed, {listing.bathrooms or '?'} bath; score {source.score}/10\n"
        f"  summary: {(facts or {}).get('summary') or ''}\n  pitch: {source.pitch}\n  signals: {'; '.join(source.signals or [])}\n  concerns: {'; '.join(source.concerns or [])}\n\n"
        f"Candidates ({len(rows)}), nearest first by the pitch:\n"
    )
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


def rerank(client: llm.Backend, listing: Listing, source: ListingPersonaProfile, facts: dict[str, Any] | None, rows: list[tuple[Listing, ListingPersonaProfile, float]]) -> tuple[list[tuple[str, str]], str | None]:
    """The model's order and reasons, with invented ids dropped; raises ModelUnavailable on failure."""
    user = rerank_prompt(listing, source, facts, rows)
    try:
        out = client.structured(system=RERANK_SYSTEM, user=user, schema=Rerank, effort="low", max_tokens=MAX_TOKENS)
    except llm.ModelUnavailable as exc:
        if not any(w in str(exc) for w in RETRY_ONCE):
            raise
        out = client.structured(system=RERANK_SYSTEM, user=user, schema=Rerank, effort="low", max_tokens=MAX_TOKENS)
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


def _request_hash(persona: str, rows: list[tuple[Listing, ListingPersonaProfile, float]], model: str) -> str:
    key = json.dumps({"persona": persona, "ids": [l.id for l, _, _ in rows], "v": [PROMPT_VERSION, hp.PROMPT_VERSION], "model": model})
    return hashlib.sha256(key.encode()).hexdigest()


def similar(session: Session, listing: Listing, persona: str, *, client: llm.Backend | None = None, use_model: bool = True, limit: int = RESULTS) -> SimilarHomes:
    if persona not in hp.PERSONAS:
        raise ValueError(f"unknown persona {persona}")
    source = session.get(ListingPersonaProfile, (listing.id, persona))
    label = hp.PERSONA_LABELS[persona]
    if source is None or source.embedding is None:
        row = session.get(ListingProfile, listing.id)
        note = "the profile is not written yet" if source is None else "the pitch is not embedded yet"
        if row is not None and row.facts is None and row.note:
            note = f"the profile could not be written: {row.note}"
        return SimilarHomes(listing_id=listing.id, persona=persona, label=label, source_score=None, source_signals=[], items=[], candidates=0, filters=[], model=None, reranked=False, cached=False, note=note)
    rows, filters = candidates(session, listing, source)
    facts = (session.get(ListingProfile, listing.id) or ListingProfile()).facts
    if not rows:
        return SimilarHomes(listing_id=listing.id, persona=persona, label=label, source_score=source.score, source_signals=list(source.signals or []), items=[], candidates=0, filters=filters, model=None, reranked=False, cached=False, note="no other listing has a profile for this persona yet")

    client = client or (make_client() if use_model else None)
    model = client.model if client else ""
    picks: list[tuple[str, str]] | None = None
    distinct: str | None = None
    reranked = cached = False
    note: str | None = None
    key = _request_hash(persona, rows, model)
    if client is not None:
        hit = session.get(SimilarResult, (listing.id, key))
        if hit is not None and datetime.now(timezone.utc) - hit.created_at < CACHE_TTL:
            picks = [(p["id"], p["reason"]) for p in hit.result["picks"]]
            distinct = hit.result.get("distinct")
            reranked, cached = True, True
        else:
            try:
                picks, distinct = rerank(client, listing, source, facts, rows)
                reranked = len(picks) >= 1
                if reranked:
                    if hit is None:
                        hit = SimilarResult(listing_id=listing.id, request_hash=key)
                        session.add(hit)
                    hit.model, hit.result, hit.created_at = model, {"picks": [{"id": i, "reason": r} for i, r in picks], "distinct": distinct}, datetime.now(timezone.utc)
                    session.commit()
                else:
                    note = "the model picked none of the candidates; showing the nearest instead"
            except llm.ModelUnavailable as exc:
                note = f"not reranked: {exc}"
    else:
        note = "not reranked: no model configured" if use_model else None
    if not reranked:
        picks = fallback_reasons(source, rows)

    by_id = {l.id: (l, p, d) for l, p, d in rows}
    items = [
        SimilarHome(listing=_summary(l), score=p.score, reason=reason, distance=round(d, 4), signals=list(p.signals or []))
        for pid, reason in (picks or [])[:limit]
        for l, p, d in [by_id[pid]]
    ]
    return SimilarHomes(
        listing_id=listing.id, persona=persona, label=label, source_score=source.score, source_signals=list(source.signals or []),
        distinct=distinct, items=items, candidates=len(rows), filters=filters, model=model or None, reranked=reranked, cached=cached, note=note,
    )
