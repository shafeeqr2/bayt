"use client";

import {
  LngLatBounds,
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  setWorkerUrl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type MapGeoJSONFeature,
  type StyleSpecification,
} from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type { MapPin } from "@/lib/api";
import { bedsLabel, formatPrice } from "@/lib/format";

import "maplibre-gl/dist/maplibre-gl.css";

// Turbopack does not emit MapLibre's worker file; scripts/copy-maplibre-worker.mjs puts it in public/.
setWorkerUrl("/maplibre-gl-worker.mjs");

// Free vector tiles, no key, no request limits (https://openfreemap.org).
const BASEMAP = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};
const PITCH = 45;
const BUILDINGS_MIN_ZOOM = 14;
const CITY_TILES_MAX_ZOOM = 17;
const PRICE_LABEL_MIN_ZOOM = 13;
const CLUSTER_RADIUS_PX = 48;

/** "$1.2M" or "$849K": short enough to sit on a pin. */
function shortPrice(price: number): string {
  if (price >= 1_000_000) return `$${(price / 1_000_000).toFixed(price >= 10_000_000 ? 0 : 1).replace(/\.0$/, "")}M`;
  return `$${Math.round(price / 1000)}K`;
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);
}

function cardHtml(pin: MapPin): string {
  const facts = [bedsLabel(pin.bedrooms_text), pin.bathrooms != null ? `${pin.bathrooms} ba` : null].filter(Boolean).join(" · ");
  const where = [pin.address, pin.community].filter(Boolean).map((t) => escapeHtml(t as string));
  return `
    <a href="/listings/${encodeURIComponent(pin.id)}" class="pin-card">
      ${pin.cover_photo ? `<img src="${escapeHtml(pin.cover_photo)}" alt="" loading="lazy" />` : ""}
      <div class="pin-card-body">
        <p class="pin-card-price">${escapeHtml(formatPrice(pin.price))}</p>
        <p class="pin-card-facts">${escapeHtml(facts)}${pin.building_type ? ` · ${escapeHtml(pin.building_type)}` : ""}</p>
        <p class="pin-card-where">${where.join(", ")}</p>
      </div>
    </a>`;
}

function toGeoJSON(pins: MapPin[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: pins.map((pin) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [pin.longitude, pin.latitude] },
      properties: { ...pin, label: shortPrice(pin.price) },
    })),
  };
}

/**
 * Bounds around the bulk of the pins. One stray match far from the rest (a street
 * elsewhere with the same name) should not zoom the whole map out to a cluster.
 */
function framingBounds(pins: MapPin[]): LngLatBounds {
  const trim = pins.length >= 10 ? Math.floor(pins.length * 0.05) : 0;
  const middle = (values: number[]) => values.sort((a, b) => a - b).slice(trim, values.length - trim);
  const lons = middle(pins.map((p) => p.longitude));
  const lats = middle(pins.map((p) => p.latitude));
  return new LngLatBounds([lons[0], lats[0]], [lons[lons.length - 1], lats[lats.length - 1]]);
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
 * Every matching home as a price pin on a tilted map with 3D buildings.
 * Pins cluster when zoomed out; clicking a pin opens a card linking to the listing.
 */
export function MapSearch({ query, total }: { query: string; total: number }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [pins, setPins] = useState<MapPin[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [unsupported] = useState(() => typeof document !== "undefined" && !supportsWebGL());

  // Pins come from the Next route handler so the page itself stays small.
  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/pins?${query}`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: MapPin[]) => setPins(data))
      .catch((err) => {
        if (err.name !== "AbortError") setFailed(true);
      });
    return () => controller.abort();
  }, [query]);

  // One map for the lifetime of the component; the pins source is swapped when filters change.
  useEffect(() => {
    if (!container.current || unsupported) return;

    const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const accent = cssColor("--accent", dark ? "#e07a4c" : "#b4532a");
    const accentText = cssColor("--accent-foreground", dark ? "#121110" : "#ffffff");
    // On the dark basemap the buildings must be clearly lighter than the ground, or
    // the whole city reads as one black mass.
    const building = dark ? "#57514b" : "#d9d4ce";
    // City buildings shade with height so towers and houses read differently.
    const cityBuilding: ExpressionSpecification = [
      "interpolate",
      ["linear"],
      ["coalesce", ["get", "height"], 4],
      0,
      dark ? "#514b46" : "#e0dbd5",
      12,
      dark ? "#6b645d" : "#c9c2ba",
      60,
      dark ? "#948b82" : "#a39b92",
    ];

    const map = new MapLibreMap({
      container: container.current,
      style: dark ? BASEMAP.dark : BASEMAP.light,
      center: [-79.39, 43.7],
      zoom: 10.5,
      pitch: PITCH,
      cooperativeGestures: true,
      attributionControl: { compact: true },
      maxPitch: 65,
    });
    map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
    mapRef.current = map;

    map.on("load", () => {
      const style = map.getStyle() as StyleSpecification;
      // Extrusions go right above the basemap's flat building fill (which would otherwise
      // paint over their roofs) and below its labels.
      const lastBuildingFill = style.layers.map((l) => l).reverse().find((l) => l.type === "fill" && l["source-layer"] === "building");
      const firstSymbol = lastBuildingFill
        ? style.layers[style.layers.findIndex((l) => l.id === lastBuildingFill.id) + 1]?.id
        : style.layers.find((l) => l.type === "symbol")?.id;

      // Inside Toronto: the city's own footprints with LiDAR-measured heights, served
      // as tiles by the backend. Outside: OpenStreetMap buildings, extruded to their
      // mapped height where there is one. The city boundary decides which is which.
      const osmFilter: ExpressionSpecification = ["!", ["has", "hide_3d"]];
      map.addLayer(
        {
          id: "buildings-3d",
          type: "fill-extrusion",
          source: "openmaptiles",
          "source-layer": "building",
          minzoom: BUILDINGS_MIN_ZOOM,
          filter: osmFilter,
          paint: {
            "fill-extrusion-color": building,
            "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
            "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
            "fill-extrusion-opacity": 0.75,
          },
        },
        firstSymbol,
      );
      map.addSource("city-buildings", {
        type: "vector",
        tiles: [`${window.location.origin}/api/tiles/buildings/{z}/{x}/{y}`],
        minzoom: BUILDINGS_MIN_ZOOM,
        maxzoom: CITY_TILES_MAX_ZOOM,
      });
      map.addLayer(
        {
          id: "city-buildings-3d",
          type: "fill-extrusion",
          source: "city-buildings",
          "source-layer": "buildings",
          minzoom: BUILDINGS_MIN_ZOOM,
          paint: {
            "fill-extrusion-color": cityBuilding,
            "fill-extrusion-height": ["coalesce", ["get", "height"], 4],
            "fill-extrusion-opacity": 0.85,
          },
        },
        firstSymbol,
      );
      fetch("/api/city/boundary")
        .then((res) => (res.ok ? res.json() : null))
        .then((boundary: GeoJSON.Polygon | GeoJSON.MultiPolygon | null) => {
          if (boundary && map.getLayer("buildings-3d")) {
            map.setFilter("buildings-3d", ["all", osmFilter, ["!", ["within", boundary]]]);
          }
        })
        .catch(() => undefined); // no boundary loaded: OpenStreetMap buildings everywhere

      map.addSource("pins", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterRadius: CLUSTER_RADIUS_PX,
        clusterMaxZoom: 15,
      });
      const clusterSize: ExpressionSpecification = ["step", ["get", "point_count"], 16, 10, 20, 50, 26, 200, 32];
      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "pins",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": accent,
          "circle-radius": clusterSize,
          "circle-stroke-width": 2,
          "circle-stroke-color": accentText,
          "circle-opacity": 0.9,
        },
      });
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "pins",
        filter: ["has", "point_count"],
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12, "text-font": ["Noto Sans Bold"] },
        paint: { "text-color": accentText },
      });
      map.addLayer({
        id: "pin",
        type: "circle",
        source: "pins",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": accent,
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 4, PRICE_LABEL_MIN_ZOOM, 6, 16, 8],
          "circle-stroke-width": 1.5,
          "circle-stroke-color": accentText,
        },
      });
      map.addLayer({
        id: "pin-label",
        type: "symbol",
        source: "pins",
        filter: ["!", ["has", "point_count"]],
        minzoom: PRICE_LABEL_MIN_ZOOM,
        layout: {
          "text-field": ["get", "label"],
          "text-size": 12,
          "text-font": ["Noto Sans Bold"],
          "text-offset": [0, 1.1],
          "text-anchor": "top",
          "text-allow-overlap": false,
        },
        paint: { "text-color": accent, "text-halo-color": dark ? "#121110" : "#ffffff", "text-halo-width": 1.5 },
      });

      // Clusters zoom in; pins open a card.
      map.on("click", "clusters", async (e) => {
        const feature = e.features?.[0] as MapGeoJSONFeature | undefined;
        if (!feature) return;
        const source = map.getSource("pins") as GeoJSONSource;
        const zoom = await source.getClusterExpansionZoom(feature.properties.cluster_id as number);
        map.easeTo({ center: (feature.geometry as GeoJSON.Point).coordinates as [number, number], zoom });
      });
      const popup = new Popup({ closeButton: false, offset: 12, maxWidth: "260px" });
      map.on("click", "pin", (e) => {
        const feature = e.features?.[0];
        if (!feature) return;
        const pin = feature.properties as unknown as MapPin;
        popup.setLngLat((feature.geometry as GeoJSON.Point).coordinates as [number, number]).setHTML(cardHtml(pin)).addTo(map);
      });
      for (const layer of ["clusters", "pin"]) {
        map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
      }
    });

    return () => {
      mapRef.current = null;
      map.remove();
    };
  }, [unsupported]);

  // Feed the pins in whenever they arrive, and frame them.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !pins) return;
    const apply = () => {
      (map.getSource("pins") as GeoJSONSource | undefined)?.setData(toGeoJSON(pins));
      if (pins.length === 0) return;
      const camera = map.cameraForBounds(framingBounds(pins), { padding: 48, maxZoom: 16 });
      if (camera) map.jumpTo({ ...camera, pitch: PITCH });
    };
    if (map.isStyleLoaded() && map.getSource("pins")) apply();
    else map.once("load", apply);
  }, [pins]);

  if (unsupported) {
    return (
      <div className="flex h-40 items-center justify-center rounded-2xl border border-border bg-surface p-4 text-center text-sm text-muted shadow-card">
        The map needs WebGL, which this browser has turned off. Switch to the list view.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div
        className="relative h-[70vh] min-h-[28rem] w-full overflow-hidden rounded-2xl border border-border bg-border shadow-card"
        role="region"
        aria-label={`Map of ${total.toLocaleString("en-CA")} ${total === 1 ? "home" : "homes"}`}
      >
        {/* MapLibre adds its own classes to this element, so React must never rewrite its className. */}
        <div ref={container} className="h-full w-full" />
        {!pins && !failed && (
          <p className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 rounded-full border border-border bg-surface px-3 py-1 text-xs text-foreground shadow-lg">
            Loading homes…
          </p>
        )}
        {failed && (
          <p className="absolute left-1/2 top-3 -translate-x-1/2 rounded-full border border-accent bg-surface px-3 py-1.5 text-sm text-foreground shadow-lg">
            Could not load the homes for this map. Reload the page, or switch to the list view.
          </p>
        )}
      </div>
      <p className="text-xs text-muted">Click a cluster to zoom in and a pin to open the home. Ctrl + scroll zooms.</p>
    </div>
  );
}
