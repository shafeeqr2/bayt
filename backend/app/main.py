from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session, contains_eager

from app.city.parking import parking_rules
from app.city.permits import permits_for
from app.city.tiles import MAX_ZOOM, MIN_ZOOM, building_tile, buildings_loaded, city_boundary
from app.city.zones import zone_label, zone_rules
from app.config import settings
from app.db import get_session
from app.lot import floorplan
from app.lot import service as lot_service
from app.lot.floorplan import FloorPlanResult
from app.lot.schemas import LotAnalysis
from app.models import Listing, ListingCityData, ListingInvestment
from app.photos import reader as photo_reader
from app.schemas import (
    CityData,
    Facets,
    InvestmentDetail,
    ListingDetail,
    ListingPage,
    ListingSummary,
    MapPin,
    ParsedStrategy,
    StrategyDefaults,
    ZoneRule,
)
from app.strategy import estimate as strategy_estimate
from app.strategy import parse as strategy_parse
from app.strategy import search as strategy
from app.strategy.finance import Financing
from app.zoning import answer as zoning_answer
from app.zoning import cards as zoning_cards
from app.zoning import precedents as zoning_precedents
from app.zoning import service as zoning_service
from app.zoning.intent import Intent
from app.zoning.schemas import PathwayAnalysis

app = FastAPI(title="Bayt API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

SessionDep = Annotated[Session, Depends(get_session)]
FinancingDep = Annotated[Financing, Depends(strategy.financing_params)]

SORTS = {
    "newest": Listing.source_updated_at.desc().nulls_last(),
    "price_asc": Listing.price.asc(),
    "price_desc": Listing.price.desc(),
}
Sort = Literal["newest", "price_asc", "price_desc", "cap_rate_desc", "cash_flow_desc", "yield_desc"]


def _cover(listing: Listing) -> str | None:
    # "medium" is only 256px wide; the frontend resizes "high" (1600px) itself.
    return listing.photos[0]["high"] if listing.photos else None


def _summary(listing: Listing, fin: Financing) -> ListingSummary:
    return ListingSummary.model_validate(listing, from_attributes=True).model_copy(
        update={
            "cover_photo": _cover(listing),
            "investment": strategy.summary(listing.investment_estimate, listing.price, fin),
        }
    )


def _with_investment(stmt: Select) -> Select:
    """Every search joins the investment estimate so returns can be filtered and sorted in SQL."""
    return stmt.outerjoin(ListingInvestment, ListingInvestment.listing_id == Listing.id)


@app.get("/api/health")
def health(session: SessionDep) -> dict[str, str]:
    session.execute(text("select 1"))
    return {"status": "ok"}


def listing_filters(
    fin: FinancingDep,
    city: str | None = None,
    building_type: str | None = None,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    min_beds: Annotated[int | None, Query(ge=0)] = None,
    min_baths: Annotated[int | None, Query(ge=0)] = None,
    q: str | None = None,
    # Investment strategy. Returns use the estimate in `listing_investment`;
    # cash flow and affordability also use the financing parameters.
    min_cap_rate: Annotated[float | None, Query(ge=-100, le=100)] = None,
    min_gross_yield: Annotated[float | None, Query(ge=0, le=100)] = None,
    min_cash_flow: Annotated[int | None, Query(description="Monthly, after the mortgage; may be negative")] = None,
    income: Annotated[int | None, Query(ge=0, description="Annual household income for qualifying")] = None,
    monthly_debts: Annotated[int, Query(ge=0)] = 0,
    occupancy: strategy.Occupancy = "rent_out",
    potential: Annotated[list[strategy.PotentialKey] | None, Query()] = None,
) -> list:
    """The search filters, shared by the list and the map so both agree on what matches."""
    filters = strategy.strategy_filters(
        fin,
        min_cap_rate=min_cap_rate,
        min_gross_yield=min_gross_yield,
        min_cash_flow=min_cash_flow,
        income=income,
        monthly_debts=monthly_debts,
        occupancy=occupancy,
        potential=potential,
    )
    if city:
        filters.append(Listing.city == city)
    if building_type:
        filters.append(Listing.building_type == building_type)
    if min_price is not None:
        filters.append(Listing.price >= min_price)
    if max_price is not None:
        filters.append(Listing.price <= max_price)
    if min_beds is not None:
        filters.append(Listing.bedrooms_total >= min_beds)
    if min_baths is not None:
        filters.append(Listing.bathrooms >= min_baths)
    if q:
        pattern = f"%{q}%"
        filters.append(
            Listing.address.ilike(pattern)
            | Listing.community.ilike(pattern)
            | Listing.mls_number.ilike(pattern)
        )
    return filters


FiltersDep = Annotated[list, Depends(listing_filters)]


@app.get("/api/listings")
def list_listings(
    session: SessionDep,
    filters: FiltersDep,
    fin: FinancingDep,
    sort: Sort = "newest",
    limit: Annotated[int, Query(ge=1, le=100)] = 24,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ListingPage:
    total = session.scalar(_with_investment(select(func.count()).select_from(Listing)).where(*filters)) or 0
    order = SORTS.get(sort) if sort in SORTS else strategy.strategy_sort(sort, fin)
    rows = session.scalars(
        _with_investment(select(Listing))
        .options(contains_eager(Listing.investment_estimate))
        .where(*filters)
        .order_by(order, Listing.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return ListingPage(
        items=[_summary(r, fin) for r in rows], total=total, limit=limit, offset=offset
    )


@app.get("/api/listings/facets")
def facets(session: SessionDep) -> Facets:
    def distinct(column) -> list[str]:
        return list(
            session.scalars(select(column).where(column.is_not(None)).distinct().order_by(column))
        )

    return Facets(cities=distinct(Listing.city), building_types=distinct(Listing.building_type))


@app.get("/api/listings/map")
def map_pins(session: SessionDep, filters: FiltersDep) -> list[MapPin]:
    """Every listing matching the filters, as pins for the search map (no paging)."""
    rows = session.scalars(
        _with_investment(select(Listing))
        .where(Listing.latitude.is_not(None), Listing.longitude.is_not(None), *filters)
        .order_by(Listing.price.desc(), Listing.id)
    ).all()
    return [
        MapPin.model_validate(r, from_attributes=True).model_copy(
            update={"cover_photo": r.photos[0]["medium"] if r.photos else None}
        )
        for r in rows
    ]


@app.get("/api/strategy/defaults")
def strategy_defaults() -> StrategyDefaults:
    """Default financing, the assumptions behind every estimate, and example strategies."""
    return strategy.defaults()


@app.get("/api/strategy/parse")
def parse_strategy(session: SessionDep, text: Annotated[str, Query(max_length=1000)]) -> ParsedStrategy:
    """Turn a strategy in plain language into search parameters, with each interpretation spelled out."""
    communities = list(session.scalars(select(Listing.community).where(Listing.community.is_not(None)).distinct()))
    parsed = strategy_parse.parse_strategy(text, communities)
    return ParsedStrategy(params=parsed.params, understood=parsed.understood, unmatched=parsed.unmatched)


@app.get("/api/listings/{listing_id}/investment")
def get_listing_investment(listing_id: str, session: SessionDep, fin: FinancingDep) -> InvestmentDetail:
    """Rent, operating costs, returns, cash needed and value-add potential at the given financing."""
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    row = session.get(ListingInvestment, listing_id)
    if row is None or row.model_version != strategy_estimate.MODEL_VERSION:
        row = strategy_estimate.refresh(session, listing)
    return strategy.detail(listing, row, fin)


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: str, session: SessionDep) -> ListingDetail:
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return ListingDetail.model_validate(listing, from_attributes=True).model_copy(
        update={
            "cover_photo": _cover(listing),
            "investment": strategy.summary(listing.investment_estimate, listing.price, Financing()),
        }
    )


@app.get("/api/listings/{listing_id}/city")
def get_listing_city_data(listing_id: str, session: SessionDep) -> CityData:
    """Lot, zoning and permits from City of Toronto open data.

    404 when the listing is outside Toronto or city data has not been loaded.
    """
    data = session.get(ListingCityData, listing_id)
    if data is None:
        raise HTTPException(status_code=404, detail="No City of Toronto data for this listing")
    listing = session.get(Listing, listing_id)
    rules, parking_note = parking_rules(
        data.zone_category,
        data.parking_zone,
        listing.building_type if listing else None,
        listing.bedrooms_total if listing else None,
    )
    return CityData.model_validate(data, from_attributes=True).model_copy(
        update={
            "zone_label": zone_label(data.zone_category),
            "zone_rules": [ZoneRule.model_validate(rule) for rule in zone_rules(data.zone_string)],
            "parking_rules": [ZoneRule(label=rule.label, value=rule.value) for rule in rules],
            "parking_note": parking_note,
            "permits": permits_for(session, data.address_point_id)
            if data.address_point_id
            else [],
        }
    )


@app.get("/api/tiles/buildings/{z}/{x}/{y}")
def building_tiles(z: int, x: int, y: int, session: SessionDep) -> Response:
    """Vector tile of City of Toronto building outlines with LiDAR heights.

    204 outside the zoom range or before `./start.sh city-data` has loaded buildings.
    """
    if not MIN_ZOOM <= z <= MAX_ZOOM or not 0 <= x < 2**z or not 0 <= y < 2**z or not buildings_loaded(session):
        return Response(status_code=204)
    tile = building_tile(session, z, x, y)
    if not tile:
        return Response(status_code=204)
    return Response(
        tile,
        media_type="application/vnd.mapbox-vector-tile",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/city/boundary")
def get_city_boundary(session: SessionDep) -> Response:
    """Toronto's municipal limits as GeoJSON, for deciding where city data applies."""
    geojson = city_boundary(session)
    if geojson is None:
        raise HTTPException(status_code=404, detail="City boundary not loaded")
    return Response(geojson, media_type="application/geo+json", headers={"Cache-Control": "public, max-age=86400"})


def _lot_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, lot_service.NotInCoverage):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, lot_service.ListingNotLocated):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, lot_service.GISError):
        return HTTPException(status_code=502, detail=f"City of Toronto GIS unavailable: {exc}")
    raise exc


@app.get("/api/listings/{listing_id}/lot")
def get_listing_lot(listing_id: str, session: SessionDep, refresh: bool = False) -> LotAnalysis:
    """Lot coverage and infill potential for a listing (cached for 30 days)."""
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        return lot_service.analyze_listing(session, listing, refresh=refresh)
    except (lot_service.NotInCoverage, lot_service.ListingNotLocated, lot_service.GISError) as exc:
        raise _lot_errors(exc) from exc


@app.get("/api/listings/{listing_id}/floorplan")
def get_listing_floorplan(listing_id: str, session: SessionDep) -> FloorPlanResult:
    """A possible floor plan: the listed rooms fitted into the city's building outline, level by level."""
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    outside = "Building outlines come from City of Toronto data, which does not cover this address."
    if listing.city != "Toronto":
        return FloorPlanResult(plan=None, reason=outside)
    try:
        lot = lot_service.analyze_listing(session, listing)
        return FloorPlanResult(plan=floorplan.floor_plan_for(listing, lot))
    except lot_service.NotInCoverage:
        return FloorPlanResult(plan=None, reason=outside)
    except lot_service.ListingNotLocated:
        return FloorPlanResult(plan=None, reason="The listing has no map location, so its building outline cannot be found.")
    except lot_service.GISError:
        return FloorPlanResult(plan=None, reason="The city's map service did not answer; try again later.")
    except floorplan.NoPlan as exc:
        return FloorPlanResult(plan=None, reason=str(exc))


@app.get("/api/listings/{listing_id}/photos")
def get_listing_photos(listing_id: str, session: SessionDep) -> photo_reader.ListingPhotos:
    """The stored photo labels (title, one sentence, facts about the house). Never calls the model."""
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    return photo_reader.labels_for(session, listing)


@app.post("/api/listings/{listing_id}/photos/read")
def post_listing_photos_read(listing_id: str, session: SessionDep, force: bool = False) -> photo_reader.ListingPhotos:
    """Read the listing's photos with the vision model and store the labels.

    One structured call per photo, in parallel. Photos already read with the current
    prompt are skipped unless `force`. Without LLM_API_KEY this is a 503.
    """
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        return photo_reader.read_listing_photos(session, listing, force=force)
    except zoning_answer.ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/listings/{listing_id}/photos/review")
def post_listing_photos_review(listing_id: str, session: SessionDep) -> photo_reader.ListingPhotos:
    """The second pass alone: all stored labels in one text-model call; fixes the level, room and front-or-back calls."""
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        photo_reader.review_labels(session, listing)
    except zoning_answer.ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return photo_reader.labels_for(session, listing)


@app.get("/api/lot")
def get_lot(
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> LotAnalysis:
    """Lot coverage and infill potential for any point in Toronto (not cached)."""
    try:
        return lot_service.analyze_point(lat, lon)
    except (lot_service.NotInCoverage, lot_service.GISError) as exc:
        raise _lot_errors(exc) from exc


@app.post("/api/listings/{listing_id}/zoning/pathways")
def post_listing_pathways(listing_id: str, intent: Intent, session: SessionDep) -> PathwayAnalysis:
    """Zoning gaps for a proposal on this listing's lot, and the playbook pathways that address them.

    Deterministic: rule resolution, gap analysis and predicate matching. No model call.
    """
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        return zoning_service.pathways_for_listing(session, listing, intent)
    except (lot_service.NotInCoverage, lot_service.ListingNotLocated, lot_service.GISError) as exc:
        raise _lot_errors(exc) from exc


@app.post("/api/zoning/pathways")
def post_point_pathways(
    intent: Intent,
    session: SessionDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> PathwayAnalysis:
    """Zoning gaps and pathways for a proposal at any point in Toronto (not cached)."""
    try:
        return zoning_service.pathways_for_point(session, lat, lon, intent)
    except (lot_service.NotInCoverage, lot_service.GISError) as exc:
        raise _lot_errors(exc) from exc


@app.post("/api/listings/{listing_id}/zoning/ask")
def post_listing_ask(listing_id: str, req: zoning_answer.AskRequest, session: SessionDep) -> zoning_answer.AskResponse:
    """The plan in plain words (and/or detail fields) -> the deterministic analysis -> a cited written answer.

    The model reads the text into the intent fields and writes the answer from the analysis
    alone; every paragraph must cite a card, clause, gap or nearby file in it, or it is dropped.
    Without LLM_API_KEY the response carries the analysis and `answer` is null.
    """
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    try:
        return zoning_service.ask_for_listing(session, listing, req)
    except (lot_service.NotInCoverage, lot_service.ListingNotLocated, lot_service.GISError) as exc:
        raise _lot_errors(exc) from exc


RadiusDep = Annotated[int, Query(ge=50, le=zoning_precedents.MAX_RADIUS_M, description="Search radius in metres")]


def _precedents_loaded(session: Session) -> None:
    if not zoning_precedents.loaded(session):
        raise HTTPException(status_code=404, detail="Committee of Adjustment data not loaded (./start.sh city-data)")


@app.get("/api/listings/{listing_id}/zoning/precedents")
def get_listing_precedents(
    listing_id: str,
    session: SessionDep,
    radius_m: RadiusDep = zoning_precedents.DEFAULT_RADIUS_M,
    work_type: str | None = None,
    q: Annotated[str | None, Query(max_length=80, description="Words that must appear in the description")] = None,
) -> zoning_precedents.PrecedentSearch:
    """Committee of Adjustment applications near this listing, nearest first, with outcome counts.

    404 when the listing is unknown or the Committee of Adjustment data is not loaded.
    """
    listing = session.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found")
    _precedents_loaded(session)
    try:
        return zoning_service.precedents_for_listing(session, listing, radius_m, work_type=work_type, query=q)
    except lot_service.ListingNotLocated as exc:
        raise _lot_errors(exc) from exc


@app.get("/api/zoning/precedents")
def get_point_precedents(
    session: SessionDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
    radius_m: RadiusDep = zoning_precedents.DEFAULT_RADIUS_M,
    work_type: str | None = None,
    q: Annotated[str | None, Query(max_length=80)] = None,
) -> zoning_precedents.PrecedentSearch:
    """Committee of Adjustment applications around any point in Toronto."""
    _precedents_loaded(session)
    return zoning_service.precedents_for_point(session, lat, lon, radius_m, work_type=work_type, query=q)


@app.get("/api/zoning/playbook")
def get_playbook() -> list[zoning_cards.StrategyCard]:
    """Every playbook card, so the frontend and reviewers can read the pathways and their triggers."""
    return zoning_cards.playbook()
