"""Match listings to City of Toronto open data and store the result.

Run with `python -m app.city.match` (done for you by `./start.sh city-data`
and on backend start when city data is loaded but not yet matched).

For each listing:
1. Address point: same street number and street name as the listing, closest
   to the listing's pin (a mismatched street type is tolerated near the pin).
   Falls back to the nearest address point within NEAREST_MAX_M of the pin.
2. Lot: the property parcel containing that address point.
3. Zoning and overlays: whatever contains a point inside the lot.
4. Heritage: a heritage register entry on the lot.
"""

import argparse

from sqlalchemy import Connection, text

from app.city.address import parse
from app.db import engine

ADDRESS_MAX_M = 2000  # Same number and street name, but this far from the pin: wrong street.
NEAREST_MAX_M = 40
TYPE_MISMATCH_MAX_M = 300

# SQL twin of app.city.address.normalize_name.
NAME_SQL = "trim(regexp_replace(regexp_replace(upper({col}), '[.'']', '', 'g'), '\\s+', ' ', 'g'))"
AP_NAME = NAME_SQL.format(col="linear_name")

INDEXES = [
    f"CREATE INDEX IF NOT EXISTS address_points_number_name ON city.address_points (upper(address_number), ({AP_NAME}))",
    "CREATE INDEX IF NOT EXISTS permits_active_geo_id ON city.permits_active (geo_id)",
    "CREATE INDEX IF NOT EXISTS permits_cleared_geo_id ON city.permits_cleared (geo_id)",
    "CREATE INDEX IF NOT EXISTS permits_cleared_2000_2016_geo_id ON city.permits_cleared_2000_2016 (geo_id)",
]

MATCH_SQL = f"""
WITH listing AS (
    SELECT l.id, ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326) AS pin,
           p.number, p.name, p.street_type, p.direction
    FROM listings l
    LEFT JOIN tmp_parsed_address p ON p.listing_id = l.id
    WHERE l.latitude IS NOT NULL
),
by_address AS (
    SELECT DISTINCT ON (li.id)
           li.id, a.ogc_fid AS ap, ST_Distance(a.geom::geography, li.pin::geography) AS dist
    FROM listing li
    JOIN city.address_points a
      ON upper(a.address_number) = li.number
     AND {AP_NAME} = li.name
     AND (li.direction IS NULL OR a.linear_name_dir = li.direction)
    CROSS JOIN LATERAL (
        SELECT li.street_type IS NULL OR a.linear_name_type = li.street_type AS type_matches
    ) t
    -- A wrong street type ("Kennedy Street" for Kennedy Rd) is a common listing
    -- typo, so accept it, but only close to the pin and after exact matches.
    WHERE ST_DWithin(
        a.geom::geography, li.pin::geography,
        CASE WHEN t.type_matches THEN {ADDRESS_MAX_M} ELSE {TYPE_MISMATCH_MAX_M} END
    )
    ORDER BY li.id, t.type_matches DESC, dist
),
by_nearest AS (
    SELECT li.id, near.ap, near.dist
    FROM listing li
    CROSS JOIN LATERAL (
        SELECT a.ogc_fid AS ap, ST_Distance(a.geom::geography, li.pin::geography) AS dist
        FROM city.address_points a
        ORDER BY a.geom <-> li.pin
        LIMIT 1
    ) near
    WHERE near.dist <= {NEAREST_MAX_M}
      AND li.id NOT IN (SELECT id FROM by_address)
),
matched AS (
    SELECT id, ap, dist, 'address' AS method FROM by_address
    UNION ALL
    SELECT id, ap, dist, 'nearest' FROM by_nearest
),
lot AS (
    SELECT m.*, a.geom AS ap_geom, a.address_point_id, a.address_full,
           NULLIF(a.municipality_name, 'None') AS municipality, NULLIF(a.ward_name, 'None') AS ward,
           parcel.parcelid, parcel.geom AS lot_geom
    FROM matched m
    JOIN city.address_points a ON a.ogc_fid = m.ap
    LEFT JOIN LATERAL (
        SELECT p.parcelid, p.geom
        FROM city.parcels p
        WHERE ST_Intersects(p.geom, a.geom) AND p.feature_type IN ('COMMON', 'CONDO')
        ORDER BY ST_Area(p.geom)
        LIMIT 1
    ) parcel ON true
),
probe AS (
    SELECT lot.*,
           COALESCE(ST_PointOnSurface(lot_geom), ap_geom) AS pt,
           ST_OrientedEnvelope(ST_Transform(lot_geom, 2952)) AS envelope
    FROM lot
)
INSERT INTO listing_city_data (
    listing_id, match_method, match_distance_m,
    address_point_id, address_full, former_municipality, ward,
    parcel_id, lot_area_m2, lot_frontage_m, lot_depth_m, lot_geojson,
    zone_category, zone_string, zone_exception, zoning_bylaw_section,
    height_limit_m, height_limit_storeys, lot_coverage_pct, parking_zone,
    policy_area, rooming_house_area, heritage_status
)
SELECT
    pr.id, pr.method, round(pr.dist::numeric, 1),
    pr.address_point_id::int, pr.address_full, pr.municipality, pr.ward,
    pr.parcelid::int,
    round(ST_Area(pr.lot_geom::geography)::numeric, 1),
    round(LEAST(side1, side2)::numeric, 1),
    round(GREATEST(side1, side2)::numeric, 1),
    ST_AsGeoJSON(pr.lot_geom, 7)::jsonb,
    zone.zn_zone, zone.zn_string,
    NULLIF(zone.excptn_no, 0)::text,
    NULLIF(zone.zbl_sectn, 'None'),
    NULLIF(height.ht_label, -1),
    NULLIF(height.ht_stories, -1)::int,
    NULLIF(coverage.prcnt_cver, -1),
    parking.zn_parkzone,
    policy.policy_id::text,
    NULLIF(rooming.rmg_string, 'None'),
    heritage.status
FROM probe pr
CROSS JOIN LATERAL (
    SELECT ST_Distance(ST_PointN(ST_ExteriorRing(pr.envelope), 1), ST_PointN(ST_ExteriorRing(pr.envelope), 2)) AS side1,
           ST_Distance(ST_PointN(ST_ExteriorRing(pr.envelope), 2), ST_PointN(ST_ExteriorRing(pr.envelope), 3)) AS side2
) dims
LEFT JOIN LATERAL (SELECT * FROM city.zoning_area z WHERE ST_Intersects(z.geom, pr.pt) LIMIT 1) zone ON true
LEFT JOIN LATERAL (SELECT * FROM city.zoning_height z WHERE ST_Intersects(z.geom, pr.pt) LIMIT 1) height ON true
LEFT JOIN LATERAL (SELECT * FROM city.zoning_lot_coverage z WHERE ST_Intersects(z.geom, pr.pt) LIMIT 1) coverage ON true
LEFT JOIN LATERAL (SELECT * FROM city.zoning_parking z WHERE ST_Intersects(z.geom, pr.pt) LIMIT 1) parking ON true
LEFT JOIN LATERAL (SELECT * FROM city.zoning_policy_area z WHERE ST_Intersects(z.geom, pr.pt) LIMIT 1) policy ON true
LEFT JOIN LATERAL (SELECT * FROM city.zoning_rooming_house z WHERE ST_Intersects(z.geom, pr.pt) LIMIT 1) rooming ON true
LEFT JOIN LATERAL (
    SELECT h.status FROM city.heritage h
    WHERE pr.lot_geom IS NOT NULL AND ST_Intersects(h.geom, pr.lot_geom)
    LIMIT 1
) heritage ON true
"""


def city_data_loaded(conn: Connection) -> bool:
    return bool(conn.scalar(text("SELECT to_regclass('city.address_points') IS NOT NULL")))


def rebuild(conn: Connection) -> int:
    for statement in INDEXES:
        conn.execute(text(statement))

    conn.execute(text(
        "CREATE TEMP TABLE tmp_parsed_address "
        "(listing_id text PRIMARY KEY, number text, name text, street_type text, direction text) "
        "ON COMMIT DROP"
    ))
    rows = [
        {"listing_id": listing_id, **vars(parsed)}
        for listing_id, address in conn.execute(text("SELECT id, address FROM listings"))
        if (parsed := parse(address))
    ]
    if rows:
        conn.execute(
            text(
                "INSERT INTO tmp_parsed_address VALUES "
                "(:listing_id, :number, :name, :street_type, :direction)"
            ),
            rows,
        )

    conn.execute(text("DELETE FROM listing_city_data"))
    return conn.execute(text(MATCH_SQL)).rowcount


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--if-needed",
        action="store_true",
        help="only run when city data is loaded and no listing has been matched yet",
    )
    args = parser.parse_args()

    with engine.begin() as conn:
        if not city_data_loaded(conn):
            print("city-match: no city data loaded, skipping (run ./start.sh city-data)")
            return
        if args.if_needed and conn.scalar(text("SELECT EXISTS (SELECT 1 FROM listing_city_data)")):
            return
        matched = rebuild(conn)
        total = conn.scalar(text("SELECT count(*) FROM listings"))
        print(f"city-match: matched {matched} of {total} listings to city data")


if __name__ == "__main__":
    main()
