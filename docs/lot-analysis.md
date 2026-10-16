# Lot analysis: coverage and infill potential

Bayt answers two questions about a listing's land:

1. What share of the lot is covered by buildings, and how much is open?
2. Could the lot take another home, either by severing it into two lots or by adding a garden suite?

Endpoints: `GET /api/listings/{id}/lot` (cached 30 days per listing) and `GET /api/lot?lat=&lon=` (any point in Toronto, not cached).
Code lives in `backend/app/lot/`.

## The investigation (October 2026)

The original idea was to pull recent SAR satellite imagery for the listing's GPS position and detect the house footprint from it. We tested whether that was necessary before building it.

### Why not satellite imagery

- **Free SAR is far too coarse.** Sentinel-1 pixels are about 10 m. A typical Toronto lot is 6 to 15 m wide, so a whole house is one or two pixels. Published Sentinel-1 work maps built-up *areas* at neighbourhood scale with 85 to 92% agreement; it does not produce per-house footprints.
- **Commercial SAR is expensive and still hard to use.** Umbra and Capella sell 25 to 50 cm spotlight scenes (roughly US$190/km² archive on SkyWatch, 25 km² minimum). Radar images have layover and shadow effects around buildings, so extracting a clean footprint is a research problem, not a lookup.
- **Optical would be the right imagery if we needed imagery**, but we would still have to run a footprint model and find the parcel boundary from somewhere else. The footprint is useless without the lot line.

### What already exists

| Source | What it gives | Verdict |
|---|---|---|
| City of Toronto Property Boundaries | Parcel polygons for every lot, refreshed daily, with address and street | Use it: this is the lot line |
| City of Toronto Building Outlines | LiDAR-derived footprints with height and type (building, garage, shed), refreshed quarterly | Use it: this is the house |
| City of Toronto Zoning By-law 569-2013 layers | Zone label with minimum frontage and lot area, Lot Coverage Overlay, Sixplex Permission | Use it: this decides what is allowed |
| City of Toronto Centreline | Street and laneway centrelines with names | Use it: tells us which lot line is the front |
| Microsoft / Overture / StatCan Open Database of Buildings | ML-derived footprints, country-wide | Fallback for cities without municipal data; less accurate on attached housing |
| Teranet parcel fabric | Province-wide parcels | Licensed, paid; not needed inside Toronto |

All four city datasets are on Open Data Toronto as downloads **and** as live ArcGIS FeatureServer layers under `https://gis.toronto.ca/arcgis/rest/services/`. The live layers answer a point-in-polygon or bounding-box query in well under a second, so the service queries them on demand and caches the result. The one exception is the Centreline: its service on `gis.toronto.ca` regularly queues requests for a minute at a time, so the code reads the Centreline from Open Data Toronto's ArcGIS Online mirror (`services3.arcgis.com/b9WvedVPoizGfvfD/arcgis/rest/services/COTGEO_CENTRELINE`, same fields, same refresh) and only falls back to the city's layer when the mirror fails. No PostGIS, no 1 GB download, no imagery pipeline.

### Hypothesis test

We matched the 724 Toronto houses in the seed data against the downloaded datasets.

| Check | Result |
|---|---|
| Listing coordinate lands in or within 20 m of a parcel | 724 of 724 |
| Parcel area vs REALTOR.ca "W x D" lot size, median ratio | 1.00 |
| Parcel area within 15% of the listed lot size | 629 of 722 |
| Measured frontage within 1 m of listed frontage (regular lots) | about 85% offline; on live spot checks regular lots agree to 0.1 m |
| Lot coverage, median across detached houses | 33% (Toronto's typical RD cap is 33 to 35%) |

The misses are corner lots (fixed by using the by-law rule that the front lot line is the shorter street line), pie-shaped and irregular lots (flagged with `irregular: true` and `frontage_confidence`), and condo townhouse parcels that cover several homes (flagged when the parcel area disagrees with the listing's lot size by more than 25%).

## How the analysis works

Everything is computed in metres in EPSG:2952 (MTM zone 10).

1. **Parcel**: the COMMON parcel containing the point, else the nearest within 15 m.
2. **Frontage**: boundary segments not shared with a neighbouring parcel are "open" edges. Open edges that run along a street centreline are street lines. The front lot line is the shorter street line (corner lots) or the only one. Frontage is reported the way the by-law measures it, between the side lot lines 6 m back from the street, which also sidesteps rounded corners; the curb-side length is returned separately as `front_lot_line_m`. Depth is the lot's extent perpendicular to the front.
3. **Coverage**: footprints clipped to the parcel, overlapping outlines unioned (the city's data has stacked roof segments), slivers under 2 m² dropped. Main building vs garage/shed is taken from the city's subtype.
4. **Zoning**: zone label (`RD (f15.0; a550) (x5)`), minimum frontage and lot area from the label or the chapter defaults (R 6 m, RD 12 m, RS 15 m, RT 6 m, RM 12 m; area = frontage × 30 m), maximum coverage from the Lot Coverage Overlay (bumped to 45% for a houseplex), as-of-right units (4 since the 2023 multiplex by-law, 6 where the Sixplex Permission layer applies).
5. **Severance**: split the lot side by side; each half must meet the minimum frontage and area. Reports whether the existing house sits on one half, and how the proposed frontage compares to the lots on the same street within 100 m, because the Committee of Adjustment weighs the prevailing lot pattern.
6. **Garden suite** (Chapter 150.7): rear yard behind the rear main wall; buildable box after 5.0 m separation from the house and 1.5 m rear setback; side setback max(0.6 m, 10% of frontage) up to 3.0 m; footprint capped at min(40% of rear yard, 60 m², 20% of lot for all ancillary buildings). Height 4.0 m, or 6.0 m with 7.5 m separation. Flags lots with no 1.0 m side path (fire access) and lots on a laneway (laneway-suite rules apply instead).

Verdicts are `likely`, `possible` (within 10% of a minimum, or blocked only by access), `unlikely`, `not_applicable` (not a low-rise residential zone) or `unknown`.

## Limits

- Toronto only. Other GTA cities in the seed (Mississauga, Vaughan, Pickering) return 404; Peel, York and Durham publish similar open data and could be added behind the same interface.
- Parcel mapping is for planning purposes and is not a survey. Zoning figures are the general chapter rules; site-specific exceptions (`x###` in the label) are flagged but not interpreted, and heritage, ravine and tree protection are not checked.
- Building outlines are LiDAR-derived and refresh quarterly, so a brand-new build or demolition can lag.
- Depends on the city's GIS being up; failures return 502. Results are cached per listing for 30 days.

## On the listing page and in the cache

The listing page's "Lot & zoning" section draws the parcel, building footprints, front lot line and rear yard to scale and shows the coverage figures against the zoning cap.
It falls back to the parcel outline alone while the analysis loads, outside Toronto, or when the city's GIS is down.

Under it, a 3D view (MapLibre GL JS over OpenFreeMap tiles, both free and keyless) extrudes the house and its neighbours to the heights in the city's building outlines and floats the zoning height limit as a thin slab over the lot, so a buyer can see what "9 m, 2 storeys" means against the street.
For that, `geometry.buildings` and `geometry.nearby_buildings` are GeoJSON Features with `height_m`, `kind` and `is_main`; nearby footprints come from one envelope query 75 m around the parcel, and a building that straddles the lot line (a semi) is split so only our half counts towards coverage while the neighbour's half still shows in 3D.
Nothing underground is drawn: the city's watermain and sewer layers exist as open data but say nothing a buyer acts on from a map; watermain age and nearby break counts would be worth adding as facts instead.

`./start.sh lot-analysis` (`python -m app.lot.backfill`) precomputes the analysis for every Toronto listing so pages never wait on the city.
It skips listings with a fresh cached result, counts the ones the city cannot place on an ordinary parcel (condos), and leaves failures uncached so a re-run retries them.
Queries are sent as POST: the city's firewall rejects GET URLs carrying a parcel polygon with more than a few dozen vertices.

## Next steps

- Show the severance and garden-suite verdicts on the listing page, and let search filter on them.
- Watermain facts (material, install year, breaks nearby) from Toronto Water's open data.
- Add other municipalities' open data behind `LotInputs`.
