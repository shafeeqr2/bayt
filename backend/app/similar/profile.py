"""The house profile: the facts of a listing and 4 persona views, written by one model call.

A buyer who taps "more like this" does not mean the same bed count. They mean the
feel, the layout, the finish level, the lot and the potential, and which of those
matters depends on who is asking. So each listing gets:

- a fact layer (`Facts`): era, layout, condition, basement, outdoor space, in
  plain fields the model fills from the listing text, the rooms, the city and lot
  data, the investment estimate and the photos;
- 4 persona views (`PersonaView`, one per `PERSONAS`): a score from 1 to 10 on a
  fixed rubric, a pitch of 3 to 5 sentences in that persona's words, the signals
  that drove the score, and the concerns.

The pitch is what gets embedded (`app.similar.embed`), so 2 houses with the same
income profile sit close in the investor space even when they look nothing alike.
The pitch names no address and no street, so location does not dominate the
vector; the search applies location and price as hard filters instead.

The model sees the photo labels when the listing has them (`listing_photos`), and
up to `MAX_PHOTOS` of the photos themselves otherwise, so a listing that was never
read by the photo pass still gets a profile. The result lives in `listing_profiles`
and `listing_persona_profiles`, keyed by the listing, with the model and the
prompt version; a changed prompt writes again. Writing is explicit (`POST
.../profile`, or the backfill); opening a listing page never calls the model.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Listing, ListingCityData, ListingInvestment, ListingPersonaProfile, ListingPhoto, ListingProfile, LotAnalysisCache
from app.photos import sheet
from app.similar import embed as embedder
from app.zoning import answer as llm

PROMPT_VERSION = 1
MAX_PHOTOS = 8  # sent to the model when the listing has no photo labels
PHOTO_MAX_PX = 800  # enough to judge finishes; 8 photos at this size are about 1 MB as data URLs
MAX_TOKENS = 3000
DESCRIPTION_CHARS = 2500
MEDIAN_MIN_COUNT = 5  # a community median needs this many comparable listings, else the city's
# Text-and-vision models per provider. The profile call sends photos, so it needs a vision model.
DEFAULT_MODELS = {
    "openrouter": "nvidia/nemotron-3.5-super-vl:free",
    "nvidia": "nvidia/nemotron-3.5-super-vl",
    "anthropic": "claude-opus-5-5",
}

Persona = Literal["first_time_buyer", "investor", "flipper", "builder"]
PERSONAS: tuple[Persona, ...] = ("first_time_buyer", "investor", "flipper", "builder")
PERSONA_LABELS: dict[str, str] = {
    "first_time_buyer": "First-time buyer",
    "investor": "Investor",
    "flipper": "Flipper",
    "builder": "Builder",
}


# -- what the model returns ------------------------------------------------------------------------


class Facts(BaseModel):
    """The house in plain fields. Null means the sources did not say."""

    era: str | None = Field(None, description="When the house was built, as a decade or a range: '1920s', '1950s to 1960s', '2015 or later'")
    style: str | None = Field(None, description="Building form and style in 2 to 5 words: 'detached 2-storey brick', 'semi-detached Victorian', 'condo tower 1-bed'")
    layout: str | None = Field(None, description="How the main floor flows: 'open plan', 'closed rooms', 'centre hall', 'side hall', 'bungalow', 'split level'")
    kitchen_finish: int | None = Field(None, description="1 original or worn, 2 dated, 3 plain but sound, 4 renovated, 5 high-end recent renovation")
    bath_finish: int | None = Field(None, description="Same scale as kitchen_finish")
    overall_condition: int | None = Field(None, description="1 needs major work, 2 tired, 3 lived-in and sound, 4 updated, 5 like new")
    renovation_era: str | None = Field(None, description="When the main finishes date from: 'original', '1990s', 'recent', 'mixed'")
    basement: Literal["finished", "partly_finished", "unfinished", "none", "unknown"] = "unknown"
    basement_suite: Literal["legal_unit", "apartment", "kitchenette", "none", "unknown"] = Field(
        "unknown", description="legal_unit only when the sources say legal or registered; apartment when there is a kitchen and bath; kitchenette when a bar or wet bar only"
    )
    separate_entrance: bool | None = Field(None, description="A door to the basement from outside, when the sources show or say it")
    outdoor: str | None = Field(None, description="Yard, deck, balcony, garage position, laneway, in one line of at most 20 words")
    light: str | None = Field(None, description="Natural light and orientation in at most 12 words, from the photos")
    summary: str = Field(description="3 to 5 plain sentences about the house as an agent would describe it: form, layout, condition, basement, outdoor. No address, no street name, no price.")


class PersonaView(BaseModel):
    score: int = Field(description="1 to 10 on this persona's rubric")
    pitch: str = Field(
        description="3 to 5 sentences in this persona's words about why this house fits or does not fit them. "
        "Facts only, each from the sources. No address, no street name, no dollar price (a comparison to the area median is fine)."
    )
    signals: list[str] = Field(description="3 to 6 short fact phrases that drove the score, e.g. 'legal basement apartment', '25 ft lot', 'kitchen renovated'")
    concerns: list[str] = Field(description="1 to 3 short fact phrases this persona would hold against the house; empty when none")


class Profile(BaseModel):
    facts: Facts
    first_time_buyer: PersonaView
    investor: PersonaView
    flipper: PersonaView
    builder: PersonaView


# -- the prompt --------------------------------------------------------------------------------------


RUBRICS = {
    "first_time_buyer": """First-time buyer: someone who will live here for 5 years or more, on a stretched budget.
Cares about: move-in condition, the monthly cost (price, tax, condo fees), bedrooms for a small household, a workable kitchen and bath, parking or transit, outdoor space, a quiet street, no big repairs ahead.
Score 9-10: updated throughout, nothing to do, a layout that works, sound building, no cost surprises.
Score 6-8: lived-in and sound, a few cosmetic jobs, or a strong home with one drawback (no parking, small yard, high fees).
Score 3-5: dated kitchen or bath, a layout that needs work, high fees or tax for what it is, or a basement that needs finishing to be useful.
Score 1-2: needs major work, a tear-down, a commercial mix, or a home whose cost is far out of line with what a first buyer gets.""",
    "investor": """Investor: someone who will rent it out and hold it, and lives on the numbers.
Cares about: rent per door, the number of doors, a legal or at least working basement apartment, a separate entrance, the cap rate and gross yield against the area, tenant demand, low fees, the potential to add a unit (garden suite, multiplex zoning, as-of-right units).
Score 9-10: 2 or more rentable units today, or a cap rate well above the area, with a clear path to more.
Score 6-8: one solid rental with a working suite or an obvious one to add, or a cap rate at the area's level with upside.
Score 3-5: a single unit at a thin yield, high condo fees, or a suite that would be costly to make work.
Score 1-2: a thin yield with no way to add a door, or costs that eat the rent.""",
    "flipper": """Flipper: someone who buys, renovates in 3 to 9 months, and sells.
Cares about: a price below the area median for the type, dated finishes on a sound structure, a layout that is cheap to open up, cosmetic work rather than structural, a resale ceiling in the area well above the buy plus the work, no heritage or permit complications.
Score 9-10: clearly dated inside, sound bones, priced below the area, in a street where renovated homes sell far higher.
Score 6-8: dated or mixed finishes with a plain path to a renovated sale, or a good spread with one complication.
Score 3-5: already renovated (no spread), or work that is structural or mechanical rather than cosmetic.
Score 1-2: fully renovated at the top of the area, a condo with nothing to change, or a tear-down.""",
    "builder": """Builder or heavy renovator: someone who will add storeys, sever the lot, build a garden or laneway suite, or build new.
Cares about: lot frontage and depth, lot area, zoning (zone category, height limit, as-of-right units), severance potential, garden suite potential, laneway access, coverage room left, heritage status, what nearby lots have done.
Score 9-10: severance likely, or a wide deep lot with garden suite room and multiplex zoning, nothing heritage, in an area where new builds sell.
Score 6-8: one clear path (garden suite, a storey, a fourplex) on a normal lot.
Score 3-5: a narrow or shallow lot with little room, or a condo or townhouse with a shared lot (builder has nothing to do).
Score 1-2: a condo apartment, a heritage property, or a lot already built to its limit.""",
}

SYSTEM = (
    """You write the profile of a house for sale in Toronto for a search tool, in 2 parts: the facts, and 4 views of the same house by 4 kinds of buyer.

Rules for the facts:
- Fill a field only from the sources given (listing text, rooms, photo labels or photos, city and lot data, investment estimate). Never invent a year, a count, a finish or a feature. Null when the sources do not say.
- Finishes and condition come from the photos or the photo labels first, then the listing text. A listing text says "renovated"; the photos say how much.
- `basement_suite` is legal_unit only when the sources say legal, registered or permitted. "In-law suite" with a kitchen and bath is apartment.

Rules for the 4 persona views:
- Score each persona on its rubric below, 1 to 10. The same house gets different scores for different personas; that is expected.
- `pitch` is 3 to 5 sentences in that persona's own words, about what they care about. Facts only, each from the sources. A first-time buyer's pitch talks about living there; an investor's about the doors, the rent and the yield; a flipper's about the spread and the work; a builder's about the lot and the zoning.
- Never write the address, the street name, the neighbourhood name or the dollar price in a pitch or a signal. Compare to the area median instead ("priced 12% below the area median for a house").
- `signals` are the 3 to 6 facts that drove the score, as short phrases. `concerns` are 1 to 3 facts that count against the house for this persona, or empty.
- No marketing words: no "stunning", "gorgeous", "must see", "rare". Plain words.

Rubrics:

"""
    + "\n\n".join(RUBRICS[p] for p in PERSONAS)
)


def _money(value: float | int | None) -> str:
    return f"${value:,.0f}" if value is not None else "not given"


def _rooms(listing: Listing) -> str:
    rooms = listing.rooms or []
    if not rooms:
        return "- none listed"
    return "\n".join(f"- {r.get('type') or 'Room'} ({r.get('level') or 'level not given'}, {r.get('dimension') or 'no size'})" for r in rooms)


def _listing_block(listing: Listing, median: tuple[float, str] | None) -> str:
    lines = [
        f"Type: {listing.property_type or 'not given'} / {listing.building_type or 'not given'} / {listing.ownership_type or 'not given'}",
        f"Price: {_money(listing.price)}",
    ]
    if median:
        value, scope = median
        pct = (listing.price - value) / value * 100
        lines.append(f"Area median for this type ({scope}): {_money(value)}; this listing is {pct:+.0f}% against it")
    lines += [
        f"Bedrooms: {listing.bedrooms_text or listing.bedrooms_total or 'not given'}; bathrooms: {listing.bathrooms if listing.bathrooms is not None else 'not given'}",
        f"Interior: {listing.sqft_min or '?'}-{listing.sqft_max or '?'} sq ft; storeys: {listing.stories or 'not given'}; lot (as listed): {listing.lot_size or 'not given'}",
        f"Parking: {listing.parking_spaces if listing.parking_spaces is not None else '?'} ({listing.parking_type or 'not given'})",
        f"Property tax: {_money(listing.tax_annual)} per year; maintenance fee: {_money(listing.maintenance_fee_monthly)} per month",
        f"Community: {listing.community or 'not given'}, {listing.city or ''}",
    ]
    text = " ".join((listing.description or "").split())
    if len(text) > DESCRIPTION_CHARS:
        text = text[:DESCRIPTION_CHARS] + " [...]"
    return "Listing facts:\n" + "\n".join(lines) + "\n\nListing text:\n" + (text or "none") + "\n\nListed rooms:\n" + _rooms(listing)


def _city_block(city: ListingCityData | None, lot: dict[str, Any] | None) -> str:
    if city is None and lot is None:
        return "City and lot data: none (outside the City of Toronto data, or not matched)"
    lines = []
    if city is not None:
        lines += [
            f"Zone: {city.zone_string or 'not given'} ({city.zone_category or '?'}); height limit {city.height_limit_m or '?'} m / {city.height_limit_storeys or '?'} storeys",
            f"Lot (city parcel): area {city.lot_area_m2 or '?'} m2, frontage {city.lot_frontage_m or '?'} m, depth {city.lot_depth_m or '?'} m",
            f"Heritage: {city.heritage_status or 'not on the register'}; former municipality: {city.former_municipality or '?'}",
        ]
    if lot:
        parcel = lot.get("parcel") or {}
        zoning = lot.get("zoning") or {}
        sev = lot.get("severance") or {}
        gs = lot.get("garden_suite") or {}
        cov = lot.get("coverage") or {}
        lines += [
            f"Lot analysis: corner lot {parcel.get('corner_lot')}; abuts a laneway {parcel.get('abuts_laneway')}; irregular {parcel.get('irregular')}",
            f"As-of-right units: {zoning.get('as_of_right_units') or '?'}; low-rise residential zone: {zoning.get('low_rise_residential')}",
            f"Severance verdict: {sev.get('verdict')}; split frontage {sev.get('split_frontage_m')} m; nearby median frontage {sev.get('nearby_median_frontage_m')} m",
            f"Garden suite verdict: {gs.get('verdict')}; max footprint {gs.get('max_footprint_m2')} m2; rear yard depth {gs.get('rear_yard_depth_m')} m",
            f"Coverage: {cov.get('coverage_pct')}% built, cap {cov.get('max_coverage_pct')}%, room for {cov.get('remaining_buildable_footprint_m2')} m2 more footprint",
        ]
    return "City and lot data:\n" + "\n".join(lines)


def _investment_block(inv: ListingInvestment | None) -> str:
    if inv is None:
        return "Investment estimate: none"
    lines = [
        f"Rent estimate: {_money(inv.rent_monthly)} per month ({inv.rent_source}); units: {inv.units}; {inv.rent_note}",
        f"Gross yield {inv.gross_yield_pct:.1f}%; cap rate {inv.cap_rate_pct:.1f}%; net operating income {_money(inv.noi_annual)} per year",
        f"Has a suite: {inv.has_suite}; suite potential: {inv.suite_potential}; separate entrance evidence: {inv.separate_entrance or 'none'}",
        f"Room for a bedroom: {inv.extra_bedroom_room or 'none'}; garden suite: {inv.garden_suite or '?'}; severance: {inv.severance or '?'}; multiplex zone: {inv.multiplex_zone}",
    ]
    if inv.suite_note:
        lines.append(f"Suite note: {inv.suite_note}")
    return "Investment estimate (Bayt's model, from TRREB rent averages and the listing):\n" + "\n".join(lines)


def _photo_block(labels: list[ListingPhoto]) -> str:
    rows = []
    for r in labels:
        f = r.facts or {}
        where = ", ".join(x for x in (f.get("level"), f.get("room")) if x)
        rows.append(f"#{r.photo_index + 1} {f.get('kind')} {('(' + where + ')') if where else ''}: {f.get('title')}. {f.get('caption')}")
    return "Photo labels (a vision model read each photo):\n" + "\n".join(rows)


def _median(session: Session, listing: Listing) -> tuple[float, str] | None:
    """The median price of the same building type in the community, or in the city when the community is thin."""
    for scope, where in (
        ("community", (Listing.community == listing.community, Listing.city == listing.city)),
        ("city", (Listing.city == listing.city,)),
    ):
        if scope == "community" and not listing.community:
            continue
        stmt = select(func.count(), func.percentile_cont(0.5).within_group(Listing.price)).where(
            Listing.building_type == listing.building_type, *where
        )
        count, median = session.execute(stmt).one()
        if count >= MEDIAN_MIN_COUNT and median:
            return float(median), f"{scope}, {count} listings"
    return None


def sources(session: Session, listing: Listing) -> tuple[str, list[str]]:
    """The user prompt and the photo URLs to send (empty when the listing has photo labels)."""
    city = session.get(ListingCityData, listing.id)
    lot_row = session.get(LotAnalysisCache, listing.id)
    inv = session.get(ListingInvestment, listing.id)
    labels = [
        r for r in session.scalars(select(ListingPhoto).where(ListingPhoto.listing_id == listing.id).order_by(ListingPhoto.photo_index)) if r.facts
    ]
    blocks = [
        _listing_block(listing, _median(session, listing)),
        _city_block(city, lot_row.result if lot_row else None),
        _investment_block(inv),
    ]
    images: list[str] = []
    if labels:
        blocks.append(_photo_block(labels))
    else:
        photos = listing.photos or []
        images = [p.get("high") or p.get("medium") or "" for p in photos[:MAX_PHOTOS]]
        images = [u for u in images if u]
        blocks.append(f"Photos: {len(images)} of the listing's {len(photos)} photos are attached, in listing order (the front of the house first, usually)." if images else "Photos: none")
    return "\n\n".join(blocks) + "\n\nWrite the facts and the 4 persona views.", images


def attach(urls: list[str]) -> list[str]:
    """The photos as JPEG data URLs: the free vision hosts take bytes, not URLs, and a URL can come back stale."""
    out = []
    for img in sheet.fetch_all(urls):
        if img is not None:
            out.append(sheet.photo_data_url(img, max_px=PHOTO_MAX_PX))
    return out


# -- keeping the answer honest -----------------------------------------------------------------------


def _clamp(value: int | None, lo: int, hi: int) -> int | None:
    if value is None:
        return None
    return max(lo, min(hi, int(value)))


def _scrub(text: str, listing: Listing) -> str:
    """Drop the address and the street name from a pitch, so location stays out of the vector."""
    out = text
    for raw in (listing.address, listing.community):
        if not raw:
            continue
        out = re.sub(re.escape(raw.strip()), "the property" if raw == listing.address else "the area", out, flags=re.I)
        street = re.sub(r"^\s*\d+[A-Za-z]?\s+", "", raw.strip())
        if street and street != raw.strip() and len(street) > 4:
            out = re.sub(re.escape(street), "the street", out, flags=re.I)
    return out


def clean(profile: Profile, listing: Listing) -> Profile:
    facts = profile.facts.model_copy(
        update={
            "kitchen_finish": _clamp(profile.facts.kitchen_finish, 1, 5),
            "bath_finish": _clamp(profile.facts.bath_finish, 1, 5),
            "overall_condition": _clamp(profile.facts.overall_condition, 1, 5),
            "summary": _scrub(profile.facts.summary.strip(), listing),
        }
    )
    views = {}
    for p in PERSONAS:
        v: PersonaView = getattr(profile, p)
        views[p] = v.model_copy(
            update={
                "score": _clamp(v.score, 1, 10) or 1,
                "pitch": _scrub(" ".join(v.pitch.split()), listing),
                "signals": [_scrub(s.strip(), listing) for s in v.signals if s.strip()][:6],
                "concerns": [_scrub(s.strip(), listing) for s in v.concerns if s.strip()][:3],
            }
        )
    return Profile(facts=facts, **views)


# -- response shapes ---------------------------------------------------------------------------------


class PersonaOut(BaseModel):
    persona: str
    label: str
    score: int
    pitch: str
    signals: list[str]
    concerns: list[str]
    embedded: bool = Field(description="True once the pitch has an embedding and can be searched")


class ListingProfileOut(BaseModel):
    listing_id: str
    model: str | None = Field(description="The model that wrote the profile; null when none is configured or nothing is written")
    prompt_version: int | None
    facts: Facts | None = Field(None, description="Null when not written yet or the model gave nothing usable")
    personas: list[PersonaOut]
    note: str | None
    computed_at: datetime | None


# -- reading and writing -----------------------------------------------------------------------------


def model_name() -> str:
    if settings.profile_model:
        return settings.profile_model
    p = llm.resolve_provider()
    return DEFAULT_MODELS.get(p.name, "") if p else ""


def make_client() -> llm.Backend | None:
    # Plain JSON mode: the schema-constrained mode stalls the Nemotron vision model (see OpenAIBackend).
    return llm.make_client(model_name() or None, json_mode="object")


def persona_rows(session: Session, listing_id: str) -> dict[str, ListingPersonaProfile]:
    rows = session.scalars(select(ListingPersonaProfile).where(ListingPersonaProfile.listing_id == listing_id)).all()
    return {r.persona: r for r in rows}


def profile_for(session: Session, listing: Listing) -> ListingProfileOut:
    """The stored profile, without calling the model."""
    row = session.get(ListingProfile, listing.id)
    views = persona_rows(session, listing.id)
    return ListingProfileOut(
        listing_id=listing.id,
        model=row.model if row else (model_name() or None),
        prompt_version=row.prompt_version if row else None,
        facts=Facts.model_validate(row.facts) if row and row.facts else None,
        personas=[
            PersonaOut(
                persona=p,
                label=PERSONA_LABELS[p],
                score=v.score,
                pitch=v.pitch,
                signals=list(v.signals or []),
                concerns=list(v.concerns or []),
                embedded=v.embedding is not None,
            )
            for p in PERSONAS
            if (v := views.get(p)) is not None
        ],
        note=row.note if row else "not written yet",
        computed_at=row.computed_at if row else None,
    )


def is_current(row: ListingProfile | None) -> bool:
    return row is not None and row.facts is not None and row.prompt_version == PROMPT_VERSION


def write_profile(
    session: Session,
    listing: Listing,
    client: llm.Backend | None = None,
    *,
    force: bool = False,
    embed: bool = True,
    embed_client: embedder.EmbeddingClient | None = None,
) -> ListingProfileOut:
    """Write the profile when it is missing or stale (or always, with `force`), store it, then embed the pitches."""
    client = client or make_client()
    if client is None:
        raise llm.ModelUnavailable("LLM_API_KEY is not set")
    row = session.get(ListingProfile, listing.id)
    if not force and is_current(row):
        if embed:
            embedder.embed_listing(session, listing.id, embed_client)
        return profile_for(session, listing)
    user, images = sources(session, listing)
    note: str | None = None
    profile: Profile | None = None
    try:
        attached = attach(images) if images else []
        out = client.structured(system=SYSTEM, user=user, schema=Profile, effort="low", max_tokens=MAX_TOKENS, images=attached or None)
        profile = clean(out, listing)  # type: ignore[arg-type]
    except llm.ModelUnavailable as exc:
        note = str(exc)
    if row is None:
        row = ListingProfile(listing_id=listing.id)
        session.add(row)
    row.model = client.model
    row.prompt_version = PROMPT_VERSION
    row.facts = profile.facts.model_dump() if profile else None
    row.note = note
    row.computed_at = func.now()  # a repeat failure with the same note changes nothing else, so stamp the time by hand
    if profile is not None:
        views = persona_rows(session, listing.id)
        for p in PERSONAS:
            v: PersonaView = getattr(profile, p)
            r = views.get(p)
            if r is None:
                r = ListingPersonaProfile(listing_id=listing.id, persona=p)
                session.add(r)
            r.score, r.pitch, r.signals, r.concerns = v.score, v.pitch, v.signals, v.concerns
            r.embedding, r.embed_model = None, None
    session.commit()
    if profile is not None and embed:
        embedder.embed_listing(session, listing.id, embed_client)
    return profile_for(session, listing)
