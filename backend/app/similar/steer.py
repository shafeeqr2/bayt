"""Steering the similar-homes answer: the buyer says what to change, and which facets count.

Two controls on the similar row. Both feed the pipeline in `service`; neither needs a
new model or new embeddings.

- **Text: "like this, but...".** "Bigger backyard", "same kitchen, any neighbourhood",
  "closer to the subway". One model call rewrites the source's persona pitch with the
  change applied: the pitch of the house the buyer is asking for, in the same voice and
  about the same length, with no address or price. That text is embedded and the
  nearest-neighbour search runs from it instead of from the source's own vector. The
  rerank call then gets the ask as a constraint, so a candidate that delivers the change
  ranks higher and its reason says how. The rewrite and its vector are cached with the
  answer, so a repeat visit costs nothing.
- **Facets.** 5 chips: layout, finish, lot, location, money. All on by default. A chip
  turned off drops that facet from the comparison: the rerank prompt lists the active
  ones and tells the model to ignore the rest. Location and money are also the two hard
  filters (5 km; the price band), so turning one off drops its filter too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.models import Listing, ListingPersonaProfile
from app.similar import profile as hp
from app.zoning import answer as llm

MAX_TEXT = 200
MAX_TOKENS = 600
RETRY_ONCE = ("HTTP 502", "HTTP 503", "HTTP 504", "ReadError", "ReadTimeout", "RemoteProtocolError")  # the free hosts drop a call now and then

FACETS = ("layout", "finish", "lot", "location", "money")
FACET_LABELS = {"layout": "Layout", "finish": "Finish", "lot": "Lot", "location": "Location", "money": "Money"}
FACET_SCOPE = {
    "layout": "bedrooms, bathrooms, storeys, room flow, basement, suites and separate entrances",
    "finish": "kitchen and bath finish, overall condition, renovation era, what work it needs",
    "lot": "lot size and frontage, outdoor space, parking, zoning and what can be built",
    "location": "distance and neighbourhood (the 5 km filter)",
    "money": "price against the area, rent, yield, carrying cost and the spread (the price band filter)",
}


@dataclass(frozen=True)
class Steering:
    """What the buyer asked to change, and which facets are on. The default is no text and every facet."""

    text: str | None = None
    facets: tuple[str, ...] = field(default=FACETS)

    @property
    def off(self) -> tuple[str, ...]:
        return tuple(f for f in FACETS if f not in self.facets)

    @property
    def is_default(self) -> bool:
        return self.text is None and not self.off

    def key(self) -> dict[str, Any]:
        return {"text": self.text, "facets": list(self.facets)}


DEFAULT = Steering()


def parse(text: str | None, facets: str | None) -> Steering:
    """Query parameters to a `Steering`. Raises ValueError on an unknown facet or no facet at all."""
    clean = " ".join((text or "").split())[:MAX_TEXT] or None
    if facets is None:
        return Steering(text=clean)
    picked = tuple(f for f in FACETS if f in {p.strip().lower() for p in facets.split(",")})
    unknown = {p.strip().lower() for p in facets.split(",") if p.strip()} - set(FACETS)
    if unknown:
        raise ValueError(f"unknown facet {sorted(unknown)[0]!r}; the facets are {', '.join(FACETS)}")
    if not picked:
        raise ValueError("at least 1 facet must be on")
    return Steering(text=clean, facets=picked)


def ask(client: llm.Backend, *, system: str, user: str, schema: type[BaseModel], max_tokens: int) -> BaseModel:
    """One structured call, tried twice when the host drops the connection."""
    try:
        return client.structured(system=system, user=user, schema=schema, effort="low", max_tokens=max_tokens)
    except llm.ModelUnavailable as exc:
        if not any(w in str(exc) for w in RETRY_ONCE):
            raise
        return client.structured(system=system, user=user, schema=schema, effort="low", max_tokens=max_tokens)


# -- the rewrite -------------------------------------------------------------------------------------


class Rewrite(BaseModel):
    pitch: str = Field(description="The pitch of the house the buyer is asking for: the source pitch with the change applied, same voice, 3 to 5 sentences")
    signals: list[str] = Field(description="3 to 6 short facts that house would have, the changed ones first")


REWRITE_SYSTEM = """You rewrite a house pitch for one kind of buyer, with one change the buyer asked for.

You get the pitch and signals of a house the buyer likes, and the buyer's words on what to change. Write the pitch of the house they are asking for: keep everything they did not ask to change, apply the change plainly, and keep the voice, the length and the kind of facts the same, so the new pitch reads like the others in the same catalogue.

Rules:
- Apply the change as a fact of the house ("a 60 ft lot with a deep, fenced yard"), not as a wish ("the buyer wants a bigger yard").
- Keep what was not mentioned. Do not invent new selling points beyond the change.
- No street name, no neighbourhood name, no dollar price, no distances in minutes. Where the ask is about location, say the kind of place ("steps to a subway station"), not the name.
- Plain words. No marketing words."""


def rewrite_prompt(source: ListingPersonaProfile, facts: dict[str, Any] | None, text: str) -> str:
    rubric = hp.RUBRICS[source.persona].split("\n", 1)[0]
    return (
        f"Buyer: {rubric}\n\n"
        f"House the buyer likes:\n  summary: {(facts or {}).get('summary') or ''}\n  pitch: {source.pitch}\n  signals: {'; '.join(source.signals or [])}\n\n"
        f"The buyer says: \"{text}\"\n\n"
        "Write the pitch and signals of the house they are asking for."
    )


def rewrite(client: llm.Backend, listing: Listing, source: ListingPersonaProfile, facts: dict[str, Any] | None, text: str) -> tuple[str, list[str]]:
    """The rewritten pitch and signals, scrubbed of the address like a stored pitch; raises ModelUnavailable on failure."""
    out = ask(client, system=REWRITE_SYSTEM, user=rewrite_prompt(source, facts, text), schema=Rewrite, max_tokens=MAX_TOKENS)
    assert isinstance(out, Rewrite)
    pitch = hp._scrub(" ".join(out.pitch.split()), listing)
    signals = [hp._scrub(s.strip(), listing) for s in out.signals if s.strip()][:6]
    if not pitch:
        raise llm.ModelUnavailable("the model returned an empty pitch")
    return pitch, signals


def facet_block(steering: Steering) -> str:
    """The lines the rerank prompt gets about the facets and the ask."""
    on = ", ".join(f"{f} ({FACET_SCOPE[f]})" for f in steering.facets)
    lines = [f"Compare on: {on}."]
    if steering.off:
        lines.append(f"Ignore: {', '.join(steering.off)}. Do not use these in the ranking or the reasons.")
    if steering.text:
        lines.append(f"The buyer asked for a change: \"{steering.text}\". Rank candidates that deliver it first, and say in their reason how they do. For everything else, the source house is the reference.")
    return "\n".join(lines)
