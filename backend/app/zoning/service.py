"""Orchestration with I/O: lot analysis (GIS + cache) and city data, then the pure analysis."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.lot import service as lot_service
from app.models import Listing, ListingCityData, ZoningAnswer
from app.zoning import answer as model_answer
from app.zoning import textrules
from app.zoning import precedents
from app.zoning.intent import Intent
from app.zoning.pathways import analyze_pathways
from app.zoning.schemas import PathwayAnalysis


def _precedents(session: Session, lat: float | None, lon: float | None, radius_m: int) -> list[precedents.Precedent] | None:
    """Every Committee of Adjustment file within radius_m, or None when the data is not loaded."""
    if lat is None or lon is None or not precedents.loaded(session):
        return None
    return precedents.nearby(session, lat, lon, radius_m)


def pathways_for_listing(
    session: Session, listing: Listing, intent: Intent, *, precedent_radius_m: int = precedents.DEFAULT_RADIUS_M
) -> PathwayAnalysis:
    lot = lot_service.analyze_listing(session, listing)
    city = session.get(ListingCityData, listing.id)
    return analyze_pathways(
        lot,
        intent,
        height_limit_m=city.height_limit_m if city else None,
        height_limit_storeys=city.height_limit_storeys if city else None,
        overlay_checked=city is not None,
        heritage_listed=(bool(city.heritage_status) if city else None),
        precedents=_precedents(session, listing.latitude, listing.longitude, precedent_radius_m),
        precedent_radius_m=precedent_radius_m,
    )


def pathways_for_point(
    session: Session, lat: float, lon: float, intent: Intent, *, precedent_radius_m: int = precedents.DEFAULT_RADIUS_M
) -> PathwayAnalysis:
    lot = lot_service.analyze_point(lat, lon)
    return analyze_pathways(
        lot, intent, precedents=_precedents(session, lat, lon, precedent_radius_m), precedent_radius_m=precedent_radius_m
    )


def precedents_for_listing(
    session: Session, listing: Listing, radius_m: int, *, work_type: str | None = None, query: str | None = None
) -> precedents.PrecedentSearch:
    if listing.latitude is None or listing.longitude is None:
        raise lot_service.ListingNotLocated("Listing has no coordinates")
    return precedents_for_point(session, listing.latitude, listing.longitude, radius_m, work_type=work_type, query=query)


def precedents_for_point(
    session: Session, lat: float, lon: float, radius_m: int, *, work_type: str | None = None, query: str | None = None
) -> precedents.PrecedentSearch:
    radius_m = max(50, min(radius_m, precedents.MAX_RADIUS_M))
    items = precedents.nearby(session, lat, lon, radius_m, work_type=work_type, query=query)
    return precedents.PrecedentSearch(
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        work_type=work_type,
        query=query,
        summary=precedents.summarize(items),
        items=items,
        truncated=len(items) >= precedents.MAX_ITEMS,
    )


def ask_for_listing(session: Session, listing: Listing, req: model_answer.AskRequest) -> model_answer.AskResponse:
    """Free text and/or detail fields -> intent -> deterministic analysis -> cited written answer.

    The model is optional: without credentials the response carries the analysis and
    a note. The written answer is cached per listing, intent, playbook, prompt and model.
    """
    client = model_answer.make_client()
    details = req.details or Intent()
    details.mode = req.mode
    text = (req.text or "").strip() or None
    understood: list[str] = []
    unclear: list[str] = []
    notes: list[str] = []

    parsed_intent: Intent | None = None
    if text and textrules.reads_all(text):
        # The rules placed the project and every number: no model call, and the cache can hit at once.
        parsed, parsed_intent = model_answer.rules_intent(text, req.mode)
        understood = parsed.understood
    elif text:
        try:
            parsed, parsed_intent = model_answer.parse_intent(client, text, req.mode)
            understood, unclear = parsed.understood, parsed.unclear
        except model_answer.ModelUnavailable as exc:
            # No model: the rule-based reader still takes the common phrases.
            parsed, parsed_intent = model_answer.rules_intent(text, req.mode)
            understood = parsed.understood
            notes.append(f"The text was read by rules only ({exc}); check the understood line and use the details for the rest.")
    intent = model_answer.merge_intent(parsed_intent, details, text)

    analysis = pathways_for_listing(session, listing, intent)

    key = model_answer.request_hash(intent, analysis.playbook_version)
    cached = session.get(ZoningAnswer, (listing.id, key))
    if cached is not None:
        answer = model_answer.Answer(**cached.answer) if cached.answer else None
        if cached.note:
            notes.append(cached.note)
        return model_answer.AskResponse(
            intent=intent, understood=understood, unclear=unclear, analysis=analysis, answer=answer,
            answer_note=" ".join(notes) or None, cached=True,
        )

    answer = None
    note = None
    try:
        answer = model_answer.write_answer(client, analysis)
        if not answer.sections:
            note = "The model's answer had no paragraph with a valid citation, so none is shown."
            answer = None
    except model_answer.ModelUnavailable as exc:
        note = f"No written answer: {exc}."
    if answer is not None:
        # Only a usable answer is cached; a failure (rate limit, token limit, no citations) is retried next time.
        session.merge(
            ZoningAnswer(
                listing_id=listing.id,
                request_hash=key,
                model=model_answer.model_name(),
                prompt_version=model_answer.PROMPT_VERSION,
                intent=intent.model_dump(mode="json"),
                answer=answer.model_dump(mode="json"),
                note=None,
            )
        )
        session.commit()
    if note:
        notes.append(note)
    return model_answer.AskResponse(
        intent=intent, understood=understood, unclear=unclear, analysis=analysis, answer=answer,
        answer_note=" ".join(notes) or None, cached=False,
    )
