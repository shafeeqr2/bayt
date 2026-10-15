"""Download City of Toronto open data and load it into the `city` schema.

Runs inside the GDAL image (see the `importer` service in docker-compose.yml)
via `./start.sh city-data`. Downloads are cached in data/city/ and only
re-fetched when the city publishes a newer version.
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

CKAN = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
CACHE = Path("/data")
PG = (
    f"PG:host={os.environ['PGHOST']} dbname={os.environ['PGDATABASE']} "
    f"user={os.environ['PGUSER']} password={os.environ['PGPASSWORD']}"
)

# (table, CKAN package, resource name). Geometry is loaded in EPSG:4326.
DATASETS = [
    ("zoning_area", "zoning-by-law", "Zoning Area - 4326.gpkg"),
    ("zoning_height", "zoning-by-law", "Zoning Height Overlay - 4326.gpkg"),
    ("zoning_lot_coverage", "zoning-by-law", "Zoning Lot Coverage Overlay - 4326.gpkg"),
    ("zoning_parking", "zoning-by-law", "Parking Zone Overlay - 4326.gpkg"),
    ("zoning_policy_area", "zoning-by-law", "Zoning Policy Area Overlay - 4326.gpkg"),
    ("zoning_rooming_house", "zoning-by-law", "Zoning Rooming House Overlay - 4326.gpkg"),
    ("parcels", "property-boundaries", "Property Boundaries - 4326.gpkg"),
    ("address_points", "address-points-municipal-toronto-one-address-repository", "Address Points - 4326.gpkg"),
    ("heritage", "heritage-register", "Heritage Register Data"),
    ("permits_active", "building-permits-active-permits", "building-permits-active-permits.csv"),
    ("permits_cleared", "building-permits-cleared-permits", "Cleared Building Permits since 2017.csv"),
    ("permits_cleared_2000_2016", "building-permits-cleared-permits", "Cleared Permits 2000 to 2016"),
]


def log(message: str) -> None:
    print(f"city-data: {message}", flush=True)


def resource(package: str, name: str) -> dict:
    with urllib.request.urlopen(f"{CKAN}/package_show?id={package}", timeout=60) as r:
        resources = json.load(r)["result"]["resources"]
    for res in resources:
        if res["name"] == name:
            return res
    sys.exit(f"city-data: resource {name!r} not found in {package!r}; the city may have renamed it")


def download(res: dict) -> Path:
    """Fetch a resource unless the cached copy matches the city's last_modified."""
    url = res["url"]
    path = CACHE / url.rsplit("/", 1)[-1]
    stamp = path.with_name(path.name + ".version")
    version = res.get("last_modified") or res.get("created") or ""
    if path.exists() and stamp.exists() and stamp.read_text() == version:
        return path

    log(f"downloading {path.name}")
    tmp = path.with_name(path.name + ".part")
    with urllib.request.urlopen(url, timeout=600) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    tmp.rename(path)
    stamp.write_text(version)
    return path


def source(path: Path) -> str:
    if path.suffix == ".zip":
        return f"/vsizip/{path}"
    return str(path)


def load(table: str, path: Path) -> None:
    log(f"loading city.{table}")
    args = [
        "ogr2ogr", "-f", "PostgreSQL", PG, source(path),
        "-nln", f"city.{table}",
        "-overwrite",
        "-lco", "GEOMETRY_NAME=geom",
        "-lco", "FID=ogc_fid",
        "-lco", "LAUNDER=YES",
        # Some city files declare numeric widths their values overflow.
        "-lco", "PRECISION=NO",
        "--config", "PG_USE_COPY", "YES",
        "-gt", "65536",
    ]
    if path.suffix == ".csv":
        args += ["-oo", "AUTODETECT_TYPE=NO", "-oo", "EMPTY_STRING_AS_NULL=YES"]
    else:
        args += ["-t_srs", "EPSG:4326", "-nlt", "PROMOTE_TO_MULTI", "-makevalid"]
    subprocess.run(args, check=True)


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    only = set(sys.argv[1:])
    for table, package, name in DATASETS:
        if only and table not in only:
            continue
        load(table, download(resource(package, name)))
    log("done")


if __name__ == "__main__":
    main()
