"""Vector tiles of the city's building outlines, for the 3D search map.

Postgres builds Mapbox Vector Tiles itself (`ST_AsMVT`), so the map can ask for
`/api/tiles/buildings/{z}/{x}/{y}` and extrude every footprint in view to its
LiDAR-measured height. Tiles only exist from `MIN_ZOOM` up: a zoom-13 tile of
downtown is already 700 KB of footprints nobody can make out at that scale.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

MIN_ZOOM = 14
MAX_ZOOM = 17  # tiles beyond this are the same data; the map overzooms them
LAYER = "buildings"

TILE_SQL = text(
    r"""
    WITH bounds AS (SELECT ST_TileEnvelope(:z, :x, :y) AS geom),
    mvt AS (
        SELECT
            ST_AsMVTGeom(ST_Transform(b.geom, 3857), bounds.geom, 4096, 64, true) AS geom,
            b.ogc_fid AS id,
            -- The city ships the height as text, with 'None' for the few it could not derive.
            CASE WHEN b.derived_height ~ '^[0-9]+(\.[0-9]+)?$' THEN b.derived_height::float END AS height,
            b.subtype_desc AS kind
        FROM city.buildings b, bounds
        WHERE b.geom && ST_Transform(bounds.geom, 4326)
    )
    SELECT ST_AsMVT(mvt, :layer, 4096, 'geom', 'id') FROM mvt WHERE geom IS NOT NULL
    """
)

BOUNDARY_SQL = text(
    """
    SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(ST_Union(geom), :tolerance), 6)
    FROM city.boundary
    """
)


def buildings_loaded(session: Session) -> bool:
    return bool(session.scalar(text("SELECT to_regclass('city.buildings') IS NOT NULL")))


def building_tile(session: Session, z: int, x: int, y: int) -> bytes:
    """The MVT for one tile; empty bytes when nothing is in it."""
    return bytes(session.scalar(TILE_SQL, {"z": z, "x": x, "y": y, "layer": LAYER}) or b"")


def city_boundary(session: Session) -> str | None:
    """Toronto's limits as a GeoJSON geometry string, simplified to about 50 m."""
    if not session.scalar(text("SELECT to_regclass('city.boundary') IS NOT NULL")):
        return None
    return session.scalar(BOUNDARY_SQL, {"tolerance": 0.0005})
