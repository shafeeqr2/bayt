"""Read the listing photos with a vision model: a title, one sentence, and facts about the house.

Each photo gets one structured call. The model sees the photo and the listing's
room list, and returns `PhotoFacts`: what the photo shows (front, back, a room,
a drawn floor plan), a short title, one sentence about the house in the photo,
and the facts a floor plan can use: the listed room it most likely is, the
windows and the wall they are on, doors to outside, stairs, what other space is
open to it, and for exterior shots the storeys and the garage side.

The caption is about the house, never the furniture: a buyer wants to know the
room, its light and its finishes, not the staging.

Results are kept in `listing_photos`, one row per photo, keyed by the listing and
the photo index, with the URL and the prompt version, so a changed photo set or
a changed prompt reads again and nothing else does. Reading is explicit (`POST
.../photos/read`); opening a listing page never calls the model.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Listing, ListingPhoto
from app.zoning import answer as llm

PROMPT_VERSION = 2
WORKERS = 6
MAX_TOKENS = 500
# Vision models per provider. The zoning model (a text model) does not read images.
DEFAULT_MODELS = {"openrouter": "nvidia/nemotron-3.5-super-vl", "nvidia": "nvidia/nemotron-3.5-super-vl", "anthropic": "claude-opus-5-5"}

Kind = Literal["exterior_front", "exterior_back", "exterior_side", "street", "aerial", "interior", "floor_plan", "other"]
Level = Literal["basement", "main", "second", "third", "unknown"]


class PhotoFacts(BaseModel):
    """What one listing photo shows, as far as the house goes."""

    kind: Kind = Field(description="exterior_front: the street face; exterior_back: the rear and yard; floor_plan: a drawn plan; interior: a room")
    title: str = Field(description="2 to 5 words naming what the photo shows, e.g. 'Front of the house', 'Kitchen', 'Second-floor bathroom'")
    caption: str = Field(
        description="One sentence, at most 25 words, about the house in this photo: the space, its windows and doors, "
        "ceiling height, built-in finishes (floors, counters, tile), and condition. Nothing about furniture, decor or staging."
    )
    level: Level | None = Field(description="The floor an interior photo is on, when the view or the room list makes it clear; null for exterior photos")
    room: str | None = Field(description="The listed room this photo most likely shows, copied exactly from the room list; null when none fits or you are unsure")
    windows: int | None = Field(description="Windows visible in the photo (count window units, not panes); null when the photo shows no wall")
    window_wall: Literal["left", "right", "far", "several", "none", "unknown"] = Field(
        description="Where the windows are from the camera's point of view: on the left wall, right wall, the far wall, on several walls, or none visible"
    )
    exterior_doors: int = Field(description="Doors to outside visible in the photo (patio doors, front door, garage doors); 0 when none")
    stairs: Literal["none", "up", "down", "both"] = Field(description="Stairs visible in the photo and which way they go from this floor")
    open_to: list[str] = Field(description="Other spaces visible through an opening with no door, e.g. ['dining room']; empty when the room is closed")
    storeys: int | None = Field(description="Storeys above ground visible in an exterior photo; null for interior photos")
    garage: Literal["left", "right", "centre", "none", "unknown"] = Field(
        description="For a front exterior photo: where an attached garage sits as seen from the street; 'none' when there is none; 'unknown' for other photos"
    )


SYSTEM = """You label the photos of a house for sale in Toronto so a buyer can see at a glance what each photo shows.

Rules:
- Write about the house: the space, its windows and doors, the ceiling, built-in finishes, the condition.
- Things that stay with the house are fine to name: floors, counters, cabinets, tile, fireplaces, tubs, sinks, closets, railings, doors, windows.
- Major appliances usually come with the house, so name them in a kitchen or laundry room: fridge, stove, range hood, dishwasher, microwave, washer, dryer. Say if they are stainless or built in.
- Never mention things that leave with the seller: furniture, beds, tables, chairs, sofas, rugs, curtains, blinds, lamps, art, plants, decor, people.
- `title` is 2 to 5 words. Name the space ("Kitchen", "Primary bedroom", "Front of the house", "Back yard and deck", "Floor plan").
- `caption` is one plain sentence of at most 25 words. No marketing words.
- `kind`: exterior_front is the street face (door, garage, porch); exterior_back is the yard side (deck, patio doors); street is the house seen from down the street; use "other" only for a map, a document or a close-up of a fixture.
- A raised porch with a railing beside the garage or the front door is the front, not the back.
- Pick `room` from the listed rooms only, copied exactly, when the photo clearly shows that room. Use the room's level and size to decide. Null when unsure.
- Two listed rooms can share a name on different levels (a main-floor kitchen and a basement kitchen). Give the name and set `level` to tell them apart.
- Count only what you can see. Never invent a count. Null when the photo gives no view of it.
- `open_to` is a list of room names; leave it empty when nothing is open to this room.
- A drawn plan, a sketch or a survey is kind = floor_plan.
- Same room from a second angle: label it the same room."""


# Things that leave with the seller. A caption that names one is asked for again, once.
# Appliances are not on the list: the fridge, stove, dishwasher, microwave, washer and
# dryer usually come with a Toronto house, and a buyer wants to know they are there.
FURNITURE = re.compile(
    r"\b(sofa|couch|arm ?chairs?|chairs?|tables?|beds?|headboard|dressers?|nightstands?|desks?|rugs?|carpets?|curtains?|drapes|blinds|"
    r"lamps?|chandeliers?|pendant lights?|mirrors?|art(?:work)?|paintings?|plants?|pillows?|cushions?|decor|ornaments?|tv|television|"
    r"sideboards?|hutch|bookshel(?:f|ves)|shelving|benches?|stools?|ottoman|vases?|towels?|toys?|people|person|cars?|vehicles?)\b",
    re.I,
)


def furniture_words(caption: str) -> list[str]:
    seen: list[str] = []
    for m in FURNITURE.finditer(caption):
        w = m.group(0).lower()
        if w not in seen:
            seen.append(w)
    return seen


def _context(listing: Any) -> str:
    rooms = listing.rooms or []
    lines = [f"- {r.get('type') or 'Room'} ({r.get('level') or 'level not given'}, {r.get('dimension') or 'no size'})" for r in rooms]
    facts = [
        f"Building: {listing.building_type or 'unknown type'}",
        f"Storeys: {listing.stories or 'not given'}",
        f"Bedrooms: {listing.bedrooms_total if listing.bedrooms_total is not None else 'not given'}",
        f"Bathrooms: {listing.bathrooms if listing.bathrooms is not None else 'not given'}",
        f"Parking: {listing.parking_type or 'not given'}",
    ]
    return "Listing facts:\n" + "\n".join(facts) + "\n\nListed rooms:\n" + ("\n".join(lines) if lines else "- none listed")


def user_prompt(listing: Any, index: int, total: int) -> str:
    return f"{_context(listing)}\n\nThis is photo {index + 1} of {total}. Describe what it shows of the house."


# --- Response shapes --------------------------------------------------------------------------


class PhotoLabel(BaseModel):
    index: int
    url: str = Field(description="The photo the facts describe (the listing's medium-size URL)")
    facts: PhotoFacts | None = Field(None, description="Null when the photo is not read yet or the model gave nothing usable")
    note: str | None = Field(None, description="Why `facts` is null, when it is")


class ListingPhotos(BaseModel):
    listing_id: str
    model: str | None = Field(description="The vision model that read the photos; null when none is configured")
    read: int = Field(description="Photos with facts")
    total: int
    photos: list[PhotoLabel]


# --- Reading ------------------------------------------------------------------------------------


def model_name() -> str:
    """The configured vision model, or the provider's default."""
    if settings.photo_model:
        return settings.photo_model
    p = llm.resolve_provider()
    return DEFAULT_MODELS.get(p.name, "") if p else ""


def make_client() -> llm.Backend | None:
    # Plain JSON mode: the schema-constrained mode stalls the Nemotron vision model (see OpenAIBackend).
    return llm.make_client(model_name() or None, json_mode="object")


def photo_url(photo: dict[str, str], size: str = "high") -> str:
    return photo.get(size) or photo.get("high") or photo.get("medium") or photo.get("low") or ""


def _rows(session: Session, listing_id: str) -> dict[int, ListingPhoto]:
    rows = session.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing_id)).all()
    return {r.photo_index: r for r in rows}


def _label(index: int, photo: dict[str, str], row: ListingPhoto | None) -> PhotoLabel:
    facts = PhotoFacts.model_validate(row.facts) if row and row.facts else None
    note = row.note if row else None
    if row is None:
        note = "not read yet"
    return PhotoLabel(index=index, url=photo_url(photo, "medium"), facts=facts, note=note)


def labels_for(session: Session, listing: Listing) -> ListingPhotos:
    """The stored labels, without calling the model."""
    rows = _rows(session, listing.id)
    photos = listing.photos or []
    labels = [_label(i, p, rows.get(i)) for i, p in enumerate(photos)]
    return ListingPhotos(
        listing_id=listing.id,
        model=model_name() or None,
        read=sum(1 for l in labels if l.facts),
        total=len(photos),
        photos=labels,
    )


def _stale(row: ListingPhoto | None, url: str) -> bool:
    return row is None or row.url != url or row.prompt_version != PROMPT_VERSION or (row.facts is None and row.note != "the model declined the request")


def read_listing_photos(session: Session, listing: Listing, client: llm.Backend | None = None, *, force: bool = False) -> ListingPhotos:
    """Read every photo that has no current facts (or all of them with `force`) and store the results."""
    client = client or make_client()
    if client is None:
        raise llm.ModelUnavailable("LLM_API_KEY is not set")
    photos = listing.photos or []
    rows = _rows(session, listing.id)
    todo = [(i, p) for i, p in enumerate(photos) if force or _stale(rows.get(i), photo_url(p))]

    def ask(i: int, p: dict[str, str], extra: str = "") -> PhotoFacts:
        facts = client.structured(
            system=SYSTEM,
            user=user_prompt(listing, i, len(photos)) + extra,
            schema=PhotoFacts,
            effort="low",
            max_tokens=MAX_TOKENS,
            images=[photo_url(p)],
        )
        return clean(facts, listing)  # type: ignore[arg-type]

    def one(item: tuple[int, dict[str, str]]) -> tuple[int, PhotoFacts | None, str | None]:
        i, p = item
        try:
            facts = ask(i, p)
            words = furniture_words(facts.caption)
            if words:
                # Once more, naming the words to leave out; keep the first answer if the retry fails.
                try:
                    again = ask(i, p, "\n\nWrite the caption without these words, which are not part of the house: " + ", ".join(words) + ".")
                    if len(furniture_words(again.caption)) < len(words):
                        facts = again
                except llm.ModelUnavailable:
                    pass
            return i, facts, None
        except llm.ModelUnavailable as exc:
            return i, None, str(exc)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(one, todo))

    for i, facts, note in results:
        row = rows.get(i)
        if row is None:
            row = ListingPhoto(listing_id=listing.id, photo_index=i)
            session.add(row)
            rows[i] = row
        row.url = photo_url(photos[i])
        row.model = client.model
        row.prompt_version = PROMPT_VERSION
        row.facts = facts.model_dump() if facts else None
        row.note = note
    session.commit()
    return labels_for(session, listing)


_LEVELS = {
    "Sub-basement": "basement", "Basement": "basement", "Lower level": "basement",
    "Main level": "main", "Ground level": "main",
    "Second level": "second", "Upper Level": "second",
    "Third level": "third",
}


def _level_key(level: str | None) -> str | None:
    return _LEVELS.get((level or "").strip())


def clean(facts: PhotoFacts, listing: Any) -> PhotoFacts:
    """Keep `room` only when it names a listed room; trim the title and caption to one line."""
    listed = [((r.get("type") or "").strip(), _level_key(r.get("level"))) for r in (listing.rooms or []) if r.get("type")]
    room = facts.room.strip() if facts.room else None
    if room:
        want = room.lower()
        exact = [(n, lvl) for n, lvl in listed if n.lower() == want]
        partial = [(n, lvl) for n, lvl in listed if want in n.lower()]
        # "Basement kitchen" names the listed "Kitchen"; the level then picks which one.
        contains = [(n, lvl) for n, lvl in listed if len(n) >= 4 and n.lower() in want]
        hits = exact or partial or contains
        if len(hits) > 1 and facts.level:
            # Two listed rooms share the name (a main and a basement kitchen): the level decides.
            hits = [h for h in hits if h[1] == facts.level] or hits
        room = hits[0][0] if hits else None
    title = " ".join(facts.title.split()).rstrip(".")
    caption = " ".join(facts.caption.split())
    exterior = facts.kind in ("exterior_front", "exterior_back", "exterior_side", "street", "aerial")
    open_to = [o.strip() for o in facts.open_to if o and o.strip().lower() not in ("none", "no", "n/a", "null", "nothing")]
    window_wall = facts.window_wall
    if facts.windows and window_wall == "none":
        window_wall = "unknown"
    return facts.model_copy(
        update={
            "room": None if exterior or facts.kind == "floor_plan" else room,
            "title": title,
            "caption": caption,
            "level": None if exterior else facts.level,
            "open_to": open_to,
            "window_wall": window_wall,
            "storeys": facts.storeys if exterior else None,
            "garage": facts.garage if facts.kind == "exterior_front" else "unknown",
        }
    )
