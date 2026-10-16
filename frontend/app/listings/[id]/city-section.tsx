import { Suspense } from "react";

import { getCityData, type CityData, type Permit } from "@/lib/api";
import { formatArea, formatDate, formatMetres, formatPrice } from "@/lib/format";
import { CoverageFacts, LotMapCell, ParcelOnly } from "./lot-panel";

// Zones where Toronto has allowed up to four units as-of-right since May 2023.
const MULTIPLEX_ZONES = new Set(["R", "RD", "RS", "RT", "RM"]);

export async function CitySection({ id }: { id: string }) {
  const city = await getCityData(id);
  if (!city) return null;

  return (
    <section className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Lot &amp; zoning</h2>
        <p className="text-sm text-muted">
          From City of Toronto open data for {city.address_full}
          {city.former_municipality ? `, ${city.former_municipality}` : ""}.
          {city.match_method === "nearest" &&
            ` Matched to the nearest city address, ${Math.round(city.match_distance_m ?? 0)} m from the listing's map pin.`}
        </p>
      </div>

      <div className="grid gap-6 rounded-xl border border-border bg-surface p-5 md:grid-cols-[15rem_minmax(0,1fr)]">
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
              ["Heritage", city.heritage_status ? `Heritage register: ${city.heritage_status}` : "Not on the heritage register"],
            ]}
          />
          <Suspense fallback={null}>
            <CoverageFacts id={id} />
          </Suspense>
          <Zoning city={city} />
        </div>
      </div>

      <Permits permits={city.permits} />
    </section>
  );
}

function Facts({ items }: { items: [string, string | null][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
      {items
        .filter(([, value]) => value)
        .map(([label, value]) => (
          <div key={label}>
            <dt className="text-muted">{label}</dt>
            <dd className="font-medium tabular-nums">{value}</dd>
          </div>
        ))}
    </dl>
  );
}

function Zoning({ city }: { city: CityData }) {
  if (!city.zone_category) {
    return (
      <p className="rounded-lg bg-background p-4 text-sm leading-relaxed">
        <span className="font-medium">Not covered by Toronto&apos;s city-wide zoning by-law (569-2013).</span>{" "}
        This site follows a former municipal or site-specific by-law, which is common for condo buildings. Check the
        applicable by-law with the City before planning changes.
      </p>
    );
  }

  return (
    <div className="space-y-3 border-t border-border pt-5">
      <div>
        <p className="text-sm text-muted">Zone</p>
        <p className="font-medium">
          {city.zone_category}
          {city.zone_label ? `, ${city.zone_label}` : ""}
          <span className="ml-2 font-mono text-xs text-muted">{city.zone_string}</span>
        </p>
      </div>
      <Facts
        items={[
          ...city.zone_rules.map((rule): [string, string] => [rule.label, rule.value]),
          ["Height limit", city.height_limit_m ? `${city.height_limit_m} m` : null],
          ["Max storeys", city.height_limit_storeys ? String(city.height_limit_storeys) : null],
          ["Max lot coverage", city.lot_coverage_pct ? `${city.lot_coverage_pct}%` : null],
          ["Parking zone", city.parking_zone],
          ["By-law section", city.zoning_bylaw_section],
        ]}
      />
      {MULTIPLEX_ZONES.has(city.zone_category) && (
        <p className="rounded-lg bg-accent/10 p-4 text-sm leading-relaxed">
          Residential zone: since May 2023 Toronto permits up to four units (duplex, triplex or fourplex) as-of-right
          here, as long as the building meets this zone&apos;s height, setback, depth and coverage rules.
          {city.zone_exception && ` Site-specific exception #${city.zone_exception} may change those rules.`}
        </p>
      )}
    </div>
  );
}

function Permits({ permits }: { permits: Permit[] }) {
  return (
    <div className="space-y-2">
      <h3 className="font-semibold">
        Building permits <span className="font-normal text-muted">({permits.length})</span>
      </h3>
      {permits.length === 0 ? (
        <p className="text-sm text-muted">No building permits on record for this address since 2000.</p>
      ) : (
        <div className="max-h-[28rem] overflow-auto rounded-xl border border-border bg-surface">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="sticky top-0 bg-surface text-left text-muted">
              <tr className="border-b border-border">
                <th className="px-4 py-2 font-medium">Applied</th>
                <th className="px-4 py-2 font-medium">Work</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="whitespace-nowrap px-4 py-2 text-right font-medium">Est. cost</th>
              </tr>
            </thead>
            <tbody>
              {permits.map((permit) => (
                <tr
                  key={`${permit.permit_num}-${permit.revision_num}`}
                  className="border-b border-border align-top last:border-0"
                >
                  <td className="whitespace-nowrap px-4 py-2 tabular-nums">{formatDate(permit.application_date)}</td>
                  <td className="px-4 py-2">
                    <p>{permit.work ?? permit.permit_type}</p>
                    {permit.description && <p className="line-clamp-2 text-xs text-muted">{permit.description}</p>}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2">{permit.status}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-right tabular-nums">
                    {permit.est_construction_cost ? formatPrice(permit.est_construction_cost) : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
