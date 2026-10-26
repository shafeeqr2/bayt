"""Read the listing photos with a vision model: a title, one sentence, and facts about the house.

Each photo gets one structured call. The model sees the photo and the listing's
room list, and returns `PhotoFacts`: what the photo shows (front, back, a room,
a drawn floor plan), a short title, one sentence about the house in the photo,
and the facts a floor plan can use: the listed room it most likely is, the
windows and the wall they are on, doors to outside, stairs, what other space is
open to it, and for exterior shots the storeys and the garage side.

The caption is about the house, never the furniture: a buyer wants to know the
room, its light and its finishes, not the staging.

One photo at a time gets the level wrong about 1 time in 10: a main-floor room
with hardwood is called the basement family room, the basement kitchen is called
the main floor. A second pass (`review_labels`) sends every label of the listing
and a contact sheet of all the photos (`sheet.py`) to the vision model in one
call. It sees the finishes side by side, the order of the photos, the listed
rooms per level, and the stairs, and returns only the photos whose level, room
or front-or-back call changes. The code applies those and rewrites the level
words in the title and the caption; the sentence is otherwise kept as written.

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
from app.photos import sheet
from app.zoning import answer as llm

PROMPT_VERSION = 2
WORKERS = 6
REVIEW_RUNS = 5  # the second pass runs this many times in parallel ...
REVIEW_AGREE = 3  # ... and a fix counts when this many runs propose it
NEIGHBOURS = 5  # a level change is vetoed when most of these nearest photos sit on another floor
REVIEW_ROUNDS = 2  # the second round sees the labels the first round corrected, so the last stragglers find their floor
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
- kind = floor_plan only for a line drawing on a page: a floor plan, a sketch or a survey with walls or lot lines drawn. A photograph from the air is aerial, never floor_plan.
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


# --- The second pass ----------------------------------------------------------------------------


class Fix(BaseModel):
    """One photo whose label changes after seeing all the photos together.

    The `*_was` fields repeat the label as given; a fix whose `*_was` does not match
    the stored label is a misread and is not applied.
    """

    photo: int = Field(description="The photo number as given, starting at 1")
    kind_was: Kind = Field(description="The kind as given")
    kind_now: Kind = Field(description="The corrected kind; the same as kind_was when it does not change")
    level_was: Level | None = Field(description="The level as given")
    level_now: Level | None = Field(description="The corrected floor; null for exterior photos")
    room_was: str | None = Field(description="The room as given")
    room_now: str | None = Field(description="The corrected listed room, copied exactly; null when none fits")
    why: str = Field(description="One clause of at most 15 words: what in the other photos shows this")


class Review(BaseModel):
    fixes: list[Fix] = Field(description="Only the photos whose kind, level or room changes. Empty when every label is right.")


REVIEW_SYSTEM = """You check the labels of all the photos of one house for sale, written one photo at a time, and fix what the single-photo view got wrong: the floor (level), the listed room, and front versus back.

The single-photo labels describe what is in the picture well: the floor finish, the windows, the stairs, the doors. They guess the room name and the floor. Trust the description over the room name.

What one photo cannot see, the set can:
- Listing photos run in order: the front of the house, the main floor room by room, then the upper floor or the basement, then the yard. A photo between two basement photos is usually the basement.
- Finishes repeat within a floor. The same floor finish, trim, ceiling and window style in 2 photos means the same floor, often the same room.
- The listed rooms say which rooms exist on which level. Use them to pick the room, after the finishes have fixed the floor.
- Small high windows, low ceilings, exposed ducts or a furnace mean the basement. Large windows at eye level, hardwood and crown moulding mean a floor above ground.
- When a photo shows above-ground finishes but its room is listed only in the basement, the room name is wrong, not the floor. Pick a listed room on that floor that fits (a bedroom with hardwood and a closet is a bedroom), or null.
- The camera stands on the floor of the photo. Stairs going down means the photo is on the upper floor, usually the main floor. Stairs going up from a room with small high windows means the basement.
- A raised porch with a railing next to the front door, the garage or the driveway is the front of the house, not a back deck.

Rules:
- Return only the photos that change. Keep every other label as it is.
- Copy `room` exactly from the listed rooms, or null.
- Do not change a label without a reason from another photo or from the room list.
- `why` is one clause of at most 15 words."""


def review_prompt(listing: Any, labels: list[tuple[int, PhotoFacts]], total: int) -> str:
    rows = []
    for i, f in labels:
        rows.append(
            f"#{i + 1} kind={f.kind} level={f.level} room={f.room} windows={f.windows}/{f.window_wall} stairs={f.stairs} "
            f"open_to={f.open_to} | {f.title} | {f.caption}"
        )
    return (
        _context(listing)
        + "\n\nLabels, one photo at a time:\n"
        + "\n".join(rows)
        + f"\n\nThe image is a contact sheet of all {total} photos, numbered #1 to #{total}, left to right then down. "
        "Compare the finishes you see across the photos. Which labels are wrong?"
    )


# --- Response shapes --------------------------------------------------------------------------


class PhotoLabel(BaseModel):
    index: int
    url: str = Field(description="The photo the facts describe (the listing's medium-size URL)")
    facts: PhotoFacts | None = Field(None, description="Null when the photo is not read yet or the model gave nothing usable")
    note: str | None = Field(None, description="Why `facts` is null, when it is; or what the second pass changed and why")


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


def make_review_client() -> llm.Backend | None:
    """The second pass uses the vision model too: it looks at the contact sheet."""
    return make_client()


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


def read_listing_photos(
    session: Session,
    listing: Listing,
    client: llm.Backend | None = None,
    *,
    force: bool = False,
    review_client: llm.Backend | None = None,
    review: bool = True,
) -> ListingPhotos:
    """Read every photo that has no current facts (or all of them with `force`), store the results, then run the second pass."""
    client = client or make_client()
    if client is None:
        raise llm.ModelUnavailable("LLM_API_KEY is not set")
    photos = listing.photos or []
    rows = _rows(session, listing.id)
    todo = [(i, p) for i, p in enumerate(photos) if force or _stale(rows.get(i), photo_url(p))]

    def ask(i: int, image: str, extra: str = "") -> PhotoFacts:
        facts = client.structured(
            system=SYSTEM,
            user=user_prompt(listing, i, len(photos)) + extra,
            schema=PhotoFacts,
            effort="low",
            max_tokens=MAX_TOKENS,
            images=[image],
        )
        return clean(facts, listing)  # type: ignore[arg-type]

    def one(item: tuple[int, dict[str, str]]) -> tuple[int, PhotoFacts | None, str | None]:
        i, p = item
        # Fetch the photo here and send the bytes; the URL alone can come back stale from the host's cache.
        img = sheet.fetch(photo_url(p))
        image = sheet.photo_data_url(img) if img is not None else photo_url(p)
        drawing = sheet.light_share(img) >= sheet.DRAWING_LIGHT_SHARE if img is not None else None
        try:
            facts = ask(i, image)
            if facts.kind == "floor_plan" and drawing is False:
                # A drawing is a light page; this is a photograph. A false floor plan would replace the generated plan later.
                try:
                    again = ask(i, image, "\n\nThis is a photograph, not a drawing. A floor plan or survey is a line drawing on a white page. Label what the photograph shows.")
                    facts = again if again.kind != "floor_plan" else again.model_copy(update={"kind": "other"})
                except llm.ModelUnavailable:
                    facts = facts.model_copy(update={"kind": "other"})
            words = furniture_words(facts.caption)
            if words:
                # Once more, naming the words to leave out; keep the first answer if the retry fails.
                try:
                    again = ask(i, image, "\n\nWrite the caption without these words, which are not part of the house: " + ", ".join(words) + ".")
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
    if review and results:
        review_client = review_client or make_review_client()
        if review_client is not None:
            for _ in range(REVIEW_ROUNDS):
                review_labels(session, listing, review_client)
    return labels_for(session, listing)


def review_labels(session: Session, listing: Listing, client: llm.Backend | None = None) -> list[Fix]:
    """The second pass: all labels in one call, apply the fixes, store them. Returns the fixes applied."""
    client = client or make_review_client()
    if client is None:
        raise llm.ModelUnavailable("LLM_API_KEY is not set")
    rows = _rows(session, listing.id)
    labels = [(i, PhotoFacts.model_validate(r.facts)) for i, r in sorted(rows.items()) if r.facts]
    photos = listing.photos or []
    if len(labels) < 2:
        return []
    images = sheet.fetch_all([photo_url(p, "medium") for p in photos])
    hists = {i: sheet.finish_histogram(img) for i, img in enumerate(images) if img is not None}
    contact = sheet.data_url(sheet.sheet_from(images))
    user = review_prompt(listing, labels, len(photos))

    def run(_: int) -> list[Fix]:
        try:
            out = client.structured(system=REVIEW_SYSTEM, user=user, schema=Review, effort="low", max_tokens=2000, images=[contact])
            return list(out.fixes)  # type: ignore[attr-defined]
        except llm.ModelUnavailable:
            return []

    with ThreadPoolExecutor(max_workers=REVIEW_RUNS) as pool:
        runs = list(pool.map(run, range(REVIEW_RUNS)))
    by_index = dict(labels)
    agreed = consensus(runs, by_index)
    moving = {f.photo - 1 for f in agreed if f.level_now != by_index[f.photo - 1].level}
    applied: list[Fix] = []
    for fix in agreed:
        i = fix.photo - 1
        old = by_index[i]
        new = apply_fix(old, fix, listing)
        if new == old:
            continue
        if new.level != old.level and new.kind == "interior" and not neighbours_agree(i, new.level, by_index, hists, exclude=moving):
            continue  # the photos that look like this one sit on another floor
        changes = [f"{k}: {getattr(old, k)} -> {getattr(new, k)}" for k in ("kind", "level", "room") if getattr(old, k) != getattr(new, k)]
        rows[i].facts = new.model_dump()
        why = " ".join(fix.why.split()).rstrip(".")
        rows[i].note = "second pass: " + "; ".join(changes) + (f" ({why[:160]})" if why else "")
        applied.append(fix)
    session.commit()
    return applied


def consensus(runs: list[list[Fix]], by_index: dict[int, PhotoFacts]) -> list[Fix]:
    """The fixes that at least REVIEW_AGREE runs propose for the same photo, kind and level, and that match the stored label.

    One run of the vision model changes its mind from call to call; what 2 of 3 runs
    agree on holds up. The room comes from the most common `room_now` among them.
    """
    groups: dict[tuple[int, str, str | None], list[Fix]] = {}
    for fixes in runs:
        seen: set[tuple[int, str, str | None]] = set()
        for f in fixes:
            old = by_index.get(f.photo - 1)
            if old is None or not fix_matches(old, f):
                continue
            key = (f.photo, f.kind_now, f.level_now)
            if key in seen:
                continue  # one vote per run
            seen.add(key)
            groups.setdefault(key, []).append(f)
    out: list[Fix] = []
    for key, fixes in sorted(groups.items()):
        if len(fixes) < REVIEW_AGREE:
            continue
        rooms = [f.room_now for f in fixes]
        room = max(set(rooms), key=lambda r: (rooms.count(r), r or ""))
        out.append(fixes[0].model_copy(update={"room_now": room}))
    return out


def neighbours_agree(i: int, level: str | None, by_index: dict[int, PhotoFacts], hists: dict[int, Any], *, exclude: set[int], k: int = NEIGHBOURS) -> bool:
    """True unless the k photos that look most like photo i mostly sit on another floor.

    Votes are weighted by closeness (1 / (distance + 0.05)), so a near twin outweighs
    a few loose matches. Only interior photos with a known floor count, and never the
    photos being moved in the same pass (a wrong cluster would vouch for itself). With
    no usable neighbours the reviewer's call stands.
    """
    if i not in hists:
        return True
    pool = [
        j for j, f in by_index.items()
        if j != i and j not in exclude and j in hists and f.kind == "interior" and f.level and f.level != "unknown"
    ]
    nearest = sorted(((sheet.chi2(hists[i], hists[j]), j) for j in pool))[:k]
    if not nearest:
        return True
    weight = lambda d: 1.0 / (d + 0.05)  # noqa: E731
    against = sum(weight(d) for d, j in nearest if by_index[j].level != level)
    total = sum(weight(d) for d, _ in nearest)
    return against * 2 <= total


LEVEL_WORDS: dict[str, list[str]] = {
    "basement": ["basement", "lower-level", "lower level", "lower-floor", "lower floor"],
    "main": ["main-floor", "main floor", "main-level", "main level", "ground-floor", "ground floor"],
    "second": ["second-floor", "second floor", "second-level", "second level", "upper-floor", "upper floor", "upper-level", "upper level"],
    "third": ["third-floor", "third floor", "third-level", "third level"],
}


def fix_matches(old: PhotoFacts, fix: Fix) -> bool:
    """The fix describes the stored label (the model did not misread the photo number or copy a wrong value)."""
    return fix.kind_was == old.kind and fix.level_was == old.level and (fix.room_was or "").lower() == (old.room or "").lower()


def apply_fix(old: PhotoFacts, fix: Fix, listing: Any) -> PhotoFacts:
    """The label with the fix applied: kind, level, room, and the level words in the title and caption."""
    level = fix.level_now
    if level == "basement" and old.stairs == "down":
        level = old.level  # the camera stands above stairs that go down: not the lowest floor
    new = clean(old.model_copy(update={"kind": fix.kind_now, "level": level, "room": fix.room_now}), listing)
    title, caption = new.title, new.caption
    if new.level != old.level and old.level in LEVEL_WORDS:
        title, caption = reword_level(title, old.level, new.level), reword_level(caption, old.level, new.level)
    if new.room and old.room and new.room.lower() != old.room.lower():
        title, caption = reword_room(title, old.room, new.room), reword_room(caption, old.room, new.room)
    return new.model_copy(update={"title": title, "caption": caption})


def reword_level(text: str, old_level: str, new_level: str | None) -> str:
    """'Main-floor kitchen' -> 'Basement kitchen'; 'the basement has' -> 'the main floor has'."""
    words = "|".join(re.escape(w) for w in LEVEL_WORDS[old_level])
    replacement = LEVEL_WORDS[new_level][0] if new_level in LEVEL_WORDS else ""
    out = re.sub(rf"\b(?:{words})\b", lambda m: _match_case(replacement, m.group(0)), text, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out[:1].upper() + out[1:] if out else out


def reword_room(text: str, old_room: str, new_room: str) -> str:
    """'Dining room' -> 'Kitchen'; 'The dining room has' -> 'The kitchen has'. Room names are matched whole, any case."""
    base = re.sub(r"\s*\d+$", "", old_room)  # "Bedroom 2" also matches "bedroom"
    pattern = rf"\b(?:{re.escape(old_room)}|{re.escape(base)})\b"
    return re.sub(pattern, lambda m: new_room if m.group(0)[:1].isupper() else new_room.lower(), text, flags=re.I)


def _match_case(word: str, like: str) -> str:
    return word[:1].upper() + word[1:] if like[:1].isupper() else word


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
        if facts.level and facts.level != "unknown" and any(lvl for _, lvl in hits):
            # The room must be listed on the photo's level: a main-floor "Dining room" is not in the basement.
            # Two listed rooms with one name (a main and a basement kitchen): the level decides.
            hits = [h for h in hits if h[1] in (facts.level, None)]
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
