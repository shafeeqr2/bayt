"""Orchestration with I/O: lot analysis (GIS + cache) and city data, then the pure analysis."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.lot import service as lot_service
from app.models import Listing, ListingCityData
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
