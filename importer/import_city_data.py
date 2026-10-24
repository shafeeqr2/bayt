"""Download City of Toronto open data and load it into the `city` schema.

Runs inside the GDAL image (see the `importer` service in docker-compose.yml)
via `./start.sh city-data`. Downloads are cached in data/city/ and only
re-fetched when the city publishes a newer version.
"""

import csv
import datetime
import json
import os
import re
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

COA_MERGED = "committee-of-adjustment-applications-merged.csv"

# (table, CKAN package, resource name). Geometry is loaded in EPSG:4326.
DATASETS = [
    ("zoning_area", "zoning-by-law", "Zoning Area - 4326.gpkg"),
    ("zoning_height", "zoning-by-law", "Zoning Height Overlay - 4326.gpkg"),
    ("zoning_lot_coverage", "zoning-by-law", "Zoning Lot Coverage Overlay - 4326.gpkg"),
    ("zoning_parking", "zoning-by-law", "Parking Zone Overlay - 4326.gpkg"),
    ("zoning_policy_area", "zoning-by-law", "Zoning Policy Area Overlay - 4326.gpkg"),
    ("zoning_rooming_house", "zoning-by-law", "Zoning Rooming House Overlay - 4326.gpkg"),
    ("parcels", "property-boundaries", "Property Boundaries - 4326.gpkg"),
    # Every building footprint with its LiDAR height, for the 3D search map (~200 MB).
    ("buildings", "topographic-mapping-building-outlines", "Building Outlines - 4326.gpkg"),
    # City limits, so the map knows where city buildings end and OpenStreetMap's begin.
    ("boundary", "regional-municipal-boundary", "toronto-boundary-wgs84"),
    ("address_points", "address-points-municipal-toronto-one-address-repository", "Address Points - 4326.gpkg"),
    ("heritage", "heritage-register", "Heritage Register Data"),
    ("permits_active", "building-permits-active-permits", "building-permits-active-permits.csv"),
    ("permits_cleared", "building-permits-cleared-permits", "Cleared Building Permits since 2017.csv"),
    ("permits_cleared_2000_2016", "building-permits-cleared-permits", "Cleared Permits 2000 to 2016"),
    # Every Committee of Adjustment application (minor variances and consents)
    # since 2001, with the decision. Many files, merged into one table; see coa_csv().
    ("coa_raw", "committee-of-adjustment-applications", COA_MERGED),
]


def log(message: str) -> None:
    print(f"city-data: {message}", flush=True)


def package(name: str) -> dict:
    with urllib.request.urlopen(f"{CKAN}/package_show?id={name}", timeout=60) as r:
        return json.load(r)["result"]


def resource(package_name: str, name: str) -> dict:
    for res in package(package_name)["resources"]:
        if res["name"] == name:
            return res
    sys.exit(f"city-data: resource {name!r} not found in {package_name!r}; the city may have renamed it")


def download(res: dict, filename: str | None = None) -> Path:
    """Fetch a resource unless the cached copy matches the city's last_modified."""
    url = res["url"]
    path = CACHE / (filename or url.rsplit("/", 1)[-1])
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


def coa_csv(package_name: str) -> Path:
    """Merge the Committee of Adjustment files into one CSV with one header.

    The package has an "Active Applications" file, a "Closed Applications since
    2017" file and one "Closed Applications <year>" file per year back to 2001.
    Their headers differ slightly (REFERENCE_FILE vs REFERENCE_FILE#, WARD vs
    WARD_NUMBER + WARD_NAME), so columns are renamed to lower snake case and
    missing ones are left empty. A `source` column says which file a row came
    from. `app.city.coa` turns the result into a typed, geocoded table.
    """
    pkg = package(package_name)
    # The datastore dumps carry no last_modified of their own; the package is
    # refreshed daily, so its refresh time versions the cache instead.
    refreshed = (pkg.get("last_refreshed") or datetime.date.today().isoformat())[:10]
    files: list[tuple[str, Path]] = []
    for res in pkg["resources"]:
        if not res.get("datastore_active"):
            continue
        name = res["name"]
        if name == "Active Applications":
            source_tag = "active"
        elif re.fullmatch(r"Closed Applications( since)? \d{4}", name):
            source_tag = "closed"
        else:
            continue
        dump = {
            "url": f"{CKAN.rsplit('/api', 1)[0]}/datastore/dump/{res['id']}",
            "last_modified": f"{refreshed} {res.get('last_modified') or ''}",
        }
        files.append((source_tag, download(dump, filename=f"coa-{res['id']}.csv")))
    if not files:
        sys.exit(f"city-data: no Committee of Adjustment files found in {package_name!r}")

    merged = CACHE / COA_MERGED
    columns: list[str] = ["source"]
    rows: list[dict[str, str]] = []
    for source_tag, path in files:
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                clean = {_column(k): (v or "").strip() for k, v in row.items() if k}
                for column in clean:
                    if column not in columns:
                        columns.append(column)
                clean["source"] = source_tag
                rows.append(clean)
    with open(merged, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log(f"merged {len(rows)} Committee of Adjustment rows from {len(files)} files")
    return merged


def _column(name: str) -> str:
    """REFERENCE_FILE# -> reference_file, C_OF_A_DESCISION -> c_of_a_descision."""
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


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
    for table, package_name, name in DATASETS:
        if only and table not in only:
            continue
        if table == "coa_raw":
            load(table, coa_csv(package_name))
        else:
            load(table, download(resource(package_name, name)))
    log("done")


if __name__ == "__main__":
    main()
