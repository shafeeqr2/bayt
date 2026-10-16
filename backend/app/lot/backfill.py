"""Precompute lot analyses (map geometry, coverage, infill verdicts) for every listing.

Run with `python -m app.lot.backfill` (done for you by `./start.sh lot-analysis`).

Each analysis costs 6 to 8 queries to the City of Toronto's GIS, so this is a
deliberate, resumable job rather than something that runs on every start:

- listings with a fresh cached result (see `service.CACHE_TTL`) are skipped
  unless `--refresh` is given;
- listings the city cannot place on a parcel (outside Toronto, no coordinates)
  are counted and skipped;
- a city GIS failure is logged and left uncached, so the next run (or the
  first visit to the listing page) tries again.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import exists, select

from app.db import SessionLocal
from app.lot.service import CACHE_TTL, GISError, ListingNotLocated, NotInCoverage, analyze_listing
from app.lot.toronto import TorontoGIS
from app.models import Listing, ListingCityData, LotAnalysisCache

DEFAULT_WORKERS = 4  # be a polite client of a public server


def candidate_ids(session, *, refresh: bool, limit: int | None = None) -> list[str]:
    """Listings worth sending to the city's GIS, oldest cache first.

    When City of Toronto open data has been loaded and matched, only listings
    sitting on a Toronto parcel are considered; otherwise every listing with
    coordinates is, and the GIS tells us which ones it cannot place.
    """
    query = select(Listing.id).where(Listing.latitude.is_not(None), Listing.longitude.is_not(None))
    if session.scalar(select(exists().where(ListingCityData.parcel_id.is_not(None)))):
        query = query.join(ListingCityData, ListingCityData.listing_id == Listing.id).where(
            ListingCityData.parcel_id.is_not(None)
        )
    if not refresh:
        fresh_after = datetime.now(timezone.utc) - CACHE_TTL
        query = query.outerjoin(LotAnalysisCache, LotAnalysisCache.listing_id == Listing.id).where(
            (LotAnalysisCache.listing_id.is_(None)) | (LotAnalysisCache.computed_at < fresh_after)
        )
    query = query.order_by(Listing.id)
    if limit:
        query = query.limit(limit)
    return list(session.scalars(query))


def run(ids: list[str], *, refresh: bool, workers: int, gis: TorontoGIS | None = None) -> Counter:
    gis = gis or TorontoGIS(timeout=45.0)
    outcomes: Counter = Counter()
    lock = threading.Lock()
    started = time.monotonic()

    def one(listing_id: str) -> None:
        with SessionLocal() as session:
            listing = session.get(Listing, listing_id)
            if listing is None:
                outcome = "missing"
            else:
                try:
                    analyze_listing(session, listing, refresh=refresh, gis=gis)
                    outcome = "analyzed"
                except NotInCoverage:
                    outcome = "outside coverage"
                except ListingNotLocated:
                    outcome = "no coordinates"
                except GISError as e:
                    outcome = "failed"
                    with lock:
                        print(f"lot-backfill: {listing_id}: {e}", file=sys.stderr)
        with lock:
            outcomes[outcome] += 1
            done = sum(outcomes.values())
            if done % 25 == 0 or done == len(ids):
                elapsed = time.monotonic() - started
                print(f"lot-backfill: {done}/{len(ids)} ({elapsed:.0f}s) {dict(outcomes)}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, ids))
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="recompute listings that already have a fresh result")
    parser.add_argument("--limit", type=int, help="only process this many listings")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"parallel GIS clients (default {DEFAULT_WORKERS})")
    parser.add_argument("ids", nargs="*", help="specific listing ids (default: every listing that needs one)")
    args = parser.parse_args()

    with SessionLocal() as session:
        ids = args.ids or candidate_ids(session, refresh=args.refresh, limit=args.limit)
    if not ids:
        print("lot-backfill: nothing to do, every listing has a fresh lot analysis")
        return

    print(f"lot-backfill: analyzing {len(ids)} listings with {args.workers} workers", flush=True)
    outcomes = run(ids, refresh=args.refresh, workers=max(1, args.workers))
    summary = ", ".join(f"{n} {k}" for k, n in sorted(outcomes.items()))
    print(f"lot-backfill: done: {summary}")
    if outcomes["failed"]:
        print(f"lot-backfill: {outcomes['failed']} listings failed on the city's GIS; re-run to retry them", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
