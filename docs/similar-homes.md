# Similar homes

A buyer opens a listing and sees "Similar homes": 8 houses that are similar for the
reason this buyer cares about, with 1 line per house that says why. The same house
appeals to a first-time buyer, an investor, a flipper and a builder for different
reasons, so "similar" is computed 4 times, once per persona, and the buyer picks
the persona with a toggle on the listing page.

The plan this follows is `docs/similar-homes-plan.md`. This file says what was
built in phases 1 and 2 and how it behaves.

## The house profile (phase 1)

One model call per listing writes `app.similar.profile.Profile`: a fact layer and
4 persona views.

| Part | Fields | Lives in |
|---|---|---|
| Facts | era, style, layout, kitchen and bath finish 1 to 5, condition, renovation era, basement, basement suite, separate entrance, outdoor, light, a 3 to 5 sentence summary | `listing_profiles.facts` |
| Persona view, x4 | score 1 to 10 on a rubric, a 3 to 5 sentence pitch in the persona's words, 3 to 6 signals, 0 to 3 concerns | `listing_persona_profiles`, 1 row per persona |
| Embedding | the pitch plus its signals as a 2048-float vector, with the embedding model's name | `listing_persona_profiles.embedding` (pgvector) |

The model sees:

- the listing facts, the description and the room list;
- the price against the median of the same building type in the community (or the city when the community has fewer than 5 such listings);
- the city data row (zone, height limit, parcel size, heritage) and the lot analysis verdicts (severance, garden suite, coverage, as-of-right units) when the listing has them;
- the investment estimate (rent, units, yield, cap rate, suite evidence);
- the photo labels when the listing has them, else up to 8 of the photos themselves as JPEG data URLs at 800 px (the free vision hosts take bytes, not URLs).

The rubrics are in `RUBRICS`, one per persona, with what the persona cares about
and what a 9-10, 6-8, 3-5 and 1-2 look like. The prompt forbids the address, the
street, the community name and the dollar price in a pitch, so location and price
stay out of the vector; `clean()` scrubs them anyway and clamps the scores.

Rows carry the model and `PROMPT_VERSION`; a changed prompt writes again. Writing
is explicit: `POST /api/listings/{id}/profile` for one listing, `./start.sh
profiles` for all of them. Opening a listing page never calls the model.

### Models

| Provider | Profile model | Embedding model |
|---|---|---|
| OpenRouter (`sk-or-`) | `nvidia/nemotron-3.5-super-vl:free` | `nvidia/nemotron-3.5-embed-1b:free` |
| NVIDIA NIM (`nvapi-`) | `nvidia/nemotron-3.5-super-vl` | `nvidia/llama-3.2-nv-embedqa-1b-v2` |
| Anthropic (`sk-ant-`) | `claude-opus-5-5` | none: pitches are stored but not searchable |

`PROFILE_MODEL` and `EMBED_MODEL` in `.env` override these. The free listings on
OpenRouter answer the profile call in about 9 s with 8 photos and under 1 s
without, cost nothing, and allow about 1,000 requests a day on an account with
credits. The backfill takes Toronto houses first, then townhouses, then condos,
and can be run again the next day for the rest; the embeddings go in batches of
200 texts per request, so they use few of the day's requests.

Measured on 2026-10-28: the first run wrote 971 profiles in about 1 hour with 3
workers, then every call dropped the connection (`ReadError`) for 6 hours until
the day's quota reset. A failed call stores the reason in the row's `note` with
`facts` null, so the next run tries that listing again. When 20 listings fail in
a row the job now stops and says so, instead of retrying each remaining listing
3 times on a host that is not answering.

## Similar homes (phase 2)

`GET /api/listings/{id}/similar?persona=investor` (`app.similar.service`):

1. **Hard filters.** The same persona's rows with a current embedding, price within
   25% of the source, within 5 km of it. Under 5 candidates: drop the radius, then
   the band; the answer lists the filters that held.
2. **Nearest neighbours.** Cosine distance to the source pitch, 30 candidates. With
   a few thousand listings this is an exact scan in milliseconds; an HNSW index can
   come when the count passes 50,000.
3. **Rerank.** One model call with the source's pitch, signals and concerns and the
   30 candidates' pitches and signals returns the best 8 in order with 1 reason
   line each (at most 22 words, facts only) and 1 line on what sets the source
   apart. Ids the model invents are dropped. Without a model, or when it fails,
   the answer is the nearest-neighbour order with the shared signals as the reason.

The reranked answer is cached in `similar_results` for 24 hours, keyed by the
persona and the candidate ids, so a new profile in the neighbourhood makes a new
answer and a repeat visit costs nothing.

On the listing page (`frontend/app/listings/[id]/similar-row.tsx`) the row shows
the 4 personas with this house's score for each, the active persona's pitch,
signals and concerns, the "what sets this home apart" line, and the 8 cards with
their score and reason. The toggle is `?persona=` on the page URL, so the row is a
server component. Buyer mode defaults to the first-time buyer.

### Where the scores show

Every listing summary carries `persona_scores` (the 4 scores, null until the
profile is written), fetched in 1 query per page:

- **Search cards** show 1 badge: the chosen buyer's score when the search has a
  buyer type ("I am a" select, `?persona=`), else the persona the house suits
  best. The card link keeps the persona, so the listing opens on that buyer.
- **Sort "Best fit"** (`sort=fit`) orders the search by that persona's score,
  highest first, unprofiled listings last.
- **Listing header** shows the 4 scores as chips; each one links to the similar
  row for that buyer.

## Checks

`tests/test_similar.py` covers the prompt blocks, the scrub and clamp, the
embedding client (batching, dimension check, NIM's `input_type`), the rerank id
guard, the fallback reasons and the cache key.

Gate 1 of the plan (50 profiles read by hand, rubric fixed) and gate 2 (100 pair
judgments, 70% agreement with the top 5) are not done yet.
