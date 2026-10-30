/** Presentational pieces for Committee of Adjustment precedents, shared by the server section and the client form. */

import { OUTCOME_LABELS, type Outcome, type Precedent, type PrecedentSummary } from "@/lib/zoning";
import { Chip } from "../../ui";

export function SummaryChips({ summary, compact }: { summary: PrecedentSummary; compact?: boolean }) {
  const chips: [string, number, "success" | "danger" | "neutral"][] = [
    ["approved", summary.approved, "success"],
    ["refused", summary.refused, "danger"],
    ["withdrawn", summary.withdrawn, "neutral"],
    ["pending", summary.pending + summary.deferred, "neutral"],
  ];
  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? "text-xs" : "text-sm"}`}>
      {chips
        .filter(([, count]) => count > 0)
        .map(([label, count, tone]) => (
          <Chip key={label} tone={tone} className="tabular-nums">
            {count} {label}
          </Chip>
        ))}
      {summary.approval_rate != null && (
        <span className="text-xs text-muted">
          {Math.round(summary.approval_rate * 100)}% approved
          {summary.appealed > 0 && `, ${summary.appealed} appealed`}
        </span>
      )}
    </div>
  );
}

const OUTCOME_TONE: Record<Outcome, string> = {
  approved: "text-success",
  refused: "text-danger",
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
