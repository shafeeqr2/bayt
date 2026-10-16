import { getLotAnalysis, type CityData, type LotAnalysis } from "@/lib/api";
import { formatArea } from "@/lib/format";
import { LotMap } from "./lot-map";
import { LotSceneLoader } from "./lot-scene-loader";

/**
 * The lot drawing. Shows the house and garage footprints, front lot line and rear
 * yard once the lot analysis is in; until then (or outside Toronto) the parcel
 * boundary alone.
 */
export async function LotMapCell({ id, city }: { id: string; city: CityData }) {
  const lot = await getLotAnalysis(id);
  if (!lot) return <ParcelOnly geojson={city.lot_geojson} />;

  const { geometry } = lot;
  return (
    <div className="space-y-2">
      <LotMap
        parcel={geometry.parcel}
        buildings={geometry.buildings.map((b) => b.geometry)}
        frontage={geometry.frontage}
        rearYard={geometry.rear_yard}
      />
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
        <Legend swatch="bg-foreground/75">Buildings</Legend>
        <Legend swatch="bg-accent">Front lot line</Legend>
        {geometry.rear_yard && <Legend swatch="border border-dashed border-accent/60 bg-accent/15">Rear yard</Legend>}
      </ul>
    </div>
  );
}

/** The lot in 3D with the neighbours and the zoning height limit. Nothing outside Toronto. */
export async function LotSceneSection({ id, city }: { id: string; city: CityData }) {
  const lot = await getLotAnalysis(id);
  if (!lot) return null;

  const { geometry } = lot;
  const limit = city.height_limit_m;
  const storeys = city.height_limit_storeys;
  return (
    <div className="space-y-2">
      <LotSceneLoader
        parcel={geometry.parcel}
        buildings={geometry.buildings}
        nearbyBuildings={geometry.nearby_buildings}
        nearbyParcels={geometry.nearby_parcels}
        frontage={geometry.frontage}
        heightLimitM={limit}
      />
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 text-xs text-muted">
        <ul className="flex flex-wrap gap-x-3 gap-y-1">
          <Legend swatch="bg-accent">This property</Legend>
          <Legend swatch="bg-[#bdb6af] dark:bg-[#5a544f]">Neighbours</Legend>
          {limit ? (
            <Legend swatch="bg-[#2563eb]/50 dark:bg-[#60a5fa]/50">
              Height limit {limit} m{storeys ? ` (${storeys} storeys)` : ""}
            </Legend>
          ) : null}
        </ul>
        <p>
          Heights from the city&apos;s LiDAR survey. The height limit is drawn over the whole lot; setbacks are not.
          Drag to rotate, Ctrl + scroll to zoom.
        </p>
      </div>
    </div>
  );
}

export function ParcelOnly({ geojson }: { geojson: CityData["lot_geojson"] }) {
  if (!geojson) return null;
  return (
    <div className="space-y-2">
      <LotMap parcel={geojson} />
      <p className="text-xs text-muted">Lot boundary to scale</p>
    </div>
  );
}

function Legend({ swatch, children }: { swatch: string; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-1.5">
      <span className={`inline-block size-2.5 rounded-sm ${swatch}`} aria-hidden />
      {children}
    </li>
  );
}

/** How much of the lot the buildings take up, against the zoning cap. */
export async function CoverageFacts({ id }: { id: string }) {
  const lot = await getLotAnalysis(id);
  if (!lot) return null;

  const { coverage, caveats } = lot;
  const allowed = coverage.max_coverage_pct;
  const overCap = allowed != null && coverage.coverage_pct > allowed;

  return (
    <div className="space-y-3 border-t border-border pt-5">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm text-muted">Lot coverage</p>
        <p className="text-sm tabular-nums">
          <span className="text-2xl font-semibold">{coverage.coverage_pct}%</span>
          <span className="text-muted">{allowed != null ? ` of ${allowed}% allowed` : " built on"}</span>
        </p>
      </div>
      <CoverageBar covered={coverage.coverage_pct} allowed={allowed} />
      <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
        <Fact label="Building footprint" value={formatArea(coverage.building_footprint_m2)} />
        <Fact label="Open land" value={`${coverage.open_pct}% of the lot`} />
        {coverage.ancillary_m2 > 0 && <Fact label="Garage and sheds" value={formatArea(coverage.ancillary_m2)} />}
        {allowed != null && (
          <Fact
            label="Room to build"
            value={
              overCap
                ? "Already over the coverage cap"
                : `${formatArea(coverage.remaining_buildable_footprint_m2)} more footprint`
            }
          />
        )}
      </dl>
      <p className="text-xs text-muted">
        Footprints from the city&apos;s building outlines, which miss driveways, patios and pools. Open land is not
        necessarily green.
      </p>
      <Caveats caveats={caveats} />
    </div>
  );
}

function CoverageBar({ covered, allowed }: { covered: number; allowed: number | null }) {
  const clamp = (pct: number) => Math.max(0, Math.min(100, pct));
  return (
    <div className="relative h-2 rounded-full bg-border" role="meter" aria-valuenow={covered} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-foreground/75" style={{ width: `${clamp(covered)}%` }} />
      {allowed != null && (
        <div
          className="absolute -top-1 h-4 w-0.5 bg-accent"
          style={{ left: `${clamp(allowed)}%` }}
          title={`Zoning cap: ${allowed}%`}
        />
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
  );
}

// Every analysis ends with the same two disclaimers; the ones before are specific to this lot.
const GENERIC_CAVEATS = 2;

function Caveats({ caveats }: { caveats: LotAnalysis["caveats"] }) {
  const specific = caveats.slice(0, Math.max(0, caveats.length - GENERIC_CAVEATS));
  if (specific.length === 0) return null;
  return (
    <ul className="space-y-1 rounded-lg bg-background p-3 text-xs leading-relaxed text-muted">
      {specific.map((caveat) => (
        <li key={caveat}>{caveat}</li>
      ))}
    </ul>
  );
}
