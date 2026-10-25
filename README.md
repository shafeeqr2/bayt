# Bayt

Real estate search that gives buyers clarity before they purchase.
See the [product brief](docs/product-brief.md) for goals, users, and features.

## Quick start

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running) and Node.js 20.9+ (24 recommended, see `frontend/.nvmrc`).

```bash
git clone https://github.com/kkamilahmed/bayt.git
cd bayt
./start.sh
```

Then open:

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

The first run builds the backend image, creates the database, runs migrations, and seeds about 2,300 Toronto listings.
Later runs reuse the database and start in seconds.

## How it fits together

See [docs/architecture.md](docs/architecture.md) for a diagram of the services and the external data sources they call.

| Part | Tech | Runs in |
|---|---|---|
| `frontend/` | Next.js 16 (App Router, Tailwind) | Your machine, via `./start.sh` |
| `backend/` | FastAPI, SQLAlchemy 2, Alembic | Docker (`backend` service) |
| Database | Postgres 17 + PostGIS | Docker (`db` service), data in the `pgdata` volume |

The Next.js dev server runs outside Docker on purpose.
Next.js recommends against running it in Docker on macOS and Windows, because file watching through Docker Desktop makes Fast Refresh slow or unreliable.
The backend source is mounted into its container, so Python changes reload automatically.

The frontend talks to the API from the server side only, using `BACKEND_URL` (set by `./start.sh`).

## Everyday commands

```bash
./start.sh                     # start everything
./start.sh backend             # start only Postgres + API
./start.sh down                # stop Postgres + API (data is kept)
./start.sh reset               # wipe your local database and reseed
./start.sh city-data           # load or refresh City of Toronto data (zoning, lots, permits, Committee of Adjustment)
./start.sh test                # run backend tests
./start.sh logs                # follow backend logs
./start.sh psql                # open a Postgres shell
./start.sh help                # list all commands
```

If a port is already taken on your machine, change it in `.env` (created from `.env.example` on first run).
Postgres is exposed on 5433 by default so it does not clash with a local Postgres on 5432.

## Map search

The search page has a List | Map toggle (`?view=map`).
Map mode shows every home matching the filters as a price pin on a tilted MapLibre map over free [OpenFreeMap](https://openfreemap.org) tiles (no key, no request limits).
Pins cluster when zoomed out; clicking a cluster zooms in and clicking a pin opens a card that links to the listing.
The pins come from `GET /api/listings/map`, which takes the same filters as `GET /api/listings` but returns every match without paging, proxied to the browser by `frontend/app/api/pins/route.ts`.

From zoom 14 the map extrudes buildings in 3D.
Inside Toronto these are the city's own building outlines with LiDAR-measured heights, served as vector tiles straight from PostGIS by `GET /api/tiles/buildings/{z}/{x}/{y}` (`backend/app/city/tiles.py`) once `./start.sh city-data` has loaded them.
Outside the city limits (`GET /api/city/boundary`) the map falls back to OpenStreetMap's buildings, which only have heights where someone has mapped them.

## City of Toronto data (zoning, lots, permits)

Listing pages show the lot boundary and size, zoning, parking rules, heritage status, and building permits for City of Toronto listings.
Parking rules come from Chapter 200 of By-law 569-2013 (`backend/app/city/parking.py`): since 2022 Toronto requires no parking for houses, houseplexes or secondary suites, and only caps resident parking in new apartment buildings by Parking Zone.
That data comes from [Toronto Open Data](https://open.toronto.ca/) and is too large for git, so load it once:

```bash
./start.sh city-data
```

The first run downloads about 1 GB into `data/city/` and takes a few minutes.
Re-run it any time to refresh; files the city has not changed are not downloaded again.

| Table (`city` schema) | Source dataset | Rows |
|---|---|---|
| `address_points` | Address Points (Municipal) | ~525k |
| `parcels` | Property Boundaries | ~500k |
| `buildings` | Topographic Mapping - Building Outlines (every footprint with its LiDAR height; drives the 3D search map) | ~558k |
| `boundary` | Regional Municipal Boundary (city limits, so the map knows where city buildings end) | 1 |
| `zoning_area` + `zoning_*` overlays | Zoning By-law 569-2013 (zones, height, lot coverage, parking, policy areas, rooming houses) | ~17k |
| `heritage` | Heritage Register | ~12k |
| `permits_active`, `permits_cleared`, `permits_cleared_2000_2016` | Building Permits | ~1.1M |

`backend/app/city/match.py` then links each listing to the city:

1. **Address:** same street number and name as the listing, closest to its map pin, or failing that the nearest address within 40 m.
2. **Lot:** the property parcel that contains that address. Frontage and depth are approximated from the lot's bounding rectangle.
3. **Zoning:** the zone and overlays at a point inside the lot.
4. **Permits:** looked up live by address point ID (`GEO_ID` in the permit data).

Coverage today: every City of Toronto listing with a usable address (1,855) matches an address and a lot.
About 30% have no zone because their sites (mostly condo buildings) are outside By-law 569-2013 and follow former municipal or site-specific by-laws.
Listings in Vaughan, Markham, Mississauga and other cities have no city data.

The importer runs in a GDAL container (`importer` service in `docker-compose.yml`).
The `city` schema is owned by the importer, not by Alembic, so migrations never touch it.

## Lot analysis

The API reports how much of a lot the house takes up and whether the lot could take another home (a severance or a garden suite).
Nobody publishes this ready-made: the City of Toronto publishes lot outlines and building outlines separately, and the backend computes the ratio and the zoning tests itself.
Only Toronto addresses are covered.

### Calling it

With the backend running on the default port, the two URLs are:

```bash
# For a listing in the database (result cached for 30 days; add ?refresh=true to recompute)
curl http://localhost:8000/api/listings/30403339/lot

# For any point in Toronto, not tied to a listing
curl "http://localhost:8000/api/lot?lat=43.7153901&lon=-79.2914554"
```

Both are also listed under http://localhost:8000/docs.

The first call for a listing takes a few seconds because it goes to the city's GIS; the result is then cached for 30 days.
To fill that cache for every Toronto listing ahead of time (so listing pages show the lot map and coverage at once), run:

```bash
./start.sh lot-analysis            # every Toronto listing without a fresh result; re-run to retry failures
./start.sh lot-analysis --refresh  # recompute everything, e.g. after the city's quarterly building-outline update
```

Condo listings are skipped: their parcel covers the whole condo corporation, so lot coverage means nothing for them.
Behind the scenes the backend sends 6 to 8 small queries to the City of Toronto's public GIS server (`https://gis.toronto.ca/arcgis/rest/services/...`) for the parcel, neighbouring parcels, building footprints, zoning, lot coverage overlay, sixplex permission and street centrelines, then does the geometry in Python. The centreline query goes to Open Data Toronto's ArcGIS Online mirror of the same layer (`services3.arcgis.com/b9WvedVPoizGfvfD/...`), which answers in well under a second while the city's own Centreline service often queues requests for a minute; the city's layer is kept as a fallback.
See [docs/lot-analysis.md](docs/lot-analysis.md) for the method and accuracy and [docs/geodata-primer.md](docs/geodata-primer.md) for what parcels, parcel fabric, GIS servers and Open Data are.

### How much of the lot the house takes up

Read the `coverage` object in the response. For 17 Hollydene Rd (listing `30403339`):

```json
"coverage": {
  "building_footprint_m2": 77.8,
  "main_building_m2": 77.8,
  "ancillary_m2": 0.0,
  "coverage_pct": 16.8,
  "open_pct": 83.2,
  "max_coverage_pct": 33.0,
  "max_coverage_pct_with_houseplex": 45.0,
  "remaining_buildable_footprint_m2": 75.4
}
```

| Field | Meaning |
|---|---|
| `coverage_pct` | All structures divided by lot area. The house takes up 16.8% of this lot. |
| `open_pct` | The rest: 83.2% is not built on. |
| `main_building_m2` / `ancillary_m2` | The house versus garages and sheds, using the city's own classification. |
| `max_coverage_pct` | Zoning cap from the Lot Coverage Overlay. `null` means the zone has no cap. |
| `max_coverage_pct_with_houseplex` | The cap rises to 45% for a multiplex (houseplex). |
| `remaining_buildable_footprint_m2` | Ground area still allowed under the cap: another 75 m² here. |

Each footprint is also listed under `buildings` with its area, height and type, and the polygons for the parcel, buildings, front lot line and rear yard are in `geometry` as GeoJSON for drawing on a map.
The listing page draws exactly that: the lot to scale with the building footprints, front lot line and rear yard, next to the coverage figures against the zoning cap.
Below it, a 3D view extrudes the house and every building within about 75 m to the city's LiDAR heights (`geometry.buildings` and `geometry.nearby_buildings` carry `height_m`), over a free [OpenFreeMap](https://openfreemap.org) basemap, with the zoning height limit drawn as a translucent ceiling over the lot.

"Open" means not built on. Driveways, patios and pools are not in the footprint data, so open land is not necessarily green.

### The rest of the response

- `parcel`: lot area, frontage (measured the way the zoning by-law does), depth, and flags for corner lots, laneways and irregular shapes.
- `zoning`: zone label (for example `RD (f15.0; a550) (x5)`), minimum frontage and lot area, and how many units are allowed as of right (4, or 6 in sixplex wards).
- `severance`: whether the lot could be split in two, with each half checked against the zone minimums and the prevailing lot pattern on the street.
- `garden_suite`: whether a garden suite fits in the rear yard after the by-law's separation, setbacks and footprint caps.
- `caveats`: warnings such as a shared condo parcel or a site-specific zoning exception. Read these before trusting the verdicts.

## Possible floor plan

Listings rarely include a floor plan, but they list each room with its level and size.
The backend fits those rooms into the city's building outline, level by level, and the listing page draws the result under "Possible layout".

```bash
curl http://localhost:8000/api/listings/30403436/floorplan
```

It is a plausible arrangement, never the real one.
Rooms follow common layouts: the living room at the front, the kitchen and family room at the back, the kitchen beside the dining room, bedrooms on an exterior wall.
Parts listings leave out are added and marked as assumed: one stair in the same place on every level, bathrooms from the bathroom count, and an attached garage when the parking type says so.
A room up to 15% larger than the space available is drawn smaller and flagged; a room that still does not fit is listed under "Not drawn".
It needs the lot analysis, so it covers Toronto houses only; condos and other cities get a one-line reason instead.
The method is in the docstring of `backend/app/lot/floorplan.py`.

## Zoning pathways

For a Toronto house, the API compares a proposal (an addition, a rebuild, more units, a garden or laneway suite, a severance) with Zoning By-law 569-2013 and lists the public routes that address each shortfall, with their risks. Phase 1 is deterministic: rule resolution, gap analysis and a hand-written playbook matched by predicate. No language model is involved. The listing page has the form under "What could you build here?".

```bash
curl -X POST http://localhost:8000/api/listings/30403339/zoning/pathways \
  -H 'content-type: application/json' \
  -d '{"mode": "buyer", "keep_existing_walls": true, "proposed_rear_setback_m": 8.0, "proposed_storeys": 2}'
curl http://localhost:8000/api/zoning/playbook   # every playbook card with its trigger and legal basis
curl "http://localhost:8000/api/listings/30403339/zoning/precedents?radius_m=500"   # nearby Committee of Adjustment files
curl -X POST http://localhost:8000/api/listings/30403339/zoning/ask \
  -H 'content-type: application/json' \
  -d '{"mode": "buyer", "text": "Keep the house and add a third storey about 10.5 m high"}'
```

With `LLM_API_KEY` in `.env`, the `ask` endpoint (and the form) reads the plan from plain words and writes a short answer in which every paragraph cites a route, a by-law clause, a standard or a nearby file from the analysis; paragraphs that cite nothing in it are dropped. The provider follows the key: an Anthropic key (`sk-ant-`) uses Claude through the Anthropic SDK; an OpenRouter key (`sk-or-`) or an NVIDIA key (`nvapi-`) uses an NVIDIA Nemotron model through the OpenAI-style chat API. `ZONING_MODEL` picks another model. A new question takes about 5 s, a repeated plan under 1 s. Without a key the form still works on the detail fields and shows the deterministic result.

Once `./start.sh city-data` has loaded the Committee of Adjustment open data (every minor variance and consent application since 2001, placed on the city's address points), the answer also shows what the committee decided on comparable files near the lot, and the listing page lists the nearest decisions. The open data has the decision and the description, not the variance table.

Design and module notes: [`docs/zoning-pathways.md`](docs/zoning-pathways.md).

## Tests

```bash
./start.sh test
```

## Changing the database

1. Edit the models in `backend/app/models.py`.
2. Generate and apply a migration:
   ```bash
   ./start.sh migration "add rent estimate to listings"
   ```
3. Review the new file in `backend/alembic/versions/` and commit it with your model change.

Teammates get it automatically: the backend runs `alembic upgrade head` every time it starts.
If two people add migrations at the same time, Alembic will report multiple heads.
Fix it by pulling, then running `docker compose exec backend alembic merge heads -m "merge"`.

## Seed data

`backend/seed/*.json.gz` holds raw REALTOR.ca listing exports from Apify (`igolaizola/realtor-canada-scraper-ppe`).
On startup the backend seeds them into an empty database (`backend/app/seed.py`).
Vacant land and placeholder prices are skipped, and the full source payload is kept in the `raw` column.

To add a newer export:

1. Export the Apify dataset as JSON (all fields).
2. `gzip -9 -c export.json > backend/seed/<date>.json.gz`
3. `./start.sh reset`

If the same listing appears in several files, the newest file wins.

Photos are not stored locally.
The database keeps REALTOR.ca's photo URLs, which stop working when a listing comes off the market.

This data is scraped from REALTOR.ca for internal prototyping only.
Keep the repo private, and do not publish the data or photos.
