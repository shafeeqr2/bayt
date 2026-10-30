"""Session taste: what a visitor's opens, saves and dismissals say about the buyer they are.

No login. The frontend keeps a random session id in an httpOnly cookie and posts
one event per action. After every 5th event one structured call to the text model
reads the last 20 events, each with the house's facts and its 4 persona scores, and
writes a 1-to-2-sentence summary, a persona guess with a confidence, and a few
"likes". Above 0.7 confidence the frontend sets the default buyer from the guess.

The model call releases the database connection first (see `summarize`), like the
floor plan hints, so a slow answer never holds a pool slot.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Listing, ListingPersonaProfile, SessionEvent, SessionTaste
from app.similar.profile import PERSONA_LABELS, PERSONAS
from app.zoning import answer as llm

log = logging.getLogger(__name__)

PROMPT_VERSION = 1
MAX_TOKENS = 700
EVERY = 5  # actions between summaries
WINDOW = 20  # events the model reads
MAX_EVENTS = 2000  # per session; beyond this new events are dropped
THRESHOLD = 0.7  # confidence above which the frontend sets the default buyer
SID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

Kind = Literal["open", "save", "unsave", "dismiss"]
Via = Literal["similar", "search", "direct", "saved"]
KINDS: tuple[str, ...] = ("open", "save", "unsave", "dismiss")


def valid_sid(sid: str) -> bool:
    return bool(SID.match(sid))


class Taste(BaseModel):
    summary: str = Field(description="1 or 2 plain sentences addressed to 'you' about the kind of home you keep opening and saving. No street names, no prices.")
    persona: Literal["first_time_buyer", "investor", "flipper", "builder"] = Field(description="The buyer type the actions fit best")
    confidence: float = Field(description="0 to 1: how sure the actions point at that buyer type")
    likes: list[str] = Field(description="3 to 5 short phrases for what you seem to like, e.g. 'finished basements with a separate entrance'")


SYSTEM = """You read what a visitor did on a Toronto home-search site and say what kind of buyer they are.

You get the last actions: opened, saved, unsaved or dismissed a listing, with the house's facts and how well it scores for 4 buyer types (first-time buyer, investor, flipper, builder, 1 to 10). Saves count most, dismissals count against, opens count a little.

Rules:
- `summary`: 1 or 2 plain sentences addressed to "you" ("You keep saving bungalows with a rental suite."). No street names, no neighbourhood names, no prices, no marketing words.
- `persona`: the buyer type whose scores the saved and opened houses are high on, and whose reasons match what they have in common.
- `confidence`: 0.9 when 3 or more saves agree, 0.5 when only opens agree, 0.3 when actions point different ways. Never above 0.6 with fewer than 2 saves.
- `likes`: 3 to 5 short phrases, each about the house, not the person."""


# -- events ------------------------------------------------------------------------------------------


def record(session: Session, sid: str, listing_id: str, kind: str, via: str | None, persona: str | None) -> int:
    """Store one event and return the session's action count. Drops events past MAX_EVENTS."""
    count = session.scalar(select(func.count()).select_from(SessionEvent).where(SessionEvent.session_id == sid)) or 0
    if count >= MAX_EVENTS:
        return count
    session.add(SessionEvent(session_id=sid, listing_id=listing_id, kind=kind, via=via, persona=persona))
    session.commit()
    return count + 1


def saves(session: Session, sid: str) -> list[str]:
    """Listing ids saved and not unsaved since, newest save first."""
    rows = session.execute(
        select(SessionEvent.listing_id, SessionEvent.kind)
        .where(SessionEvent.session_id == sid, SessionEvent.kind.in_(("save", "unsave")))
        .order_by(SessionEvent.id)
    ).all()
    return saved_ids(rows)


def saved_ids(rows: list[tuple[str, str]]) -> list[str]:
    """Pure part of `saves`: replay save/unsave in order."""
    current: dict[str, None] = {}
    for listing_id, kind in rows:
        if kind == "save":
            current.pop(listing_id, None)
            current[listing_id] = None
        else:
            current.pop(listing_id, None)
    return list(reversed(current))


def due(actions: int) -> bool:
    """A summary is written after every EVERY-th action."""
    return actions > 0 and actions % EVERY == 0


def taste_for(session: Session, sid: str) -> SessionTaste | None:
    row = session.get(SessionTaste, sid)
    return row if row is not None and row.summary else None


def default_persona(taste: SessionTaste | Taste | None) -> str | None:
    """The buyer the frontend should preselect, or None when the guess is weak."""
    if taste is None or taste.persona not in PERSONAS or taste.confidence is None:
        return None
    return taste.persona if taste.confidence >= THRESHOLD else None


# -- the summary -------------------------------------------------------------------------------------


def _facts(listing: Any) -> str:
    bits = [
        listing.building_type or "home",
        f"{listing.bedrooms_text} bd" if listing.bedrooms_text else None,
        f"{listing.bathrooms} ba" if listing.bathrooms is not None else None,
        f"{listing.sqft_min}-{listing.sqft_max} sqft" if listing.sqft_min and listing.sqft_max else None,
        listing.lot_size,
        listing.ownership_type,
    ]
    return ", ".join(b for b in bits if b)


def event_lines(events: list[tuple[str, str | None, Any, dict[str, int], str | None]]) -> list[str]:
    """One line per event: what was done, the house, its 4 scores, and the best persona's pitch."""
    out = []
    for kind, via, listing, scores, pitch in events:
        score_text = ", ".join(f"{PERSONA_LABELS.get(p, p)} {scores[p]}" for p in PERSONAS if p in scores) or "no scores yet"
        line = f"- {kind.upper()}{f' (from {via})' if via else ''}: {_facts(listing)}. Scores: {score_text}."
        if pitch:
            line += f" Pitch: {pitch[:260]}"
        out.append(line)
    return out


def user_prompt(lines: list[str]) -> str:
    return "Actions, oldest first:\n" + "\n".join(lines)


def _window(session: Session, sid: str) -> list[tuple[str, str | None, Any, dict[str, int], str | None]]:
    events = session.scalars(
        select(SessionEvent).where(SessionEvent.session_id == sid).order_by(SessionEvent.id.desc()).limit(WINDOW)
    ).all()
    events = list(reversed(events))
    ids = {e.listing_id for e in events}
    listings = {l.id: l for l in session.scalars(select(Listing).where(Listing.id.in_(ids))).all()} if ids else {}
    profiles: dict[str, dict[str, int]] = {}
    pitches: dict[str, tuple[int, str]] = {}
    if ids:
        for row in session.scalars(select(ListingPersonaProfile).where(ListingPersonaProfile.listing_id.in_(ids))).all():
            profiles.setdefault(row.listing_id, {})[row.persona] = row.score
            if row.listing_id not in pitches or row.score > pitches[row.listing_id][0]:
                pitches[row.listing_id] = (row.score, row.pitch)
    out = []
    for e in events:
        listing = listings.get(e.listing_id)
        if listing is None:
            continue
        out.append((e.kind, e.via, listing, profiles.get(e.listing_id, {}), pitches.get(e.listing_id, (0, None))[1]))
    return out


def clean(t: Taste) -> Taste:
    return Taste(
        summary=t.summary.strip()[:400],
        persona=t.persona,
        confidence=min(max(float(t.confidence), 0.0), 1.0),
        likes=[l.strip()[:60] for l in t.likes if l.strip()][:5],
    )


def make_client() -> llm.Backend | None:
    # The text model, plain JSON mode like the other Nemotron calls.
    return llm.make_client(None, json_mode="object")


def summarize(session: Session, sid: str, actions: int, client: llm.Backend | None) -> SessionTaste | None:
    """Write the taste row for a session from its last events. None without a model or when it gave nothing usable."""
    if client is None:
        return None
    lines = event_lines(_window(session, sid))
    if not lines:
        return None
    row = session.get(SessionTaste, sid) or SessionTaste(session_id=sid)
    row.actions = actions
    row.model = client.model
    row.prompt_version = PROMPT_VERSION
    row.computed_at = datetime.now(timezone.utc)
    # Give the database connection back during the model call; the session reopens one for the write.
    session.close()
    try:
        taste = clean(_ask(client, lines))
        row.summary, row.persona, row.confidence, row.likes, row.note = taste.summary, taste.persona, taste.confidence, taste.likes, None
    except (llm.ModelUnavailable, ValueError) as exc:
        log.warning("taste summary failed for %s: %s", sid, exc)
        row.note = str(exc)[:500]
    session.add(row)
    session.commit()
    return row if row.summary else None


def _ask(client: llm.Backend, lines: list[str]) -> Taste:
    out = client.structured(system=SYSTEM, user=user_prompt(lines), schema=Taste, effort="low", max_tokens=MAX_TOKENS)
    assert isinstance(out, Taste)
    return out


# -- the metric --------------------------------------------------------------------------------------


def similar_metric(session: Session) -> dict[str, Any]:
    """Share of sessions with a save whose saved house was first opened from the similar page."""
    events = session.execute(
        select(SessionEvent.session_id, SessionEvent.listing_id, SessionEvent.kind, SessionEvent.via).order_by(SessionEvent.id)
    ).all()
    return metric_from_rows(events)


def metric_from_rows(rows: list[tuple[str, str, str, str | None]]) -> dict[str, Any]:
    """Pure part of `similar_metric`: replay events in order."""
    opened_via_similar: set[tuple[str, str]] = set()
    with_save: set[str] = set()
    via_similar: set[str] = set()
    for sid, listing_id, kind, via in rows:
        if kind == "open" and via == "similar":
            opened_via_similar.add((sid, listing_id))
        elif kind == "save":
            with_save.add(sid)
            if (sid, listing_id) in opened_via_similar:
                via_similar.add(sid)
    return {
        "sessions_with_save": len(with_save),
        "sessions_saved_via_similar": len(via_similar),
        "share": round(len(via_similar) / len(with_save), 3) if with_save else None,
    }
