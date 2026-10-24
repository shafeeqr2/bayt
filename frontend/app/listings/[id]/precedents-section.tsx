import { getPrecedents } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { APPLICATION_TYPE_LABELS, type Precedent } from "@/lib/zoning";
import { OutcomeLabel, SummaryChips } from "./precedents-ui";

const SHOWN = 15;

/**
 * Committee of Adjustment applications near the listing, from Toronto Open Data, nearest first.
 * Renders nothing when the data has not been loaded (`./start.sh city-data`).
 */
export async function PrecedentsSection({ id }: { id: string }) {
  const search = await getPrecedents(id);
  if (!search) return null;
  const { summary, items, radius_m } = search;

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <h3 className="font-semibold">
          Committee of Adjustment decisions nearby{" "}
          <span className="font-normal text-muted">
            ({summary.total} within {radius_m} m)
          </span>
        </h3>
        <p className="text-sm text-muted">
          What neighbours asked the committee for and what it decided, since 2001. The city publishes the decision and
          the description, not the variance table, so an approval nearby is not an approval of a plan here.
        </p>
      </div>

      {summary.total === 0 ? (
        <p className="text-sm text-muted">No application on file within {radius_m} m.</p>
      ) : (
        <>
          <SummaryChips summary={summary} />
          <div className="max-h-[32rem] overflow-auto rounded-xl border border-border bg-surface">
            <table className="w-full min-w-[44rem] text-sm">
              <thead className="sticky top-0 bg-surface text-left text-muted">
                <tr className="border-b border-border">
                  <th className="px-4 py-2 font-medium">Where</th>
                  <th className="px-4 py-2 font-medium">Asked for</th>
                  <th className="whitespace-nowrap px-4 py-2 font-medium">Heard</th>
                  <th className="px-4 py-2 font-medium">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {items.slice(0, SHOWN).map((p) => (
                  <PrecedentRow key={p.sys_id} p={p} />
                ))}
              </tbody>
            </table>
            {items.length > SHOWN && (
              <p className="border-t border-border px-4 py-2 text-xs text-muted">
                Showing the nearest {SHOWN} of {items.length}.
              </p>
            )}
          </div>
        </>
      )}
      <p className="text-xs text-muted">
        Source:{" "}
        <a href={search.source_url} target="_blank" rel="noreferrer" className="hover:underline">
          Toronto Open Data, Committee of Adjustment Applications
        </a>
        . Each file is placed on the city address point for its street address.
      </p>
    </div>
  );
}

function PrecedentRow({ p }: { p: Precedent }) {
  return (
    <tr className="border-b border-border align-top last:border-0">
      <td className="px-4 py-2">
        <p>{p.address ?? "Address withheld"}</p>
        <p className="text-xs text-muted tabular-nums">
          {Math.round(p.distance_m)} m{p.reference_file && ` · ${p.reference_file}`}
        </p>
      </td>
      <td className="px-4 py-2">
        <p className="text-xs text-muted">
          {[APPLICATION_TYPE_LABELS[p.application_type ?? ""] ?? p.application_type, p.work_type].filter(Boolean).join(" · ")}
        </p>
        {p.description && <p className="line-clamp-3 leading-snug">{p.description}</p>}
      </td>
      <td className="whitespace-nowrap px-4 py-2 tabular-nums">{p.hearing_date ? formatDate(p.hearing_date) : "—"}</td>
      <td className="px-4 py-2">
        <OutcomeLabel p={p} />
      </td>
    </tr>
  );
}
