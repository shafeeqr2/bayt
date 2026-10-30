import { Suspense } from "react";

import { getCityData, getLotAnalysis, type CityData, type Permit } from "@/lib/api";
import { formatArea, formatDate, formatMetres, formatPrice } from "@/lib/format";
import { card, Chip, Disclosure, Fact, Help, Section } from "../../ui";
import { CoverageFacts, LotMapCell, LotSceneSection, ParcelOnly } from "./lot-panel";
import { PathwaysPanel } from "./pathways-panel";
import { PrecedentsSection } from "./precedents-section";

// Zones where Toronto has allowed up to four units as-of-right since May 2023.
const MULTIPLEX_ZONES = new Set(["R", "RD", "RS", "RT", "RM"]);

export async function CitySection({ id }: { id: string }) {
  const city = await getCityData(id);
  if (!city) return <LotOnlySection id={id} />;

  return (
    <Section
      id="lot"
      eyebrow="City of Toronto open data"
      title="Lot & zoning"
      lead={`${city.address_full}${city.former_municipality ? `, ${city.former_municipality}` : ""}.`}
      help={
        <>
          Lot lines, zoning, heritage status and permits come from the City of Toronto&apos;s open data and GIS.
          {city.match_method === "nearest" &&
            ` The listing was matched to the nearest city address, ${Math.round(city.match_distance_m ?? 0)} m from its map pin.`}
        </>
      }
      helpLabel="About the data"
    >
      <div className={`grid gap-6 p-5 md:grid-cols-[15rem_minmax(0,1fr)] ${card}`}>
        {/* The lot analysis needs the city's GIS, so it streams in after the rest. */}
        <Suspense fallback={<ParcelOnly geojson={city.lot_geojson} />}>
          <LotMapCell id={id} city={city} />
        </Suspense>
        <div className="space-y-5">
          <Facts
            items={[
              ["Lot area", formatArea(city.lot_area_m2)],
              ["Frontage (approx.)", formatMetres(city.lot_frontage_m)],
              ["Depth (approx.)", formatMetres(city.lot_depth_m)],
              ["Heritage", city.heritage_status ? `On the register: ${city.heritage_status}` : "Not on the register"],
            ]}
          />
          <Suspense fallback={null}>
            <CoverageFacts id={id} />
          </Suspense>
          <Zoning city={city} />
        </div>
      </div>

      <Suspense fallback={null}>
        <LotSceneSection id={id} city={city} />
      </Suspense>

      {city.parking_rules.length > 0 && <Parking city={city} />}

      <Suspense fallback={null}>
        <PrecedentsSection id={id} />
      </Suspense>

      <Permits permits={city.permits} />

      {/* The pathway analysis resolves the low-rise residential chapter only. */}
      {city.zone_category && MULTIPLEX_ZONES.has(city.zone_category) && <PathwaysPanel id={id} />}
    </Section>
  );
}

/**
 * The lot analysis on its own, for when City of Toronto open data has not been loaded
 * (`./start.sh city-data`). It comes straight from the city's GIS, so the lot map,
 * coverage and 3D view still work; zoning, heritage and permits need the open data.
 */
async function LotOnlySection({ id }: { id: string }) {
  const lot = await getLotAnalysis(id);
  if (!lot) return null;

  return (
    <Section
      id="lot"
      eyebrow="City of Toronto GIS"
      title="Lot"
      lead="Lot lines and coverage from the city's GIS."
      help="Zoning, heritage status and building permits appear once the city's open data has been loaded."
      helpLabel="About the data"
    >
      <div className={`grid gap-6 p-5 md:grid-cols-[15rem_minmax(0,1fr)] ${card}`}>
        <LotMapCell id={id} city={null} />
        <div className="space-y-5">
          <CoverageFacts id={id} divider={false} />
        </div>
      </div>

      <LotSceneSection id={id} city={null} />

      <Suspense fallback={null}>
        <PrecedentsSection id={id} />
      </Suspense>

      <PathwaysPanel id={id} />
    </Section>
  );
}

function Facts({ items }: { items: [string, string | null][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
      {items
        .filter(([, value]) => value)
        .map(([label, value]) => (
          <Fact key={label} label={label} value={value} />
        ))}
    </dl>
  );
}

function Zoning({ city }: { city: CityData }) {
  if (!city.zone_category) {
    return (
      <p className="rounded-lg bg-surface-2 p-4 text-sm leading-relaxed text-muted">
        <span className="font-medium text-foreground">Not in the city-wide zoning by-law (569-2013).</span> A former
        municipal or site-specific by-law applies, as is common for condo buildings.
      </p>
    );
  }

  const multiplex = MULTIPLEX_ZONES.has(city.zone_category);
  return (
    <div className="space-y-4 border-t border-border pt-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <p className="font-medium">
          Zone {city.zone_category}
          {city.zone_label ? ` · ${city.zone_label}` : ""}
        </p>
        <Chip tone="neutral" className="font-mono">
          {city.zone_string}
        </Chip>
        {multiplex && <Chip tone="success">Up to 4 units as-of-right</Chip>}
      </div>
      <Facts
        items={[
          ...city.zone_rules.map((rule): [string, string] => [rule.label, rule.value]),
          ["Height limit", city.height_limit_m ? `${city.height_limit_m} m` : null],
          ["Max storeys", city.height_limit_storeys ? String(city.height_limit_storeys) : null],
          ["Max lot coverage", city.lot_coverage_pct ? `${city.lot_coverage_pct}%` : null],
          ["By-law section", city.zoning_bylaw_section],
        ]}
      />
      {multiplex && (
        <div className="text-sm text-muted">
          <Help label="About the 4-unit rule">
            Since May 2023 Toronto permits up to 4 units (duplex, triplex or fourplex) as-of-right in this zone, as long
            as the building meets the zone&apos;s height, setback, depth and coverage rules.
            {city.zone_exception && ` Site-specific exception #${city.zone_exception} may change those rules.`}
          </Help>
        </div>
      )}
    </div>
  );
}

function Parking({ city }: { city: CityData }) {
  return (
    <Disclosure title="Parking rules" count="By-law 569-2013, Chapter 200">
      <div className="space-y-4 p-5">
        <Facts items={city.parking_rules.map((rule): [string, string] => [rule.label, rule.value])} />
        {city.parking_note && <p className="text-sm leading-relaxed text-muted">{city.parking_note}</p>}
      </div>
    </Disclosure>
  );
}

function Permits({ permits }: { permits: Permit[] }) {
  return (
    <Disclosure title="Building permits" count={`(${permits.length})`}>
      {permits.length === 0 ? (
        <p className="p-5 text-sm text-muted">No building permit on record for this address since 2000.</p>
      ) : (
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="sticky top-0 bg-surface text-left text-muted">
              <tr className="border-b border-border">
                <th className="px-5 py-2.5 font-medium">Applied</th>
                <th className="px-4 py-2.5 font-medium">Work</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="whitespace-nowrap px-5 py-2.5 text-right font-medium">Est. cost</th>
              </tr>
            </thead>
            <tbody>
              {permits.map((permit) => (
                <tr
                  key={`${permit.permit_num}-${permit.revision_num}`}
                  className="border-b border-border align-top last:border-0"
                >
                  <td className="whitespace-nowrap px-5 py-2.5 tabular-nums">{formatDate(permit.application_date)}</td>
                  <td className="px-4 py-2.5">
                    <p>{permit.work ?? permit.permit_type}</p>
                    {permit.description && <p className="line-clamp-2 text-xs text-muted">{permit.description}</p>}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5">{permit.status}</td>
                  <td className="whitespace-nowrap px-5 py-2.5 text-right tabular-nums">
                    {permit.est_construction_cost ? formatPrice(permit.est_construction_cost) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Disclosure>
  );
}
