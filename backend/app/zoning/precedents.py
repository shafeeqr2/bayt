"""Committee of Adjustment precedents near a point.

`nearby` reads `city.coa_applications` (built by `app.city.coa`). Everything
else is pure: `summarize` counts outcomes, `for_card` picks the applications a
strategy card calls comparable (by WORK_TYPE and by words in the description).

A precedent is a record of what a neighbour asked for and what the committee
decided. It is not a prediction: the open data has the decision and the
description, not the variance table, so "approved" says the file was approved,
not that a variance of the same size was.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

if TYPE_CHECKING:  # cards -> facts -> precedents would otherwise be a cycle
    from app.zoning.cards import StrategyCard

DATASET_URL = "https://open.toronto.ca/dataset/committee-of-adjustment-applications/"
DEFAULT_RADIUS_M = 500
MAX_RADIUS_M = 2000
MAX_ITEMS = 1500  # midtown has ~400 files within 500 m; the cap only guards the response size
EXAMPLES_PER_CARD = 5

Outcome = Literal["approved", "refused", "withdrawn", "deferred", "pending", "unknown"]


class Precedent(BaseModel):
    sys_id: str
    reference_file: str | None
    application_type: Literal["MV", "CO"] | None = Field(description="MV = minor variance, CO = consent")
    work_type: str | None
    sub_type: str | None
    description: str | None
    zoning_designation: str | None
    address: str | None
    planning_district: str | None
    in_date: date | None
    hearing_date: date | None
    decision: str = Field(description="approved | approved_with_conditions | approved_in_part | refused | withdrawn | deferred | pending | unknown")
    decision_raw: str | None
    appeal: str | None = Field(description="approved | refused | dismissed | pending | unknown, or null without an appeal")
    appeal_body: str | None
    outcome: Outcome
    status: str | None
    distance_m: float
    lat: float
    lon: float


class PrecedentSummary(BaseModel):
    total: int
    approved: int
    refused: int
    withdrawn: int
    deferred: int
    pending: int
    unknown: int
    approval_rate: float | None = Field(None, description="approved / (approved + refused); null with no decided file")
    appealed: int = Field(0, description="Files with any appeal on record")
    by_work_type: dict[str, int]
    oldest_hearing: date | None
    newest_hearing: date | None


class CardPrecedents(BaseModel):
    """What the committee did with comparable files near this lot, for one strategy card."""

    work_types: list[str]
    keywords: list[str]
    summary: PrecedentSummary
    examples: list[Precedent] = Field(description="Most recent decided files first")


class PrecedentSearch(BaseModel):
    lat: float
    lon: float
    radius_m: int
    work_type: str | None
    query: str | None
    summary: PrecedentSummary
    items: list[Precedent] = Field(description="Nearest first")
    truncated: bool = Field(False, description="True when more files exist in the radius than the response holds")
    source_url: str = DATASET_URL
    note: str = (
        "Toronto Open Data, Committee of Adjustment Applications. Each file is placed on the city address "
        "point for its street address. The data has the decision and the description, not the variance table."
    )


_SELECT = f"""
SELECT sys_id, reference_file, application_type, work_type, sub_type, description, zoning_designation,
       address_full AS address, planning_district, in_date, hearing_date,
       decision, decision_raw, appeal, appeal_body, outcome, status,
       ST_Distance(geom::geography, pt.g) AS distance_m, ST_Y(geom) AS lat, ST_X(geom) AS lon
FROM city.coa_applications, (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS g) pt
WHERE geom IS NOT NULL
  AND ST_DWithin(geom::geography, pt.g, :radius_m)
  AND (CAST(:work_type AS text) IS NULL OR work_type = CAST(:work_type AS text))
  AND (CAST(:query AS text) IS NULL OR description ILIKE '%' || CAST(:query AS text) || '%')
ORDER BY distance_m, hearing_date DESC NULLS LAST
LIMIT {MAX_ITEMS}
"""


def loaded(session: Session) -> bool:
    return bool(session.scalar(text("SELECT to_regclass('city.coa_applications') IS NOT NULL")))


def nearby(
    session: Session,
    lat: float,
    lon: float,
    radius_m: int = DEFAULT_RADIUS_M,
    *,
    work_type: str | None = None,
    query: str | None = None,
) -> list[Precedent]:
    radius_m = max(50, min(int(radius_m), MAX_RADIUS_M))
    rows = session.execute(
        text(_SELECT),
        {"lat": lat, "lon": lon, "radius_m": radius_m, "work_type": work_type or None, "query": (query or "").strip() or None},
    ).mappings()
    return [Precedent(**{**row, "distance_m": round(row["distance_m"], 1)}) for row in rows]


def summarize(items: list[Precedent]) -> PrecedentSummary:
    counts = {k: 0 for k in ("approved", "refused", "withdrawn", "deferred", "pending", "unknown")}
    by_work: dict[str, int] = {}
    dates: list[date] = []
    appealed = 0
    for p in items:
        counts[p.outcome] = counts.get(p.outcome, 0) + 1
        by_work[p.work_type or "Unknown"] = by_work.get(p.work_type or "Unknown", 0) + 1
        if p.hearing_date:
            dates.append(p.hearing_date)
        if p.appeal:
            appealed += 1
    decided = counts["approved"] + counts["refused"]
    return PrecedentSummary(
        total=len(items),
        **counts,
        approval_rate=round(counts["approved"] / decided, 2) if decided else None,
        appealed=appealed,
        by_work_type=dict(sorted(by_work.items(), key=lambda kv: -kv[1])),
        oldest_hearing=min(dates) if dates else None,
        newest_hearing=max(dates) if dates else None,
    )


def has_keyword(p: Precedent, card: StrategyCard) -> bool:
    if not card.precedent_keywords or not p.description:
        return False
    text_ = p.description.lower()
    return any(k.lower() in text_ for k in card.precedent_keywords)


def matches_card(p: Precedent, card: StrategyCard) -> bool:
    """A file is comparable when its WORK_TYPE is one the card names or its description has a card keyword."""
    if card.precedent_work_types and p.work_type and p.work_type.lower() in {w.lower() for w in card.precedent_work_types}:
        return True
    return has_keyword(p, card)


def for_card(items: list[Precedent], card: StrategyCard) -> CardPrecedents | None:
    """None when the card names no comparable work; otherwise the comparable files and their counts."""
    if not card.precedent_work_types and not card.precedent_keywords:
        return None
    comparable = [p for p in items if matches_card(p, card)]
    # Examples: files whose description has a card keyword first (they are the closest match), then the most recent.
    decided = sorted(
        (p for p in comparable if p.outcome in ("approved", "refused")),
        key=lambda p: (has_keyword(p, card), p.hearing_date or date.min, -p.distance_m),
        reverse=True,
    )
    return CardPrecedents(
        work_types=card.precedent_work_types,
        keywords=card.precedent_keywords,
        summary=summarize(comparable),
        examples=decided[:EXAMPLES_PER_CARD],
    )
