"""Pure pathway analysis: gaps -> facts -> card match -> response. No I/O, no database.

`service.py` wraps this with the lot analysis and the city data lookups.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from app.lot.schemas import LotAnalysis
from app.zoning import cards as playbook
from app.zoning.facts import build_facts
from app.zoning.gaps import analyze_gaps
from app.zoning.intent import Intent
from app.zoning.predicate import Truth
from app.zoning.schemas import CandidateOut, GapOut, LegalBasisOut, PathwayAnalysis


def analyze_pathways(
    lot: LotAnalysis,
    intent: Intent,
    *,
    height_limit_m: float | None = None,
    height_limit_storeys: int | None = None,
    overlay_checked: bool = False,
    heritage_listed: bool | None = None,
) -> PathwayAnalysis:
    gaps = analyze_gaps(lot, intent, height_limit_m=height_limit_m, height_limit_storeys=height_limit_storeys, overlay_checked=overlay_checked)
    facts = build_facts(lot, intent, gaps, heritage_listed=heritage_listed)
    candidates = playbook.match(facts)

    caveats = list(lot.caveats)
    if not lot.zoning.low_rise_residential:
        caveats.insert(0, f"Zone {lot.zoning.zone or 'unknown'} is outside the low-rise residential chapter; standards were not resolved.")
    if lot.zoning.has_site_exception:
        caveats.insert(0, "The zone carries a site-specific exception. Its text was not read; any standard may differ.")
    if not overlay_checked:
        caveats.append("The Height Overlay Map was not read; height uses the 10.0 m default and the storey limit is unknown.")
    if lot.envelope is None and any(b.is_main for b in lot.buildings):
        caveats.append("The existing building's position is not in this cached lot analysis; refresh it to judge the alteration pathways.")
    elif lot.envelope is None:
        caveats.append("No main building found, so existing setbacks are unknown and the alteration pathways cannot be judged.")

    missing: set[str] = set()
    outs: list[CandidateOut] = []
    for c in candidates:
        missing.update(c.missing)
        card = c.card
        outs.append(
            CandidateOut(
                card_id=card.id,
                name=card.name,
                category=card.category,
                result="applies" if c.result is Truth.TRUE else "may_apply",
                summary=card.summary.strip(),
                decision_body=card.decision_body,
                covers_gaps=c.covers_gaps,
                missing_facts=c.missing,
                why=c.why,
                legal_basis=[LegalBasisOut(clause=b.clause, says=b.says, url=b.url) for b in card.legal_basis],
                mechanics=card.mechanics,
                risks=card.risks,
                questions=card.buyer_questions if intent.mode == "buyer" else card.professional_notes,
                cost_band=card.cost_band,
                time_band=card.time_band,
                score=c.score,
            )
        )

    return PathwayAnalysis(
        mode=intent.mode,
        intent=intent,
        zone_label=lot.zoning.zone_label,
        zone=lot.zoning.zone,
        gaps=[GapOut(**asdict(g)) for g in gaps],
        short_standards=[g.standard for g in gaps if g.status == "short"],
        unknown_standards=[g.standard for g in gaps if g.status == "unknown"],
        candidates=outs,
        missing_facts=sorted(missing),
        caveats=caveats,
        playbook_version=playbook.playbook_version(),
        computed_at=datetime.now(timezone.utc),
    )

