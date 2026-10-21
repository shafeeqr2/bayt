import type { Potential } from "@/lib/api";

/** The ways a buyer could add value, as small chips. Used on search cards and the listing page. */
export function PotentialChips({ potential, max }: { potential: Potential[]; max?: number }) {
  if (potential.length === 0) return null;
  const shown = max ? potential.slice(0, max) : potential;
  const extra = potential.length - shown.length;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Ways to add value">
      {shown.map((p) => (
        <li
          key={p.key}
          title={p.detail}
          className="rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent"
        >
          {p.label}
        </li>
      ))}
      {extra > 0 && (
        <li className="rounded-full border border-border px-2 py-0.5 text-xs text-muted">+{extra}</li>
      )}
    </ul>
  );
}
