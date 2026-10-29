"""Write the house profile and the persona embeddings for every listing.

Run with `python -m app.similar.backfill` (`./start.sh profiles`). Each listing is
1 model call (the facts and the 4 persona views) and the pitches are embedded in
batches afterwards, so this is a deliberate, resumable job:

- listings with a profile from the current prompt are skipped unless `--refresh`;
- the free listings on OpenRouter allow about 1,000 requests per day, so the job
  takes Toronto houses first (`--order`), stops at `--limit`, and can be run
  again tomorrow for the rest;
- a rate limit (429) or a dropped connection waits and retries; any other model
  failure is stored in the row's `note` and the next run tries that listing again;
- when `STOP_AFTER` listings in a row fail, the host is not answering (the free
  listings drop the connection for hours once the day's requests are used up), so
  the job stops instead of waiting on every remaining listing. Run it again later.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import Text, case, cast, select

from app.db import SessionLocal
from app.models import Listing, ListingProfile
from app.similar import embed as embedder
from app.similar import profile as hp
from app.zoning import answer as llm

DEFAULT_WORKERS = 4
EMBED_EVERY = 100  # embed the pitches written so far every this many listings, so "similar" works while the job runs
RETRY_WAIT_S = 20
RETRIES = 3
STOP_AFTER = 20  # consecutive failed listings before the job gives up on the host for now
# Failures worth a retry after a wait: the host's rate limit, and a dropped or timed-out connection.
TRANSIENT = ("rate limited", "ReadError", "ReadTimeout", "ConnectError", "RemoteProtocolError", "HTTP 502", "HTTP 503", "HTTP 504")

# Toronto houses first: that is where the lot and zoning data give the personas the most to say.
ORDER = case(
    (Listing.building_type.in_(("House", "Duplex", "Triplex", "Fourplex", "Multi-Family")), 0),
    (Listing.building_type == "Row / Townhouse", 1),
    else_=2,
)


def candidate_ids(session, *, refresh: bool, limit: int | None = None, city: str | None = None) -> list[str]:
    query = select(Listing.id)
    if city:
        query = query.where(Listing.city == city)
    if not refresh:
        query = query.outerjoin(ListingProfile, ListingProfile.listing_id == Listing.id).where(
            (ListingProfile.listing_id.is_(None))
            | (ListingProfile.facts.is_(None))
            | (cast(ListingProfile.facts, Text) == "null")  # failed rows written before `none_as_null`
            | (ListingProfile.prompt_version != hp.PROMPT_VERSION)
        )
    query = query.order_by(ORDER, Listing.city != "Toronto", Listing.id)
    if limit:
        query = query.limit(limit)
    return list(session.scalars(query))


def run(ids: list[str], *, refresh: bool, workers: int, client: llm.Backend | None = None) -> Counter:
    client = client or hp.make_client()
    if client is None:
        raise llm.ModelUnavailable("LLM_API_KEY is not set")
    outcomes: Counter = Counter()
    lock = threading.Lock()
    stop = threading.Event()
    failed_in_a_row = 0
    started = time.monotonic()

    def one(listing_id: str) -> None:
        nonlocal failed_in_a_row
        if stop.is_set():
            outcome = "skipped"
        else:
            with SessionLocal() as session:
                listing = session.get(Listing, listing_id)
                if listing is None:
                    outcome = "missing"
                else:
                    outcome = "failed"
                    note = None
                    for attempt in range(RETRIES):
                        out = hp.write_profile(session, listing, client, force=refresh, embed=False)
                        note = out.note
                        if out.facts is not None:
                            outcome = "written"
                            break
                        if note and any(w in note for w in TRANSIENT) and attempt < RETRIES - 1:
                            time.sleep(RETRY_WAIT_S * (attempt + 1))
                            continue
                        break
                    if outcome == "failed":
                        with lock:
                            print(f"  {listing_id}: {note}", file=sys.stderr)
        with lock:
            outcomes[outcome] += 1
            if outcome == "written":
                failed_in_a_row = 0
            elif outcome == "failed":
                failed_in_a_row += 1
                if failed_in_a_row >= STOP_AFTER and not stop.is_set():
                    stop.set()
                    print(
                        f"profiles: {STOP_AFTER} listings failed in a row; the host is not answering. "
                        "Stopping; run again later for the rest.",
                        file=sys.stderr,
                    )
            done = sum(outcomes.values())
            if done % 25 == 0 or done == len(ids):
                elapsed = time.monotonic() - started
                print(f"  {done}/{len(ids)} in {elapsed:.0f}s ({dict(outcomes)})", flush=True)
        if done % EMBED_EVERY == 0:
            embed_all()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, ids))
    return outcomes


def embed_all(limit: int | None = None) -> int:
    """Embed every persona row that lacks a current vector, in batches."""
    client = embedder.make_client()
    if client is None:
        print("profiles: no embedding model for this provider; pitches are stored but not searchable", flush=True)
        return 0
    total = 0
    with SessionLocal() as session:
        while True:
            rows = embedder.pending(session, client.model, limit=embedder.BATCH)
            if not rows:
                break
            for attempt in range(RETRIES):
                try:
                    total += embedder.embed_rows(session, rows, client)
                    break
                except llm.ModelUnavailable as exc:
                    if "rate limited" in str(exc) and attempt < RETRIES - 1:
                        time.sleep(RETRY_WAIT_S * (attempt + 1))
                        continue
                    print(f"profiles: embedding stopped: {exc}", file=sys.stderr)
                    return total
            print(f"  embedded {total} persona rows", flush=True)
            if limit and total >= limit:
                break
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write house profiles and embed the persona pitches.")
    parser.add_argument("--refresh", action="store_true", help="rewrite profiles that already exist")
    parser.add_argument("--limit", type=int, default=None, help="stop after this many listings")
    parser.add_argument("--city", default=None, help="only listings in this city")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--embed-only", action="store_true", help="skip the model; embed pitches that lack a vector")
    args = parser.parse_args(argv)

    if not args.embed_only:
        with SessionLocal() as session:
            ids = candidate_ids(session, refresh=args.refresh, limit=args.limit, city=args.city)
        print(f"profiles: {len(ids)} listings to write with {hp.model_name()} ({args.workers} workers)", flush=True)
        if ids:
            try:
                outcomes = run(ids, refresh=args.refresh, workers=args.workers)
            except llm.ModelUnavailable as exc:
                print(f"profiles: {exc}", file=sys.stderr)
                return 1
            print(f"profiles: {dict(outcomes)}", flush=True)
    embedded = embed_all()
    print(f"profiles: embedded {embedded} persona rows with {embedder.model_name()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
