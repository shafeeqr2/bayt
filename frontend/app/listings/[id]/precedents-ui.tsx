/** Presentational pieces for Committee of Adjustment precedents, shared by the server section and the client form. */

import { OUTCOME_LABELS, type Outcome, type Precedent, type PrecedentSummary } from "@/lib/zoning";

export function SummaryChips({ summary, compact }: { summary: PrecedentSummary; compact?: boolean }) {
  const chips: [string, number, string][] = [
    ["Approved", summary.approved, "bg-emerald-600/15 text-emerald-700 dark:text-emerald-300"],
    ["Refused", summary.refused, "bg-accent/15 text-accent"],
    ["Withdrawn", summary.withdrawn, "bg-border text-muted"],
    ["Pending", summary.pending + summary.deferred, "bg-border text-muted"],
  ];
  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? "text-xs" : "text-sm"}`}>
      {chips
        .filter(([, count]) => count > 0)
        .map(([label, count, tone]) => (
          <span key={label} className={`rounded-full px-2.5 py-0.5 font-medium tabular-nums ${tone}`}>
            {count} {label.toLowerCase()}
          </span>
        ))}
      {summary.approval_rate != null && (
        <span className="text-muted">
          {Math.round(summary.approval_rate * 100)}% of decided files approved
          {summary.appealed > 0 && `, ${summary.appealed} appealed`}
        </span>
      )}
    </div>
  );
}

const OUTCOME_TONE: Record<Outcome, string> = {
  approved: "text-emerald-700 dark:text-emerald-300",
  refused: "text-accent",
  withdrawn: "text-muted",
  deferred: "text-muted",
  pending: "text-muted",
  unknown: "text-muted",
};

export function OutcomeLabel({ p }: { p: Precedent }) {
  return (
    <span className={`font-medium ${OUTCOME_TONE[p.outcome]}`}>
      {OUTCOME_LABELS[p.outcome]}
      {p.appeal && p.appeal_body && (
        <span className="block text-xs font-normal text-muted">
          {p.appeal === "dismissed" ? `${p.appeal_body} appeal dismissed` : p.appeal === "pending" ? `Under ${p.appeal_body} appeal` : `${p.appeal_body}: ${p.appeal}`}
        </span>
      )}
    </span>
  );
}
