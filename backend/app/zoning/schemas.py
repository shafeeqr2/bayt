"""Response shapes for the zoning pathways endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.zoning.intent import Intent

DISCLAIMER = (
    "This is a research summary of public zoning rules and past decisions for 1 parcel. "
    "It is not legal advice and it does not predict a decision. Confirm every number with "
    "a zoning review from Toronto Building and with a licensed professional."
)


class GapOut(BaseModel):
    standard: str
    label: str
    kind: Literal["min", "max"]
    unit: str
    required: float | None
    required_status: Literal["known", "unknown", "not_applicable"]
    proposed: float | None
    proposed_source: Literal["intent", "existing", "derived"] | None
    existing: float | None
    status: Literal["complies", "short", "unknown", "not_applicable"]
    existing_status: Literal["complies", "short", "unknown", "not_applicable"]
    delta: float | None = Field(None, description="Relief the proposal needs; positive when short")
    relief_pct: float | None
    clause_ids: list[str]
    source_url: str | None
    note: str | None


class LegalBasisOut(BaseModel):
    clause: str
    says: str
    url: str | None


class CandidateOut(BaseModel):
    card_id: str
    name: str
    category: str
    result: Literal["applies", "may_apply"] = Field(description="may_apply = a fact the trigger needs is missing")
    summary: str
    decision_body: str
    covers_gaps: list[str] = Field(description="Standards the proposal is short on that this pathway addresses")
    missing_facts: list[str]
    why: list[str] = Field(description="The trigger conditions that held, in the card's own words")
    legal_basis: list[LegalBasisOut]
    mechanics: list[str]
    risks: list[str]
    questions: list[str] = Field(description="Buyer mode: questions for the lawyer, agent or builder. Professional mode: what to check next")
    cost_band: str
    time_band: str
    score: int


class PathwayAnalysis(BaseModel):
    mode: Literal["buyer", "professional"]
    intent: Intent
    zone_label: str | None
    zone: str | None
    gaps: list[GapOut]
    short_standards: list[str]
    unknown_standards: list[str]
    candidates: list[CandidateOut]
    missing_facts: list[str] = Field(description="Facts that would turn a may_apply into applies or drops it")
    caveats: list[str]
    playbook_version: str
    disclaimer: str = DISCLAIMER
    computed_at: datetime
