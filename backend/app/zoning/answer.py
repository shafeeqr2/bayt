"""Phase 2: the model reads free text into the intent, and writes a cited answer from the analysis.

Two calls to Claude, both with structured output so the shape is fixed:

1. `parse_intent`: the buyer's own words -> the fields of `Intent`. The model may
   only fill fields the text supports; a number it did not read stays None.
   Form fields the person typed override what the model read.
2. `write_answer`: the deterministic `PathwayAnalysis` -> a short written answer.
   Every paragraph cites what it rests on: a card (`card:<id>`), a by-law clause
   (`clause:<id>`), a gap row (`gap:<standard>`) or a nearby file (`file:<ref>`).
   `check_citations` drops every paragraph whose citations do not all resolve to
   something in the analysis. The model never adds a rule, a number or a file.

Without credentials (`LLM_API_KEY`), both calls raise `ModelUnavailable`
and the endpoint returns the deterministic analysis alone.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Protocol

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.zoning.intent import Intent, Mode
from app.zoning.schemas import PathwayAnalysis

PROMPT_VERSION = 1  # bump when a prompt or an output schema changes; it keys the answer cache

NUMERIC_FIELDS = (
    "proposed_units",
    "proposed_storeys",
    "proposed_height_m",
    "proposed_gfa_m2",
    "proposed_footprint_m2",
    "proposed_building_depth_m",
    "proposed_building_length_m",
    "proposed_front_setback_m",
    "proposed_side_setback_m",
    "proposed_rear_setback_m",
)


class ModelUnavailable(RuntimeError):
    """No credentials, a refusal, or an API failure; the caller falls back to the deterministic answer."""


# -- output schemas (plain types only: structured output rejects numeric bounds) ----


class ParsedIntent(BaseModel):
    """What the model read in the person's words. Null means the text did not say."""

    project: str | None = Field(None, description="addition | new_build | convert | garden_suite | laneway_suite | sever | null")
    keep_existing_walls: bool | None = Field(None, description="true when the main walls stay (alteration), false for a tear-down")
    sever_lot: bool | None = None
    proposed_units: int | None = None
    proposed_storeys: int | None = None
    proposed_height_m: float | None = None
    proposed_gfa_m2: float | None = Field(None, description="Gross floor area of all floors in square metres")
    proposed_footprint_m2: float | None = None
    proposed_building_depth_m: float | None = None
    proposed_building_length_m: float | None = None
    proposed_front_setback_m: float | None = None
    proposed_side_setback_m: float | None = Field(None, description="The smaller side yard in metres")
    proposed_rear_setback_m: float | None = None
    understood: list[str] = Field(default_factory=list, description="One short line per fact read from the text, in the person's units")
    unclear: list[str] = Field(default_factory=list, description="Things the text mentions that no field can hold")


class Paragraph(BaseModel):
    text: str
    citations: list[str] = Field(description="card:<id> | clause:<id> | gap:<standard> | file:<reference>; at least 1")


class Section(BaseModel):
    heading: str
    paragraphs: list[Paragraph]


class Draft(BaseModel):
    headline: str = Field(description="One sentence: can the plan go ahead, and by which route")
    sections: list[Section]
    questions: list[str] = Field(description="Buyer mode: for the lawyer, agent or builder. Professional mode: what to check next")
    unknowns: list[str] = Field(description="Facts the analysis lacked, in plain words")


class Answer(BaseModel):
    headline: str
    sections: list[Section]
    questions: list[str]
    unknowns: list[str]
    dropped: list[str] = Field(default_factory=list, description="Paragraphs removed by the citation check, with the reason")
    model: str
    prompt_version: int = PROMPT_VERSION


# -- client -------------------------------------------------------------------


class ParseClient(Protocol):
    """The slice of `anthropic.Anthropic` this module uses, so tests can pass a fake."""

    @property
    def messages(self) -> Any: ...


def make_client() -> ParseClient | None:
    """A real client when credentials exist, else None."""
    if not settings.llm_api_key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=settings.llm_api_key)


def _call(client: ParseClient | None, *, system: str, user: str, output_format: type[BaseModel], effort: str, max_tokens: int) -> BaseModel:
    if client is None:
        raise ModelUnavailable("LLM_API_KEY is not set")
    try:
        import anthropic
    except ImportError:  # pragma: no cover - the fake client in tests needs no SDK
        anthropic = None
    try:
        response = client.messages.parse(
            model=settings.zoning_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=output_format,
            output_config={"effort": effort},
        )
    except Exception as exc:  # noqa: BLE001 - mapped to one failure the endpoint reports
        if anthropic is not None and isinstance(exc, anthropic.AuthenticationError):
            raise ModelUnavailable("the API key was rejected") from exc
        if anthropic is not None and isinstance(exc, anthropic.RateLimitError):
            raise ModelUnavailable("the model is rate limited; try again in a minute") from exc
        if anthropic is not None and isinstance(exc, (anthropic.APIStatusError, anthropic.APIConnectionError)):
            raise ModelUnavailable(f"the model call failed: {exc.__class__.__name__}") from exc
        raise
    if getattr(response, "stop_reason", None) == "refusal":
        raise ModelUnavailable("the model declined the request")
    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise ModelUnavailable("the model returned no structured output")
    return parsed


# -- 1. free text -> intent ---------------------------------------------------

PARSE_SYSTEM = """You read what a person wants to build on a house lot in Toronto and fill a fixed set of fields.

Rules:
- Fill a field only when the text states it or clearly implies it. Otherwise leave it null.
- Metres and square metres. Convert feet (x 0.3048) and square feet (x 0.0929) and say so in `understood`.
- "Keep the walls", "renovate", "add on", "extend", "second storey on the existing" imply keep_existing_walls = true and project = addition.
- "Tear down", "demolish", "rebuild", "new build" imply keep_existing_walls = false and project = new_build.
- "Split the lot", "sever", "two lots" imply sever_lot = true and project = sever.
- More units inside the house with no addition is project = convert.
- A garden suite or a laneway suite is its own project value.
- `understood` lists each fact you took from the text, one short line each. `unclear` lists what the text says that no field holds.
- Never invent a number."""


def parse_intent(client: ParseClient | None, text: str, mode: Mode) -> tuple[ParsedIntent, Intent]:
    """The model's reading of `text`, and the Intent built from it (invalid numbers dropped)."""
    parsed = _call(
        client,
        system=PARSE_SYSTEM,
        user=f"Mode: {mode}.\n\nThe person wrote:\n\"\"\"\n{text.strip()}\n\"\"\"",
        output_format=ParsedIntent,
        effort="low",
        max_tokens=2000,
    )
    assert isinstance(parsed, ParsedIntent)
    return parsed, intent_from_parsed(parsed, text, mode)


def intent_from_parsed(parsed: ParsedIntent, text: str, mode: Mode) -> Intent:
    fields: dict[str, Any] = {"mode": mode, "text": text}
    if parsed.project in ("addition", "new_build", "convert", "garden_suite", "laneway_suite", "sever"):
        fields["project"] = parsed.project
    for name in ("keep_existing_walls", "sever_lot", *NUMERIC_FIELDS):
        value = getattr(parsed, name)
        if value is None:
            continue
        try:
            Intent(**{name: value})
        except ValidationError:
            continue  # a zero or negative number the model read; the field stays unknown
        fields[name] = value
    return Intent(**fields)


def merge_intent(parsed: Intent | None, details: Intent, text: str | None) -> Intent:
    """Form fields win over the model's reading; the model fills what the form left blank."""
    base = parsed.model_dump() if parsed else {}
    for name, value in details.model_dump().items():
        if name == "project" and value == "unknown":
            continue
        if value is not None:
            base[name] = value
    base["text"] = text
    base["mode"] = details.mode
    return Intent(**base)


# -- 2. analysis -> cited answer ----------------------------------------------

WRITE_SYSTEM = """You write a short answer about what a person can build on one Toronto house lot. You are given a
deterministic analysis: the zoning gaps (the by-law value, the plan, the building that stands today), ranked
pathway cards with their legal basis, risks and questions, and nearby Committee of Adjustment files.

Rules:
- Use only what the analysis says. Do not add a rule, a clause, a number, a cost or a file that is not in it.
- Every paragraph cites what it rests on, as ids from the analysis: card:<card_id>, clause:<clause id>,
  gap:<standard>, file:<reference_file>. A paragraph with no valid citation is deleted before the person sees it.
- Plain language. Short sentences. Say "short by 0.5 m", not "non-compliant".
- Say what is unknown and what would settle it. Never say a variance will be approved; the analysis is not a prediction.
- Buyer mode: the person is deciding whether to buy. End with questions for their lawyer, agent or builder.
  Professional mode: the person is a planner, agent or builder. End with what to check next.
- 3 to 5 sections: what the plan is short on; the route that fits best and why; the other routes; the risks; what the
  neighbours got. Skip a section with nothing to say.
- This is not legal advice. Do not say that it is."""


def _compact_analysis(a: PathwayAnalysis) -> dict[str, Any]:
    """The analysis as the model sees it: ids first, everything else trimmed."""
    gaps = [
        {
            "id": f"gap:{g.standard}",
            "label": g.label,
            "status": g.status,
            "required": g.required,
            "required_status": g.required_status,
            "proposed": g.proposed,
            "proposed_source": g.proposed_source,
            "existing": g.existing,
            "existing_status": g.existing_status,
            "delta": g.delta,
            "unit": g.unit,
            "clauses": [f"clause:{c}" for c in g.clause_ids],
            "note": g.note,
        }
        for g in a.gaps
        if g.status != "not_applicable" or g.existing_status == "short"
    ]
    cards = []
    for c in a.candidates:
        card: dict[str, Any] = {
            "id": f"card:{c.card_id}",
            "name": c.name,
            "category": c.category,
            "result": c.result,
            "summary": c.summary,
            "decision_body": c.decision_body,
            "covers_gaps": c.covers_gaps,
            "missing_facts": c.missing_facts,
            "legal_basis": [{"id": f"clause:{b.clause}", "says": b.says} for b in c.legal_basis],
            "steps": c.mechanics,
            "risks": c.risks,
            "questions": c.questions,
            "cost_band": c.cost_band,
            "time_band": c.time_band,
        }
        if c.precedents:
            s = c.precedents.summary
            card["nearby_files"] = {
                "total": s.total,
                "approved": s.approved,
                "refused": s.refused,
                "approval_rate": s.approval_rate,
                "examples": [
                    {
                        "id": f"file:{p.reference_file}",
                        "address": p.address,
                        "distance_m": p.distance_m,
                        "hearing_date": str(p.hearing_date) if p.hearing_date else None,
                        "asked_for": p.description,
                        "outcome": p.outcome,
                        "appeal": p.appeal,
                    }
                    for p in c.precedents.examples
                    if p.reference_file
                ],
            }
        cards.append(card)
    return {
        "mode": a.mode,
        "intent": a.intent.model_dump(exclude_none=True),
        "zone_label": a.zone_label,
        "short_standards": a.short_standards,
        "unknown_standards": a.unknown_standards,
        "gaps": gaps,
        "pathways": cards,
        "nearby_files_all": a.precedents.model_dump() if a.precedents else None,
        "precedent_radius_m": a.precedent_radius_m,
        "caveats": a.caveats,
    }


def valid_citations(a: PathwayAnalysis) -> set[str]:
    ids: set[str] = set()
    for g in a.gaps:
        ids.add(f"gap:{g.standard}")
        ids.update(f"clause:{c}" for c in g.clause_ids)
    for c in a.candidates:
        ids.add(f"card:{c.card_id}")
        ids.update(f"clause:{b.clause}" for b in c.legal_basis)
        if c.precedents:
            ids.update(f"file:{p.reference_file}" for p in c.precedents.examples if p.reference_file)
    return ids


_CITATION = re.compile(r"^(card|clause|gap|file):\S")


def check_citations(draft: Draft, a: PathwayAnalysis, model: str) -> Answer:
    """Keep only paragraphs whose citations all resolve; record what was dropped and why."""
    ids = valid_citations(a)
    dropped: list[str] = []
    sections: list[Section] = []
    for section in draft.sections:
        kept: list[Paragraph] = []
        for p in section.paragraphs:
            cites = [c.strip() for c in p.citations if c and c.strip()]
            if not cites:
                dropped.append(f"No citation: {p.text[:80]}")
                continue
            bad = [c for c in cites if not _CITATION.match(c) or c not in ids]
            if bad:
                dropped.append(f"Unknown citation {', '.join(bad)}: {p.text[:80]}")
                continue
            kept.append(Paragraph(text=p.text.strip(), citations=cites))
        if kept:
            sections.append(Section(heading=section.heading.strip(), paragraphs=kept))
    return Answer(
        headline=draft.headline.strip(),
        sections=sections,
        questions=[q.strip() for q in draft.questions if q.strip()],
        unknowns=[u.strip() for u in draft.unknowns if u.strip()],
        dropped=dropped,
        model=model,
    )


def write_answer(client: ParseClient | None, analysis: PathwayAnalysis) -> Answer:
    draft = _call(
        client,
        system=WRITE_SYSTEM,
        user=json.dumps(_compact_analysis(analysis), default=str, sort_keys=True),
        output_format=Draft,
        effort="medium",
        max_tokens=6000,
    )
    assert isinstance(draft, Draft)
    return check_citations(draft, analysis, settings.zoning_model)


class AskRequest(BaseModel):
    """What the form sends: the person's words, and any detail fields they opened."""

    mode: Mode = "buyer"
    text: str | None = Field(None, max_length=2000, description="The plan in the person's own words")
    details: Intent | None = Field(None, description="Fields from the detail form; they override what the model reads")


class AskResponse(BaseModel):
    intent: Intent
    understood: list[str] = Field(default_factory=list, description="What the model read from the text, one line each")
    unclear: list[str] = Field(default_factory=list, description="What the text said that no field holds")
    analysis: PathwayAnalysis
    answer: Answer | None = Field(None, description="The cited written answer; null when the model was unavailable")
    answer_note: str | None = Field(None, description="Why `answer` is null, or that it came from the cache")
    cached: bool = False


def request_hash(intent: Intent, playbook_version: str) -> str:
    """Cache key: the same intent, playbook, prompt and model give the same answer."""
    payload = json.dumps(
        {"intent": intent.model_dump(exclude={"text"}), "playbook": playbook_version, "prompt": PROMPT_VERSION, "model": settings.zoning_model},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
