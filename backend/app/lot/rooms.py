"""Room completion for the floor plan: what the listing says about rooms it does not list.

TRREB listings carry at most 12 rooms, often without sizes, and the description
and the photos mention more: "finished basement with rec room, fourth bedroom and
3-piece bath", a photo labelled "Second-floor office". The generated plan drew
only the room table, so large houses came out mostly empty.

One structured call to the text model reads the room table, the description and
the photo labels and returns the rooms that are missing or unsized, with a
typical size for each and the reason, plus how much of the footprint the top
floor covers when the house is a 1.5-storey or has a smaller upper floor. The
plan draws them as assumed rooms (dashed) with the source in the tooltip.

The answer is cached per listing in `floor_plan_hints`. Without a model key the
plan falls back to the room table alone, as before.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import FloorPlanHint, Listing
from app.photos import reader as photo_reader
from app.zoning import answer as llm

log = logging.getLogger(__name__)

PROMPT_VERSION = 2
MAX_TOKENS = 1500
MAX_ROOMS = 8
DRAWN_LEVELS = ("Basement", "Main level", "Second level", "Third level")
Level = Literal["Basement", "Main level", "Second level", "Third level"]
Source = Literal["room list", "description", "photos"]


class RoomHint(BaseModel):
    name: str = Field(description="The room, named like the room list: 'Bedroom 4', 'Recreational, Games room', 'Bathroom', 'Office'")
    level: str = Field(description="One of: Basement, Main level, Second level, Third level")
    width_m: float = Field(description="A typical width in metres for this kind of room in a Toronto house, e.g. 3.3 for a bedroom")
    depth_m: float = Field(description="A typical depth in metres")
    source: Source = Field(description="'room list' when the room is listed without a size; 'description' or 'photos' when only they mention it")
    why: str = Field(description="At most 12 words quoting or pointing at the evidence")


class Completion(BaseModel):
    rooms: list[RoomHint] = Field(description="Rooms that are missing from the room list or listed without a size; empty when the list is complete")
    upper_floor_share: float | None = Field(
        description="For a house whose top floor is smaller than the ground floor (a 1.5-storey, a loft, a set-back third floor): "
        "the share of the footprint the top floor covers, 0.3 to 0.9. Null for a full storey or when unknown."
    )
    notes: list[str] = Field(description="0 to 2 short notes a buyer should know about the layout, e.g. 'Open-plan main floor'")


SYSTEM = """You complete the room list of a house for sale in Toronto so a floor plan can be drawn from it.

You get the room list (name | level | size), the counts, the listing description, and what a vision model saw in the photos. The room list is incomplete: listings carry at most 12 rooms and often leave out sizes. Work through these 3 steps and return every room you find:

1. Every listed room whose size is "no size" or "Measurements not available": return it with the same name and level and a typical size (source "room list").
2. Every room the description names that the room list does not have on that level: add it (source "description"). Read carefully: "family room", "home office", "second kitchen", "2 bathrooms downstairs", "4th bedroom in the basement", "finished basement with rec room", "mudroom", "sunroom", "loft".
3. Every room a photo shows that the room list does not have on that level (source "photos").

Rules:
- Never repeat a room that is listed with a size. Never add a room that nothing mentions. Hallways, closets and stairs are not rooms.
- Bedrooms: "3 + 1" means 3 above grade and 1 in the basement; if the list has fewer, add the missing ones. Bathrooms: the count includes powder rooms; the description often says where they are ("2 bathrooms in the suite").
- Levels are exactly: Basement, Main level, Second level, Third level. A bungalow has no Second level; a basement suite's rooms are on the Basement.
- Typical sizes in metres: bedroom 3.3 by 3.6; primary bedroom 3.7 by 4.5; bathroom 2.4 by 1.5; powder room 1.5 by 1.2; kitchen 3.2 by 3.8; living 3.6 by 4.6; dining 3.2 by 3.6; family 3.6 by 4.6; office or den 2.8 by 3.0; rec room 4.0 by 6.0; laundry 1.8 by 2.4; utility 2.0 by 3.0; cold room 1.5 by 2.5; foyer 1.8 by 2.4; sunroom 2.8 by 3.6.
- upper_floor_share: only when the description or an exterior photo says 1.5 storey, a loft, dormers, or a set-back top floor; 0.3 to 0.9. Otherwise null.
- At most 8 rooms. Plain names. No marketing words.

Example answer for a list with "Office | Main level | no size" and a description that says "finished basement with a rec room and a 3-piece bath":
{"rooms": [{"name": "Office", "level": "Main level", "width_m": 2.8, "depth_m": 3.0, "source": "room list", "why": "listed with no size"},
 {"name": "Recreational, Games room", "level": "Basement", "width_m": 4.0, "depth_m": 6.0, "source": "description", "why": "'finished basement with a rec room'"},
 {"name": "Bathroom", "level": "Basement", "width_m": 2.4, "depth_m": 1.5, "source": "description", "why": "'3-piece bath' in the basement"}],
 "upper_floor_share": null, "notes": []}"""


def _photo_lines(photos: photo_reader.ListingPhotos | None) -> list[str]:
    if not photos:
        return []
    lines = []
    for p in photos.photos:
        f = p.facts
        if f is None or f.kind not in ("interior", "exterior_front", "exterior_back", "street"):
            continue
        bits = [f.title]
        if f.room:
            bits.append(f"listed room: {f.room}")
        if f.level and f.level != "unknown":
            bits.append(f"level: {f.level}")
        if f.storeys:
            bits.append(f"{f.storeys} storeys visible")
        lines.append("- " + "; ".join(bits))
    return lines[:30]


def user_prompt(listing: Any, photos: photo_reader.ListingPhotos | None) -> str:
    rooms = listing.rooms or []
    listed = [f"- {r.get('type') or 'Room'} | {r.get('level') or 'no level'} | {r.get('dimension') or 'no size'}" for r in rooms]
    building = ((listing.raw or {}).get("_details") or {}).get("Building") or {}
    counts = [
        f"Bedrooms: {listing.bedrooms_text or listing.bedrooms_total or 'unknown'}",
        f"Bathrooms: {listing.bathrooms or 'unknown'}" + (f" (half: {building.get('HalfBathTotal')})" if building.get("HalfBathTotal") else ""),
        f"Storeys: {listing.stories or 'unknown'}",
        f"Type: {listing.building_type or 'unknown'}",
        f"Interior: {listing.sqft_min or '?'}-{listing.sqft_max or '?'} sqft",
    ]
    parts = [
        "Room list (name | level | size):",
        *(listed or ["- none"]),
        "",
        "Counts: " + "; ".join(counts),
        "",
        "Description:",
        (listing.description or "").strip()[:2500] or "(none)",
    ]
    lines = _photo_lines(photos)
    if lines:
        parts += ["", "Photos (what the vision model saw):", *lines]
    return "\n".join(parts)


def complete(client: llm.Backend, listing: Any, photos: photo_reader.ListingPhotos | None) -> Completion:
    out = client.structured(system=SYSTEM, user=user_prompt(listing, photos), schema=Completion, effort="low", max_tokens=MAX_TOKENS)
    assert isinstance(out, Completion)
    return clean(out, sized_rooms(listing))


# The model copies level names from the listing ("Ground level") or shortens them; map them to the 4 we draw.
LEVEL_ALIASES = {
    "basement": "Basement", "sub-basement": "Basement", "lower level": "Basement", "lower": "Basement", "lower floor": "Basement",
    "main level": "Main level", "main": "Main level", "main floor": "Main level", "ground level": "Main level", "ground": "Main level",
    "ground floor": "Main level", "first floor": "Main level", "first level": "Main level",
    "second level": "Second level", "second": "Second level", "second floor": "Second level", "upper level": "Second level",
    "upper": "Second level", "upper floor": "Second level", "2nd floor": "Second level",
    "third level": "Third level", "third": "Third level", "third floor": "Third level", "3rd floor": "Third level",
}


def normalise_level(level: str) -> str | None:
    return LEVEL_ALIASES.get(level.strip().lower())


def sized_rooms(listing: Any) -> set[tuple[str, str]]:
    """(name, level) of every listed room that has a size: the model must not add those again."""
    from app.lot.floorplan import LEVELS, parse_dimension  # noqa: PLC0415 (floorplan imports nothing from here)

    out = set()
    for r in listing.rooms or []:
        level = LEVELS.get((r.get("level") or "").strip())
        if level and parse_dimension(r.get("dimension")):
            out.add(((r.get("type") or "").strip().lower(), level[0]))
    return out


def clean(c: Completion, sized: set[tuple[str, str]] | None = None) -> Completion:
    """Levels we draw, sizes within reason, no echo of a listed room, at most MAX_ROOMS."""
    rooms: list[RoomHint] = []
    seen: set[tuple[str, str]] = set(sized or ())
    for r in c.rooms:
        level = normalise_level(r.level)
        name = r.name.strip()[:40]
        if level is None or not name or (name.lower(), level) in seen:
            continue
        w, d = min(max(r.width_m, 1.2), 8.0), min(max(r.depth_m, 1.2), 8.0)
        if w * d < 2.0:
            continue
        seen.add((name.lower(), level))
        rooms.append(r.model_copy(update={"level": level, "width_m": round(w, 2), "depth_m": round(d, 2), "name": name}))
        if len(rooms) >= MAX_ROOMS:
            break
    share = c.upper_floor_share
    if share is not None and not 0.3 <= share <= 0.9:
        share = None
    return Completion(rooms=rooms, upper_floor_share=share, notes=[n.strip() for n in c.notes if n.strip()][:2])


def make_client() -> llm.Backend | None:
    # The text model, plain JSON mode like the other Nemotron calls.
    return llm.make_client(None, json_mode="object")


def hints_for(session: Session, listing: Listing, client: llm.Backend | None) -> FloorPlanHint | None:
    """The cached completion for a listing, computed on first use. None without a model or when the model gave nothing usable."""
    if client is None:
        return None
    row = session.get(FloorPlanHint, listing.id)
    if row is not None and row.model == client.model and row.prompt_version == PROMPT_VERSION:
        return row if row.hints is not None else None
    photos = photo_reader.labels_for(session, listing)
    row = row or FloorPlanHint(listing_id=listing.id)
    row.model = client.model
    row.prompt_version = PROMPT_VERSION
    row.computed_at = datetime.now(timezone.utc)
    # The model call can take tens of seconds. Give the database connection back for that
    # time (everything needed is loaded); the session reopens one for the write below.
    session.close()
    try:
        row.hints = complete(client, listing, photos).model_dump(mode="json")
        row.note = None
    except (llm.ModelUnavailable, ValueError) as exc:
        log.warning("floor plan hints failed for %s: %s", listing.id, exc)
        row.hints = None
        row.note = str(exc)[:500]
    session.add(row)
    session.commit()
    return row if row.hints is not None else None
