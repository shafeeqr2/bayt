import type { CityData } from "@/lib/api";

const METRES_PER_DEGREE_LAT = 110_540;
const METRES_PER_DEGREE_LON_AT_EQUATOR = 111_320;
const SIZE = 240;
const PADDING = 16;

/** Draws the lot boundary to scale, north up. */
export function LotShape({ geojson }: { geojson: NonNullable<CityData["lot_geojson"]> }) {
  const rings = geojson.coordinates.map((polygon) => polygon[0]);
  const points = rings.flat();
  const lat0 = points.reduce((sum, [, lat]) => sum + lat, 0) / points.length;
  const lon0 = points.reduce((sum, [lon]) => sum + lon, 0) / points.length;
  const lonScale = METRES_PER_DEGREE_LON_AT_EQUATOR * Math.cos((lat0 * Math.PI) / 180);

  const projected = rings.map((ring) =>
    ring.map(([lon, lat]) => [(lon - lon0) * lonScale, -(lat - lat0) * METRES_PER_DEGREE_LAT]),
  );
  const xs = projected.flat().map(([x]) => x);
  const ys = projected.flat().map(([, y]) => y);
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const scale = (SIZE - 2 * PADDING) / Math.max(maxX - minX, maxY - minY, 1);
  const offsetX = (SIZE - (maxX - minX) * scale) / 2;
  const offsetY = (SIZE - (maxY - minY) * scale) / 2;

  const paths = projected.map(
    (ring) =>
      ring
        .map(([x, y], i) => `${i ? "L" : "M"}${(x - minX) * scale + offsetX},${(y - minY) * scale + offsetY}`)
        .join(" ") + " Z",
  );

  return (
    <svg
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      className="aspect-square w-full max-w-60 rounded-xl border border-border bg-background"
      role="img"
      aria-label="Lot boundary"
    >
      {paths.map((d, i) => (
        <path key={i} d={d} className="fill-accent/15 stroke-accent" strokeWidth={2} strokeLinejoin="round" />
      ))}
      <text x={SIZE - 12} y={20} textAnchor="end" className="fill-muted text-[11px]">
        N ↑
      </text>
    </svg>
  );
}
