import type { ReactNode } from "react";

import { ChevronDownIcon, InfoIcon } from "./icons";

/*
  Shared building blocks for both pages. Everything here renders on the server:
  disclosures use the native <details> element, so the long explanations cost no
  JavaScript and stay out of the way until asked for.
*/

export const card = "rounded-card border border-border bg-surface shadow-card";
export const button = {
  primary:
    "inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-lg bg-accent px-4 text-sm font-medium text-accent-foreground transition-colors duration-200 hover:bg-accent/90 disabled:cursor-default disabled:opacity-60",
  secondary:
    "inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-lg border border-border bg-surface px-4 text-sm font-medium transition-colors duration-200 hover:border-foreground/40",
  ghost:
    "inline-flex h-10 cursor-pointer items-center justify-center gap-2 rounded-lg px-3 text-sm text-muted transition-colors duration-200 hover:text-foreground",
};
export const control =
  "h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm outline-none transition-colors duration-200 focus:border-accent";

/** A section: one title, one short lead, and the long explanation behind "How this works". */
export function Section({
  id,
  eyebrow,
  title,
  lead,
  help,
  helpLabel = "How this works",
  action,
  children,
  className = "",
}: {
  id?: string;
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  help?: ReactNode;
  helpLabel?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={`scroll-mt-28 space-y-5 ${className}`}>
      <SectionHeader eyebrow={eyebrow} title={title} lead={lead} help={help} helpLabel={helpLabel} action={action} />
      {children}
    </section>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  lead,
  help,
  helpLabel = "How this works",
  action,
  level = 2,
}: {
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  help?: ReactNode;
  helpLabel?: string;
  action?: ReactNode;
  level?: 2 | 3;
}) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0 space-y-1">
        {eyebrow && <p className="text-xs font-medium uppercase tracking-wider text-accent">{eyebrow}</p>}
        <Heading className={level === 2 ? "display text-2xl font-semibold sm:text-[1.75rem]" : "text-lg font-semibold"}>
          {title}
        </Heading>
        {(lead || help) && (
          <div className="max-w-2xl text-sm text-muted">
            {lead}
            {help && (
              <>
                {lead ? " " : null}
                <Help label={helpLabel}>{help}</Help>
              </>
            )}
          </div>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** An inline disclosure for the fine print. Closed, it is 1 small link; open, a quiet note under the lead. */
export function Help({ label = "How this works", children }: { label?: string; children: ReactNode }) {
  return (
    <details className="inline">
      <summary className="inline-flex cursor-pointer items-center gap-1 text-accent hover:underline">
        <InfoIcon className="size-3.5" />
        {label}
      </summary>
      <span className="mt-2 block max-w-2xl rounded-lg bg-surface-2 p-3 text-sm leading-relaxed text-muted">{children}</span>
    </details>
  );
}

/**
 * A card that opens on click. The summary row holds the title, a count and anything
 * worth seeing while closed (chips, totals); the body holds the table.
 */
export function Disclosure({
  title,
  count,
  summary,
  open = false,
  children,
  level = 3,
}: {
  title: ReactNode;
  count?: ReactNode;
  summary?: ReactNode;
  open?: boolean;
  children: ReactNode;
  level?: 2 | 3;
}) {
  const Heading = level === 2 ? "h2" : "h3";
  return (
    <details open={open} className={`group ${card} overflow-hidden`}>
      <summary className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 transition-colors duration-200 hover:bg-surface-2">
        <Heading className="flex items-center gap-2 text-base font-semibold">
          {title}
          {count != null && <span className="font-normal tabular-nums text-muted">{count}</span>}
        </Heading>
        {summary && <div className="min-w-0 flex-1">{summary}</div>}
        <ChevronDownIcon className="chev ml-auto size-5 shrink-0 text-muted transition-transform duration-200" />
      </summary>
      <div className="border-t border-border">{children}</div>
    </details>
  );
}

/** A small label, with the brand tint by default. */
export function Chip({
  children,
  tone = "brand",
  className = "",
  title,
}: {
  children: ReactNode;
  tone?: "brand" | "neutral" | "danger" | "success" | "solid";
  className?: string;
  title?: string;
}) {
  const tones = {
    brand: "bg-accent-soft text-accent",
    neutral: "bg-surface-2 text-muted",
    danger: "bg-danger-soft text-danger",
    success: "bg-success/12 text-success",
    solid: "bg-foreground text-background",
  };
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${tones[tone]} ${className}`}>
      {children}
    </span>
  );
}

/** A label and value, for fact grids. */
export function Fact({ label, value, icon }: { label: string; value: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      {icon && <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted">{icon}</span>}
      <div className="min-w-0">
        <dt className="text-xs text-muted">{label}</dt>
        <dd className="font-medium tabular-nums">{value}</dd>
      </div>
    </div>
  );
}

/** The "n/10" fit score, drawn as a short bar so a row of 4 scans without reading. */
export function ScoreBar({ score, active = false }: { score: number; active?: boolean }) {
  return (
    <span className="flex items-center gap-2" aria-label={`${score} out of 10`}>
      <span className={`h-1.5 w-16 overflow-hidden rounded-full ${active ? "bg-background/30" : "bg-border"}`}>
        <span
          className={`block h-full rounded-full ${active ? "bg-background" : "bg-accent"}`}
          style={{ width: `${Math.max(6, Math.min(100, score * 10))}%` }}
        />
      </span>
      <span className="tabular-nums">{score}</span>
    </span>
  );
}
