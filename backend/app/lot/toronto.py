"""City of Toronto GIS client.

Toronto publishes the datasets we need as queryable ArcGIS FeatureServer layers
(https://gis.toronto.ca/arcgis/rest/services). They are the live versions of the
Open Data Toronto "Property Boundaries", "Topographic Mapping - Building Outlines",
"Zoning By-law" and "Toronto Centreline" datasets, so we can answer per-lot
questions with a handful of small spatial queries instead of hosting ~1 GB of
GeoJSON in PostGIS.

Only COMMON parcels (ordinary fee-simple lots) are analyzed. CONDO parcels cover
whole condo corporations and RESERVE parcels are 0.3 m access-control strips.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

import httpx
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

BASE = "https://gis.toronto.ca/arcgis/rest/services"

LAYERS = {
    "parcels": f"{BASE}/cot_geospatial27/FeatureServer/36",
    "buildings": f"{BASE}/cot_geospatial3/FeatureServer/2",
    "zoning": f"{BASE}/cot_geospatial11/FeatureServer/3",
    "lot_coverage": f"{BASE}/cot_geospatial11/FeatureServer/10",
    "sixplex": f"{BASE}/cot_geospatial11/FeatureServer/80",
    "centreline": f"{BASE}/cot_geospatial/FeatureServer/2",
}

# Centreline FEATURE_CODE_DESC values that are streets a lot can front onto.
STREET_CODES = {
    "Local",
    "Collector",
    "Minor Arterial",
    "Major Arterial",
    "Access Road",
    "Pending",
    "Other",
    "Busway",
}
LANEWAY_CODE = "Laneway"


class GISError(RuntimeError):
    """The city's GIS service failed or returned an error payload."""


@dataclass
class Feature:
    geometry: BaseGeometry  # WGS84 (EPSG:4326)
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class LotInputs:
    """Everything `analysis.analyze` needs for one lot, all in WGS84."""

    parcel: Feature
    neighbours: list[Feature]  # COMMON parcels within ~100 m, excluding the parcel itself
    buildings: list[Feature]  # footprints intersecting the parcel
    zoning: Feature | None
    lot_coverage: Feature | None
    centrelines: list[Feature]  # street + laneway centrelines within ~60 m
    sixplex: Feature | None


class TorontoGIS:
    def __init__(self, client: httpx.Client | None = None, timeout: float = 20.0):
        self._client = client or httpx.Client(timeout=timeout, headers={"User-Agent": "bayt/0.1"})

    # -- low level -----------------------------------------------------------

    def _query(
        self,
        layer: str,
        *,
        geometry: str,
        geometry_type: str,
        out_fields: str = "*",
        where: str = "1=1",
        distance_m: float | None = None,
    ) -> list[Feature]:
        params: dict[str, Any] = {
            "geometry": geometry,
            "geometryType": geometry_type,
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "where": where,
            "outFields": out_fields,
            "outSR": 4326,
            "returnGeometry": "true",
            "f": "geojson",
        }
        # Passing distance=0 makes the server return nothing, so only send it when used.
        if distance_m:
            params["distance"] = distance_m
            params["units"] = "esriSRUnit_Meter"
        try:
            resp = self._client.get(f"{LAYERS[layer]}/query", params=params)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise GISError(f"{layer}: {e}") from e
        if "error" in data:
            raise GISError(f"{layer}: {data['error']}")
        return [
            Feature(shape(f["geometry"]), f.get("properties") or {})
            for f in data.get("features", [])
            if f.get("geometry")
        ]

    @staticmethod
    def _point(lat: float, lon: float) -> tuple[str, str]:
        return f"{lon},{lat}", "esriGeometryPoint"

    @staticmethod
    def _envelope(geom: BaseGeometry, pad_m: float) -> tuple[str, str]:
        """Bounding box padded by `pad_m` metres, as an Esri envelope.

        Server-side buffering of a polygon ("distance=") fails on some parcels,
        so neighbourhood queries use a padded envelope instead.
        """
        minx, miny, maxx, maxy = geom.bounds
        lat = (miny + maxy) / 2
        dlat = pad_m / 111_320
        dlon = pad_m / (111_320 * max(0.1, math.cos(math.radians(lat))))
        return f"{minx - dlon},{miny - dlat},{maxx + dlon},{maxy + dlat}", "esriGeometryEnvelope"

    @staticmethod
    def _polygon(geom: BaseGeometry) -> tuple[str, str]:
        # ArcGIS wants Esri JSON for polygons: rings as [x, y] lists.
        if geom.geom_type == "MultiPolygon":
            rings = [list(p.exterior.coords) for p in geom.geoms]
        else:
            rings = [list(geom.exterior.coords)]
        esri = {"rings": [[list(c[:2]) for c in r] for r in rings], "spatialReference": {"wkid": 4326}}
        return json.dumps(esri), "esriGeometryPolygon"

    # -- layers --------------------------------------------------------------

    def parcel_at(self, lat: float, lon: float) -> Feature | None:
        """The COMMON parcel containing the point, or the nearest one within 15 m.

        Listing coordinates are geocoded and sometimes land on the road in front
        of the house, hence the fallback.
        """
        geometry, gtype = self._point(lat, lon)
        where = "FEATURE_TYPE='COMMON'"
        hits = self._query("parcels", geometry=geometry, geometry_type=gtype, where=where)
        if not hits:
            hits = self._query(
                "parcels", geometry=geometry, geometry_type=gtype, where=where, distance_m=15
            )
            if not hits:
                return None
            pt = Point(lon, lat)
            hits.sort(key=lambda f: f.geometry.distance(pt))
            return hits[0]
        # Overlapping parcels exist (e.g. a lot inside a plan-of-subdivision block); take the smallest.
        hits.sort(key=lambda f: f.geometry.area)
        return hits[0]

    def parcels_near(self, parcel: BaseGeometry, distance_m: float = 100) -> list[Feature]:
        geometry, gtype = self._envelope(parcel, distance_m)
        return self._query(
            "parcels",
            geometry=geometry,
            geometry_type=gtype,
            where="FEATURE_TYPE='COMMON'",
            out_fields="PARCELID,FEATURE_TYPE,ADDRESS_NUMBER,LINEAR_NAME_FULL,STATEDAREA",
        )

    def buildings_intersecting(self, parcel: BaseGeometry) -> list[Feature]:
        geometry, gtype = self._polygon(parcel)
        return self._query(
            "buildings",
            geometry=geometry,
            geometry_type=gtype,
            out_fields="BUILDINGID,SUBTYPE_CODE,SUBTYPE_DESC,DERIVED_HEIGHT,ELEVATION,LAST_GEOMETRY_MAINT",
        )

    def zoning_at(self, lat: float, lon: float) -> Feature | None:
        geometry, gtype = self._point(lat, lon)
        hits = self._query("zoning", geometry=geometry, geometry_type=gtype, where="ZN_STATUS<>5")
        return hits[0] if hits else None

    def lot_coverage_at(self, lat: float, lon: float) -> Feature | None:
        geometry, gtype = self._point(lat, lon)
        hits = self._query("lot_coverage", geometry=geometry, geometry_type=gtype)
        return hits[0] if hits else None

    def sixplex_at(self, lat: float, lon: float) -> Feature | None:
        geometry, gtype = self._point(lat, lon)
        hits = self._query("sixplex", geometry=geometry, geometry_type=gtype)
        return hits[0] if hits else None

    def centrelines_near(self, parcel: BaseGeometry, distance_m: float = 60) -> list[Feature]:
        geometry, gtype = self._envelope(parcel, distance_m)
        feats = self._query(
            "centreline",
            geometry=geometry,
            geometry_type=gtype,
            out_fields="CENTRELINE_ID,LINEAR_NAME_FULL,FEATURE_CODE_DESC",
        )
        keep = STREET_CODES | {LANEWAY_CODE}
        return [f for f in feats if f.properties.get("FEATURE_CODE_DESC") in keep]

    # -- bundle --------------------------------------------------------------

    def lot_inputs(self, lat: float, lon: float) -> LotInputs | None:
        parcel = self.parcel_at(lat, lon)
        if parcel is None:
            return None
        pid = parcel.properties.get("PARCELID")
        c = parcel.geometry.representative_point()
        return LotInputs(
            parcel=parcel,
            neighbours=[f for f in self.parcels_near(parcel.geometry) if f.properties.get("PARCELID") != pid],
            buildings=self.buildings_intersecting(parcel.geometry),
            zoning=self.zoning_at(c.y, c.x),
            lot_coverage=self.lot_coverage_at(c.y, c.x),
            centrelines=self.centrelines_near(parcel.geometry),
            sixplex=self.sixplex_at(c.y, c.x),
        )
