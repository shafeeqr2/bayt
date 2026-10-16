# Geodata primer

Plain-language answers to the questions that came up while building the lot analysis service.
See [lot-analysis.md](lot-analysis.md) for the method itself.

## What is a parcel boundary?

A parcel boundary is the legal outline of a single piece of land: the lot lines that define what a property owner owns.
It is the shape on a survey or a deed, drawn as a polygon on a map.

For a Toronto house that is usually a rectangle, say 12 m wide along the street by 38 m deep, with:

- the **front lot line** along the street
- two **side lot lines** shared with the neighbours
- the **rear lot line** at the back fence

Everything inside that outline is the lot the listing is selling.
The house footprint sits inside it, and the difference between the two is the open land.

The City of Toronto maintains these outlines for every property as its "Property Boundaries" dataset.
Each polygon carries a parcel ID, the address number and street, and the city's stated area.
In the analysis, this polygon is the denominator for lot coverage and the shape that gets measured for frontage, depth, rear yard and a possible split.

Two things worth knowing:

- **It is not a survey.** The city compiled it from records of varying age, so it is good for planning numbers, but a real severance or build still needs a licensed surveyor.
- **Not every parcel is one home.** The dataset marks parcels as COMMON (an ordinary lot), CONDO (a whole condo corporation, which can cover many townhouses) or RESERVE (a 0.3 m strip used to block access). The service only analyzes COMMON parcels and warns when the parcel area disagrees with the listing's lot size, which usually means a shared parcel.

## What is a parcel fabric?

"Parcel fabric" is the GIS term for a city's complete, seamless set of parcel boundaries, where every lot fits against its neighbours with no gaps or overlaps, like fabric.
Toronto's parcel fabric is published as the "Property Boundaries" dataset on Open Data and as the "Property Boundary" layer on the city's ArcGIS server.
The layer describes itself as "Parcel Mapping - Municipal Parcel Fabric."

## Is the Bayt lot service a GIS server?

No. The GIS server belongs to the City of Toronto. The Bayt service is a client of it.

- **The city's GIS server** at `gis.toronto.ca/arcgis/rest/services` is a public ArcGIS Server run by the City of Toronto.
  It hosts the parcel, building outline, zoning and centreline layers and answers spatial queries such as "which parcel contains this point" or "which building footprints overlap this polygon."
  Open Data Toronto also mirrors some of these layers to ArcGIS Online (`services3.arcgis.com/b9WvedVPoizGfvfD`); the service reads the Centreline from that mirror because the city's own Centreline service is slow.
  No account or key is needed. We do not run or control it.
- **The Bayt lot service** in `backend/app/lot/` is code in our backend.
  When someone asks for a listing's lot, it sends 6 to 8 small queries to the city's server, receives the polygons back, and does all the analysis itself: projecting to metres, finding the front lot line, unioning footprints, computing coverage, applying the zoning rules, testing the split and the garden suite.
  The result is cached in the Postgres table `lot_analyses`, so repeat requests do not hit the city at all.

The city provides raw shapes and attributes. The reasoning about what those shapes mean for a buyer happens in Bayt.

The trade-off is a runtime dependency on the city's server. If it is down, uncached requests return a 502.
If that becomes a problem, the alternative is to download the same datasets from Open Data Toronto (about 1 GB of GeoJSON) and load them into PostGIS, which would make Bayt its own GIS server.
The analysis code would not change, only the data access in `toronto.py`.

## ArcGIS Server vs parcel fabric

These are two different things.

- **ArcGIS Server** is software: Esri's product for publishing map data over the web. The City of Toronto runs an instance of it and hosts dozens of layers on it.
- **Parcel fabric** is a dataset: the city's parcel boundaries, served as one layer among many on that server.

In the code, `LAYERS["parcels"]` points at that one layer. The buildings, zoning and centreline layers on the same server are not part of the parcel fabric.

## What is Open Data?

Open Data is public-sector data that a government publishes for anyone to download and reuse, free of charge and under a permissive licence.
The idea is that data collected with public money should be available to the public.

The City of Toronto runs its portal at [open.toronto.ca](https://open.toronto.ca).
It hosts around 500 datasets, including the ones this service relies on: Property Boundaries, Building Outlines, the Zoning By-law layers, the street Centreline, and Address Points.
Each dataset page has a description, a refresh schedule, and downloads in several formats (GeoJSON, Shapefile, CSV, GeoPackage).
A programmatic API, built on a platform called CKAN, lets you search the catalogue and fetch records.

How the two city sources relate:

- **Open Data Toronto** is where the full datasets were downloaded to run the hypothesis test offline against all 724 Toronto listings in the seed. It is the official, documented, licensed way to get the data.
- **The city's ArcGIS server** hosts the live versions of the same datasets. The service uses it because it answers small spatial queries on demand, which the Open Data API cannot do (it has no "which parcel contains this point" filter).

Both are run by the City of Toronto and carry the same underlying data.
Open Data is the bulk download front door. The ArcGIS server is the query-by-location back door.

Most large Canadian cities have a similar portal (Mississauga, Vaughan, Ottawa, Vancouver), and the Government of Canada runs [open.canada.ca](https://open.canada.ca).

## Can we use open.canada.ca for all our data?

Not for this feature. open.canada.ca is the federal government's catalogue, and the data we need is owned at the other two levels of government.

- **Parcel boundaries are provincial.** Land ownership is registered by each province's land registry. In Ontario that is Teranet, whose parcel fabric is a paid, licensed product. There is no free national parcel layer on open.canada.ca. Toronto publishes its own municipal copy as Open Data, which is why Toronto works and most of the rest of Ontario would not.
- **Zoning is municipal.** Every city writes its own zoning by-law with its own zone codes, minimums and maps. The federal catalogue has nothing on it.
- **Building footprints are the one partial exception.** Statistics Canada's Open Database of Buildings on open.canada.ca compiles footprints from municipalities across the country, and Microsoft's ML-derived Canada footprints are also open. A 2019 comparison rated StatCan's set as precise but mostly limited to attached housing, and Microsoft's as better on detached homes but weak on row houses and downtowns. Either would do as a fallback for the house footprint, but without a parcel they cannot tell you the lot.

The two things that actually drive the analysis, lot lines and zoning, only exist at the municipal level.
Expanding beyond Toronto means adding each city's open parcel and zoning data one at a time.
Mississauga, Vaughan and Pickering, which appear in the seed, all publish parcels; their zoning layers would need checking.

A single national source for parcels is a commercial purchase: Teranet for Ontario, or a reseller such as Precisely that bundles provinces.
