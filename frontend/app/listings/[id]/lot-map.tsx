import type { GeoArea, GeoLineString } from "@/lib/api";

const METRES_PER_DEGREE_LAT = 110_540;
const METRES_PER_DEGREE_LON_AT_EQUATOR = 111_320;
const SIZE = 240;
const PADDING = 16;
const SCALE_BAR_CHOICES_M = [2, 5, 10, 20, 50];

type Point = [number, number];

/** Every ring (outer boundary and holes) of a Polygon or MultiPolygon, as lon/lat pairs. */
function rings(area: GeoArea): Point[][] {
  const polygons = area.type === "Polygon" ? [area.coordinates] : area.coordinates;
  return polygons.flatMap((polygon) => polygon.map((ring) => ring.map(([lon, lat]) => [lon, lat] as Point)));
}

/**
 * Draws a lot to scale, north up: the parcel, the buildings on it, the front lot line
 * and the rear yard. Only the parcel is required, so it also works from the parcel
 * boundary alone.
 */
export function LotMap({
  parcel,
  buildings = [],
  frontage = null,
  rearYard = null,
}: {
  parcel: GeoArea;
  buildings?: GeoArea[];
  frontage?: GeoLineString | null;
  rearYard?: GeoArea | null;
}) {
  const parcelRings = rings(parcel);
  const points = parcelRings.flat();
  const lat0 = points.reduce((sum, [, lat]) => sum + lat, 0) / points.length;
  const lon0 = points.reduce((sum, [lon]) => sum + lon, 0) / points.length;
  const lonScale = METRES_PER_DEGREE_LON_AT_EQUATOR * Math.cos((lat0 * Math.PI) / 180);

  // Local metres, y down (north up on screen).
  const toMetres = ([lon, lat]: Point): Point => [(lon - lon0) * lonScale, -(lat - lat0) * METRES_PER_DEGREE_LAT];
  const parcelMetres = parcelRings.map((ring) => ring.map(toMetres));
  const xs = parcelMetres.flat().map(([x]) => x);
  const ys = parcelMetres.flat().map(([, y]) => y);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const scale = (SIZE - 2 * PADDING) / Math.max(maxX - minX, maxY - minY, 1);
  const offsetX = (SIZE - (maxX - minX) * scale) / 2;
  const offsetY = (SIZE - (maxY - minY) * scale) / 2;

  const toScreen = (p: Point): Point => {
    const [x, y] = toMetres(p);
    return [(x - minX) * scale + offsetX, (y - minY) * scale + offsetY];
  };
  const path = (ring: Point[], close = true) =>
    ring.map((p, i) => `${i ? "L" : "M"}${toScreen(p).map((v) => v.toFixed(1)).join(",")}`).join(" ") + (close ? " Z" : "");
  const areaPath = (area: GeoArea) => rings(area).map((ring) => path(ring)).join(" ");

  const barMetres =
    [...SCALE_BAR_CHOICES_M].reverse().find((m) => m * scale <= (SIZE - 2 * PADDING) * 0.4) ?? SCALE_BAR_CHOICES_M[0];
  const barPx = barMetres * scale;

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="aspect-square w-full max-w-60 rounded-xl border border-border bg-background"
      role="img"
      aria-label={buildings.length ? "Lot boundary with building footprints" : "Lot boundary"}
    >
      <path
        d={areaPath(parcel)}
        fillRule="evenodd"
        className={frontage ? "fill-accent/10 stroke-accent/50" : "fill-accent/10 stroke-accent"}
        strokeWidth={frontage ? 1.5 : 2}
        strokeLinejoin="round"
      />
      {rearYard && (
        <path
          d={areaPath(rearYard)}
          fillRule="evenodd"
          className="fill-accent/15 stroke-accent/60"
          strokeWidth={1}
          strokeDasharray="3 3"
          strokeLinejoin="round"
        />
      )}
      {buildings.map((building, i) => (
        <path
          key={i}
          d={areaPath(building)}
          fillRule="evenodd"
          className="fill-foreground/75 stroke-foreground"
          strokeWidth={1}
          strokeLinejoin="round"
        />
      ))}
      {frontage && (
        <path d={path(frontage.coordinates as Point[], false)} className="stroke-accent" strokeWidth={5} strokeLinecap="round" />
      )}
      <text x={SIZE - 12} y={20} textAnchor="end" className="fill-muted text-[11px]">
        N ↑
      </text>
      <g className="stroke-muted" strokeWidth={1.5}>
        <line x1={12} y1={SIZE - 12} x2={12 + barPx} y2={SIZE - 12} />
        <line x1={12} y1={SIZE - 16} x2={12} y2={SIZE - 8} />
        <line x1={12 + barPx} y1={SIZE - 16} x2={12 + barPx} y2={SIZE - 8} />
      </g>
      <text x={12 + barPx + 6} y={SIZE - 9} className="fill-muted text-[11px]">
        {barMetres} m
      </text>
    </svg>
  );
}
