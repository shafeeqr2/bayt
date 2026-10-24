"""Orchestration with I/O: lot analysis (GIS + cache) and city data, then the pure analysis."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.lot import service as lot_service
from app.models import Listing, ListingCityData
from app.zoning.intent import Intent
from app.zoning.pathways import analyze_pathways
from app.zoning.schemas import PathwayAnalysis


def pathways_for_listing(session: Session, listing: Listing, intent: Intent) -> PathwayAnalysis:
    lot = lot_service.analyze_listing(session, listing)
    city = session.get(ListingCityData, listing.id)
    return analyze_pathways(
        lot,
        intent,
        height_limit_m=city.height_limit_m if city else None,
        height_limit_storeys=city.height_limit_storeys if city else None,
        overlay_checked=city is not None,
        heritage_listed=(bool(city.heritage_status) if city else None),
    )


def pathways_for_point(lat: float, lon: float, intent: Intent) -> PathwayAnalysis:
    lot = lot_service.analyze_point(lat, lon)
    return analyze_pathways(lot, intent)
