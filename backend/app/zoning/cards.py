"""Playbook cards: hand-written legal pathways, loaded from YAML and matched by predicate.

A card is reviewed by a person before it ships. The loader refuses a card whose
trigger reads a fact that does not exist, that has no risk, or that has no legal
basis, so a bad card fails at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from app.zoning import predicate
from app.zoning.facts import FACT_PATHS
from app.zoning.standards import STANDARDS

PLAYBOOK_DIR = Path(__file__).parent / "playbook"

Category = Literal[
    "legal_non_conforming",
    "as_of_right",
    "minor_variance",
    "consent",
    "rezoning",
    "appeal",
    "constraint",  # not a pathway: a fact the answer must state
]
CostBand = Literal["none", "low", "medium", "high", "very_high"]
TimeBand = Literal["weeks", "months", "half_year", "year_plus"]


class LegalBasis(BaseModel):
    clause: str = Field(description="Clause id, e.g. 10.20.40.70(3) or 'Planning Act s.45(1)'")
    says: str = Field(description="What the clause does, in 1 sentence")
    url: str | None = None


class StrategyCard(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    name: str
    category: Category
    summary: str
    decision_body: str
    covers: list[str] = Field(default_factory=list, description="Standards this pathway can remove a gap on")
    trigger: Any
    legal_basis: list[LegalBasis] = Field(min_length=1)
    mechanics: list[str] = Field(min_length=1)
    risks: list[str] = Field(min_length=1, description="Mandatory. The answer must show these every time")
    buyer_questions: list[str] = Field(default_factory=list, description="Buyer mode: what to ask the lawyer, agent or builder")
    professional_notes: list[str] = Field(default_factory=list, description="Professional mode: what to check next")
    cost_band: CostBand
    time_band: TimeBand
    precedent_work_types: list[str] = Field(default_factory=list, description="Committee of Adjustment WORK_TYPE values to pull as precedents")
    version: int = 1

    @field_validator("covers")
    @classmethod
    def _known_standards(cls, v: list[str]) -> list[str]:
        bad = [s for s in v if s not in STANDARDS]
        if bad:
            raise ValueError(f"unknown standards in covers: {bad}")
        return v

    @field_validator("trigger")
    @classmethod
    def _valid_trigger(cls, v: Any) -> Any:
        pred = predicate.parse(v)
        bad = sorted(predicate.paths(pred) - set(FACT_PATHS))
        if bad:
            raise ValueError(f"trigger reads unknown facts: {bad}")
        return v

    @property
    def predicate(self) -> predicate.Predicate:
        return predicate.parse(self.trigger)


COST_PENALTY = {"none": 0, "low": 0, "medium": 1, "high": 3, "very_high": 5}


@dataclass
class Candidate:
    card: StrategyCard
    result: predicate.Truth  # TRUE or UNKNOWN (FALSE cards are dropped)
    missing: list[str]
    covers_gaps: list[str]  # standards the proposal is short on that this card addresses
    passed: list[str]
    score: int
    why: list[str] = field(default_factory=list)


def load_cards(directory: Path = PLAYBOOK_DIR) -> list[StrategyCard]:
    cards: list[StrategyCard] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        with path.open() as fh:
            data = yaml.safe_load(fh)
        card = StrategyCard.model_validate(data)
        if card.id in seen:
            raise ValueError(f"duplicate card id {card.id} in {path.name}")
        seen.add(card.id)
        cards.append(card)
    if not cards:
        raise ValueError(f"no cards found in {directory}")
    return cards


@lru_cache(maxsize=1)
def playbook() -> list[StrategyCard]:
    return load_cards()


def playbook_version() -> str:
    """Changes whenever a card file changes; part of the answer cache key."""
    import hashlib

    h = hashlib.sha256()
    for path in sorted(PLAYBOOK_DIR.glob("*.yaml")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()[:12]


def match(facts: dict[str, Any], cards: list[StrategyCard] | None = None) -> list[Candidate]:
    """Every card whose trigger is TRUE or UNKNOWN, best first."""
    short = {k.split(".")[1] for k, v in facts.items() if k.startswith("gap.") and k.endswith(".status") and v == "short"}
    out: list[Candidate] = []
    for card in cards or playbook():
        ev = predicate.evaluate(card.predicate, facts)
        if ev.result is predicate.Truth.FALSE:
            continue
        covers = [s for s in card.covers if s in short]
        score = 10 * len(covers) + (5 if ev.result is predicate.Truth.TRUE else 0) - COST_PENALTY[card.cost_band]
        if card.category == "constraint" and ev.result is predicate.Truth.TRUE:
            score += 20  # a confirmed constraint sits above every pathway: the answer must state it first
        why = list(ev.passed)
        if ev.missing:
            why.append("needs: " + ", ".join(sorted(set(ev.missing))))
        out.append(Candidate(card, ev.result, sorted(set(ev.missing)), covers, ev.passed, score, why))
    out.sort(key=lambda c: (-c.score, c.card.id))
    return out
