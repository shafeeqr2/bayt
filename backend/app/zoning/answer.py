"""Phase 2: the model reads free text into the intent, and writes a cited answer from the analysis.

Two model calls, both with structured (JSON schema) output so the shape is fixed:

1. `parse_intent`: the buyer's own words -> the fields of `Intent`. The model may
   only fill fields the text supports; a number it did not read stays None.
   Form fields the person typed override what the model read.
2. `write_answer`: the deterministic `PathwayAnalysis` -> a short written answer.
   Every paragraph cites what it rests on: a card (`card:<id>`), a by-law clause
   (`clause:<id>`), a gap row (`gap:<standard>`) or a nearby file (`file:<ref>`).
   `check_citations` drops every paragraph whose citations do not all resolve to
   something in the analysis. The model never adds a rule, a number or a file.

The provider comes from the key (`LLM_API_KEY`): an Anthropic key uses the
Anthropic SDK; an OpenRouter or NVIDIA key uses the OpenAI-style chat API with
`response_format` json_schema, which is how NVIDIA's Nemotron models are
served. Without credentials both calls raise `ModelUnavailable` and the
endpoint returns the deterministic analysis alone.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.zoning import textrules
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
    proposed_units: int | None = Field(None, description="Dwelling units after the work")
    proposed_storeys: int | None = Field(None, description="Storeys after the work (a 'third storey' means 3)")
    proposed_height_m: float | None = Field(None, description="Building height after the work, metres")
    proposed_gfa_m2: float | None = Field(None, description="Gross floor area of all floors, square metres")
    proposed_footprint_m2: float | None = Field(None, description="Ground area of all buildings after the work, square metres")
    proposed_building_depth_m: float | None = Field(None, description="Rear main wall measured from the required front yard setback, metres")
    proposed_building_length_m: float | None = Field(None, description="Front main wall to rear main wall, metres")
    proposed_front_setback_m: float | None = Field(None, description="Front wall to the front lot line, metres")
    proposed_side_setback_m: float | None = Field(None, description="The smaller side yard, metres")
    proposed_rear_setback_m: float | None = Field(None, description="Rear wall to the rear lot line, metres")
    understood: list[str] = Field(default_factory=list, description="One short line per fact read from the text, in the person's units")
    unclear: list[str] = Field(default_factory=list, description="Things the text mentions that no field can hold")


class Paragraph(BaseModel):
    text: str
    citations: list[str] = Field(description="card:<id> | clause:<id> | gap:<standard> | file:<reference>; at least 1")


class Section(BaseModel):
    heading: str
    paragraphs: list[Paragraph]


class Draft(BaseModel):
    headline: str = Field(description="One sentence about this plan: what it is short on and the route that fits, e.g. 'The third storey is 0.5 m over the height limit; a minor variance is the usual route.'")
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


# -- backends ----------------------------------------------------------------


class Backend(Protocol):
    """One structured call: system + user prompt -> an instance of `schema`."""

    model: str

    def structured(self, *, system: str, user: str, schema: type[BaseModel], effort: str, max_tokens: int) -> BaseModel: ...


@dataclass(frozen=True)
class Provider:
    name: str
    kind: str  # anthropic | openai
    base_url: str | None
    default_model: str


PROVIDERS = {
    "anthropic": Provider("anthropic", "anthropic", None, "claude-opus-5-5"),
    "openrouter": Provider("openrouter", "openai", "https://openrouter.ai/api/v1", "nvidia/nemotron-3-super-120b-a12b"),
    "nvidia": Provider("nvidia", "openai", "https://integrate.api.nvidia.com/v1", "nvidia/nemotron-3-super-120b-a12b"),
    "openai": Provider("openai", "openai", None, ""),
}
KEY_PREFIXES = (("sk-ant-", "anthropic"), ("sk-or-", "openrouter"), ("nvapi-", "nvidia"))


def resolve_provider(key: str | None = None, provider: str | None = None) -> Provider | None:
    """The provider for the configured key, or None without a key or an unknown prefix."""
    key = key if key is not None else settings.llm_api_key
    name = (provider or settings.llm_provider or "auto").lower()
    if not key:
        return None
    if name == "auto":
        name = next((p for prefix, p in KEY_PREFIXES if key.startswith(prefix)), "")
    if name not in PROVIDERS:
        return None
    p = PROVIDERS[name]
    base = settings.llm_base_url or p.base_url
    return Provider(p.name, p.kind, base, p.default_model)


def model_name(provider: Provider | None = None) -> str:
    p = provider or resolve_provider()
    return settings.zoning_model or (p.default_model if p else "")


def make_client() -> Backend | None:
    """A backend when credentials exist, else None."""
    p = resolve_provider()
    if p is None:
        return None
    model = model_name(p)
    if p.kind == "anthropic":
        return AnthropicBackend(settings.llm_api_key or "", model)
    if not p.base_url or not model:
        return None
    return OpenAIBackend(settings.llm_api_key or "", p.base_url, model, p.name)


class AnthropicBackend:
    """`client.messages.parse` with `output_format`: the SDK validates the JSON against the schema."""

    def __init__(self, api_key: str, model: str, client: Any = None):
        self.model = model
        self._client = client
        self._api_key = api_key

    def structured(self, *, system: str, user: str, schema: type[BaseModel], effort: str, max_tokens: int) -> BaseModel:
        import anthropic

        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self._api_key)
        try:
            response = self._client.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=schema,
                output_config={"effort": effort},
            )
        except anthropic.AuthenticationError as exc:
            raise ModelUnavailable("the API key was rejected") from exc
        except anthropic.RateLimitError as exc:
            raise ModelUnavailable("the model is rate limited; try again in a minute") from exc
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            raise ModelUnavailable(f"the model call failed: {exc.__class__.__name__}") from exc
        if getattr(response, "stop_reason", None) == "refusal":
            raise ModelUnavailable("the model declined the request")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise ModelUnavailable("the model returned no structured output")
        return parsed


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.S)


class OpenAIBackend:
    """OpenAI-style `POST {base_url}/chat/completions` with `response_format` json_schema.

    This is how OpenRouter and NVIDIA NIM serve the Nemotron models. The JSON comes
    back as the message text; it is validated with the pydantic schema here, so a
    provider that ignores the schema still cannot slip a wrong shape through.
    """

    def __init__(self, api_key: str, base_url: str, model: str, provider: str = "openai", transport: httpx.BaseTransport | None = None):
        self.model = model
        self.provider = provider
        self._url = base_url.rstrip("/") + "/chat/completions"
        headers = {"authorization": f"Bearer {api_key}", "content-type": "application/json"}
        if provider == "openrouter":
            headers["x-title"] = "Bayt zoning pathways"
        self._http = httpx.Client(headers=headers, timeout=180.0, transport=transport)

    def structured(self, *, system: str, user: str, schema: type[BaseModel], effort: str, max_tokens: int) -> BaseModel:
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system + "\n\nAnswer with one JSON object that matches the given schema. No prose outside the JSON."},
                {"role": "user", "content": user},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "strict": True, "schema": schema.model_json_schema()},
            },
        }
        if self.provider == "openrouter":
            # Reasoning models think inside the output budget and Nemotron thinks for minutes
            # when allowed; both calls here are "write JSON from given material", so thinking is
            # off unless the caller asks for high effort.
            body["reasoning"] = {"effort": "low", "exclude": True} if effort in ("high", "xhigh", "max") else {"enabled": False}
        try:
            response = self._http.post(self._url, json=body)
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"the model call failed: {exc.__class__.__name__}") from exc
        if response.status_code in (401, 403):
            raise ModelUnavailable("the API key was rejected")
        if response.status_code == 429:
            raise ModelUnavailable("the model is rate limited; try again in a minute")
        if response.status_code >= 400:
            raise ModelUnavailable(f"the model call failed: HTTP {response.status_code} {response.text[:120]}")
        try:
            data = response.json()
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelUnavailable("the model returned no structured output") from exc
        if choice.get("finish_reason") == "length":
            usage = data.get("usage") or {}
            raise ModelUnavailable(
                f"the model ran out of output tokens ({usage.get('completion_tokens', '?')} used of {max_tokens})"
            )
        if not isinstance(text, str) or not text.strip():
            raise ModelUnavailable("the model returned no structured output")
        try:
            return schema.model_validate_json(_FENCE.sub("", text).strip())
        except ValidationError as exc:
            raise ModelUnavailable(f"the model returned JSON that does not fit the schema ({exc.error_count()} errors)") from exc


def _call(client: Backend | None, *, system: str, user: str, output_format: type[BaseModel], effort: str, max_tokens: int) -> BaseModel:
    if client is None:
        raise ModelUnavailable("LLM_API_KEY is not set")
    return client.structured(system=system, user=user, schema=output_format, effort=effort, max_tokens=max_tokens)


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
- `understood` lists each fact you took from the text, one short line each, as `field = value`.
- `unclear` lists only things the text says that no field can hold. Do not list fields the text never mentions.
- Never invent a number."""


FIELD_GUIDE = "\n".join(
    f"- {name}: {field.description or name.replace('proposed_', '').replace('_', ' ')}"
    for name, field in ParsedIntent.model_fields.items()
    if name not in ("understood", "unclear")
)


def parse_intent(client: Backend | None, text: str, mode: Mode) -> tuple[ParsedIntent, Intent]:
    """The model's reading of `text`, and the Intent built from it (invalid numbers dropped)."""
    parsed = _call(
        client,
        system=PARSE_SYSTEM,
        user=(
            f"Mode: {mode}.\n\nThe person wrote:\n\"\"\"\n{text.strip()}\n\"\"\"\n\n"
            f"Fields to fill (a number goes in its field, not only in `understood`):\n{FIELD_GUIDE}"
        ),
        output_format=ParsedIntent,
        effort="low",
        max_tokens=2000,
    )
    assert isinstance(parsed, ParsedIntent)
    backfill_from_understood(parsed)
    backfill_from_rules(parsed, text)
    intent = intent_from_parsed(parsed, text, mode)
    # The lines a person checks come from the final fields, not from the model's prose.
    parsed.understood = textrules.describe(intent.model_dump())
    parsed.unclear = [u for u in parsed.unclear if not _names_an_empty_field(u)]
    return parsed, intent


_FIELD_NAME = re.compile(r"\b(proposed_[a-z0-9_]+|keep_existing_walls|sever_lot)\b")


def _names_an_empty_field(line: str) -> bool:
    """Smaller models list every blank field as "unclear"; a line that names a field and gives no number is noise."""
    return bool(_FIELD_NAME.search(line)) and not re.search(r"\d", _FIELD_NAME.sub("", line))


def backfill_from_rules(parsed: ParsedIntent, text: str) -> None:
    """Fields the model left empty take the rule-based reading of the same text (`textrules.extract`)."""
    for name, value in textrules.extract(text).items():
        if name in ParsedIntent.model_fields and getattr(parsed, name) is None:
            setattr(parsed, name, value)


def rules_intent(text: str, mode: Mode) -> tuple[ParsedIntent, Intent]:
    """The no-model path: the same reading from rules alone."""
    parsed = ParsedIntent(**textrules.extract(text))
    intent = intent_from_parsed(parsed, text, mode)
    parsed.understood = textrules.describe(intent.model_dump())
    return parsed, intent


_ASSIGNMENT = re.compile(r"\b(proposed_[a-z0-9_]+|keep_existing_walls|sever_lot|project)\s*=\s*([A-Za-z0-9_.\-]+)")


def backfill_from_understood(parsed: ParsedIntent) -> None:
    """A smaller model sometimes writes `proposed_rear_setback_m = 6.5` in `understood` and leaves the field null.

    The line is the model's own reading, so an empty field takes that value. A filled field is never changed.
    """
    for line in parsed.understood:
        for name, raw in _ASSIGNMENT.findall(line):
            if name not in ParsedIntent.model_fields or getattr(parsed, name) is not None:
                continue
            value: Any = raw
            if name in ("keep_existing_walls", "sever_lot"):
                value = {"true": True, "false": False}.get(raw.lower())
            elif name.startswith("proposed_"):
                try:
                    value = int(raw) if name in ("proposed_units", "proposed_storeys") else float(raw)
                except ValueError:
                    continue
            if value is not None:
                setattr(parsed, name, value)


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


def write_answer(client: Backend | None, analysis: PathwayAnalysis) -> Answer:
    draft = _call(
        client,
        system=WRITE_SYSTEM,
        user=json.dumps(_compact_analysis(analysis), default=str, sort_keys=True),
        output_format=Draft,
        effort="medium",
        max_tokens=12000,
    )
    assert isinstance(draft, Draft)
    return check_citations(draft, analysis, client.model if client else model_name())


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
        {"intent": intent.model_dump(exclude={"text"}), "playbook": playbook_version, "prompt": PROMPT_VERSION, "model": model_name()},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()
