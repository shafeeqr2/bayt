"use client";

import {
  Map as MapLibreMap,
  NavigationControl,
  setWorkerUrl,
  type ExpressionSpecification,
  type StyleSpecification,
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type { BuildingFeature, GeoArea, GeoLineString } from "@/lib/api";

import "maplibre-gl/dist/maplibre-gl.css";

// Turbopack does not emit MapLibre's worker file; scripts/copy-maplibre-worker.mjs puts it in public/.
setWorkerUrl("/maplibre-gl-worker.mjs");

// Free vector tiles, no key, no request limits (https://openfreemap.org).
const BASEMAP = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};
const DEFAULT_HEIGHT_M = 6; // for the rare outline without a LiDAR height: a modest two-storey house
const PITCH = 58;
const EARTH_CIRCUMFERENCE_M = 40_075_016.686;

export type LotSceneProps = {
  parcel: GeoArea;
  buildings: BuildingFeature[];
  nearbyBuildings: BuildingFeature[];
  nearbyParcels: GeoArea[];
  frontage: GeoLineString | null;
  /** Zoning height limit over this lot, drawn as a translucent ceiling. */
  heightLimitM: number | null;
};

type Point = [number, number];

function outerRings(area: GeoArea): Point[][] {
  const polygons = area.type === "Polygon" ? [area.coordinates] : area.coordinates;
  return polygons.map((polygon) => polygon[0].map(([lon, lat]) => [lon, lat] as Point));
}

function collection(areas: GeoArea[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features: areas.map((geometry) => ({ type: "Feature", geometry, properties: {} })) };
}

function buildingCollection(buildings: BuildingFeature[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: buildings.map((b) => ({
      type: "Feature",
      geometry: b.geometry,
      properties: { height: b.properties.height_m ?? DEFAULT_HEIGHT_M, kind: b.properties.kind },
    })),
  };
}

/** Compass bearing (degrees) from `from` to `to`, so the camera can look at the lot from the street. */
function bearingBetween([lon1, lat1]: Point, [lon2, lat2]: Point): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLon = toRad(lon2 - lon1);
  const y = Math.sin(dLon) * Math.cos(toRad(lat2));
  const x = Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) - Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(dLon);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

function supportsWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function cssColor(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/**
 * The lot in 3D: the house and its neighbours extruded to the city's LiDAR heights
 * over a street basemap, with the zoning height limit floating above the lot.
 */
export function LotScene({ parcel, buildings, nearbyBuildings, nearbyParcels, frontage, heightLimitM }: LotSceneProps) {
  const container = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState(false);
  // Client-only component (loaded with ssr: false), so the DOM is there at first render.
  const [unsupported] = useState(() => typeof document !== "undefined" && !supportsWebGL());

  useEffect(() => {
    if (!container.current || unsupported) return;

    const ring = outerRings(parcel).flat();
    const lons = ring.map(([lon]) => lon);
    const lats = ring.map(([, lat]) => lat);
    const center: Point = [(Math.min(...lons) + Math.max(...lons)) / 2, (Math.min(...lats) + Math.max(...lats)) / 2];

    // Zoom so the lot's longest side takes about a third of the view.
    const metresPerDegree = (EARTH_CIRCUMFERENCE_M / 360) * Math.cos((center[1] * Math.PI) / 180);
    const extentM = Math.max(
      (Math.max(...lons) - Math.min(...lons)) * metresPerDegree,
      (Math.max(...lats) - Math.min(...lats)) * (EARTH_CIRCUMFERENCE_M / 360),
      10,
    );
    const viewHeightPx = container.current.clientHeight || 384;
    const metresPerPixel = extentM / (viewHeightPx * 0.35);
    const zoom = Math.min(19.5, Math.max(17.5, Math.log2((metresPerDegree * 360) / 512 / metresPerPixel)));

    // Look from the street into the lot; fall back to north-up when there is no front lot line.
    let bearing = 0;
    if (frontage) {
      const coords = frontage.coordinates;
      const mid: Point = [
        (coords[0][0] + coords[coords.length - 1][0]) / 2,
        (coords[0][1] + coords[coords.length - 1][1]) / 2,
      ];
      bearing = bearingBetween(mid, center);
    }

    const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const accent = cssColor("--accent", dark ? "#e07a4c" : "#b4532a");
    const neighbour = dark ? "#5a544f" : "#bdb6af";
    const neighbourLine = dark ? "#8a837c" : "#8c857e";
    // The zoning envelope is a rule, not a building, so it gets a cool colour that no footprint uses.
    const envelope = dark ? "#60a5fa" : "#2563eb";

    const map = new MapLibreMap({
      container: container.current,
      style: dark ? BASEMAP.dark : BASEMAP.light,
      center,
      zoom,
      pitch: PITCH,
      bearing,
      cooperativeGestures: true,
      attributionControl: { compact: true },
      maxPitch: 70,
    });
    map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");

    const extrusionHeight: ExpressionSpecification = ["get", "height"];

    map.on("load", () => {
      map.addSource("nearby-parcels", { type: "geojson", data: collection(nearbyParcels) });
      map.addSource("parcel", { type: "geojson", data: collection([parcel]) });
      map.addSource("nearby-buildings", { type: "geojson", data: buildingCollection(nearbyBuildings) });
      map.addSource("buildings", { type: "geojson", data: buildingCollection(buildings) });
      if (frontage) {
        map.addSource("frontage", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [{ type: "Feature", geometry: frontage, properties: {} }] },
        });
      }

      // Put our layers right above the basemap's flat building fill (which would otherwise
      // paint over the roofs) and under its labels so street names stay readable.
      const layers = (map.getStyle() as StyleSpecification).layers;
      const lastBuildingFill = [...layers].reverse().find((l) => l.type === "fill" && l["source-layer"] === "building");
      const firstSymbol = lastBuildingFill
        ? layers[layers.findIndex((l) => l.id === lastBuildingFill.id) + 1]?.id
        : layers.find((l) => l.type === "symbol")?.id;

      map.addLayer(
        { id: "nearby-parcels", type: "line", source: "nearby-parcels", paint: { "line-color": neighbourLine, "line-width": 0.8, "line-opacity": 0.6 } },
        firstSymbol,
      );
      map.addLayer({ id: "parcel-fill", type: "fill", source: "parcel", paint: { "fill-color": accent, "fill-opacity": 0.18 } }, firstSymbol);
      map.addLayer({ id: "parcel-line", type: "line", source: "parcel", paint: { "line-color": accent, "line-width": 2 } }, firstSymbol);
      if (frontage) {
        map.addLayer({ id: "frontage", type: "line", source: "frontage", paint: { "line-color": accent, "line-width": 5 }, layout: { "line-cap": "round" } }, firstSymbol);
      }
      map.addLayer({
        id: "nearby-buildings",
        type: "fill-extrusion",
        source: "nearby-buildings",
        paint: { "fill-extrusion-color": neighbour, "fill-extrusion-height": extrusionHeight, "fill-extrusion-opacity": 0.85 },
      });
      map.addLayer({
        id: "buildings",
        type: "fill-extrusion",
        source: "buildings",
        paint: { "fill-extrusion-color": accent, "fill-extrusion-height": extrusionHeight, "fill-extrusion-opacity": 0.95 },
      });
      if (heightLimitM) {
        // The zoning envelope: a faint volume up to the limit so the eye can judge the
        // height against the house, capped by a thin slab. Nothing may rise above the slab.
        map.addLayer({
          id: "height-envelope",
          type: "fill-extrusion",
          source: "parcel",
          paint: { "fill-extrusion-color": envelope, "fill-extrusion-height": heightLimitM, "fill-extrusion-opacity": 0.12 },
        });
        map.addLayer({
          id: "height-limit",
          type: "fill-extrusion",
          source: "parcel",
          paint: {
            "fill-extrusion-color": envelope,
            "fill-extrusion-base": heightLimitM - 0.3,
            "fill-extrusion-height": heightLimitM,
            "fill-extrusion-opacity": 0.45,
          },
        });
      }
      setReady(true);
    });

    return () => {
      map.remove();
    };
  }, [parcel, buildings, nearbyBuildings, nearbyParcels, frontage, heightLimitM, unsupported]);

  if (unsupported) {
    return (
      <div className="flex h-40 items-center justify-center rounded-xl border border-border bg-surface p-4 text-center text-sm text-muted">
        The 3D view needs WebGL, which this browser has turned off.
      </div>
    );
  }
  return (
    <div
      className={`h-96 w-full overflow-hidden rounded-xl border border-border bg-border transition-opacity ${ready ? "opacity-100" : "opacity-60"}`}
      role="img"
      aria-label="3D view of the lot, its buildings and neighbours"
    >
      {/* MapLibre adds its own classes to this element, so React must never rewrite its className. */}
      <div ref={container} className="h-full w-full" />
    </div>
  );
}
