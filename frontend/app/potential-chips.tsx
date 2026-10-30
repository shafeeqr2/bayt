import type { Potential } from "@/lib/api";
import { Chip } from "./ui";

/** The ways a buyer could add value, as small chips. Used on search cards and the listing page. */
export function PotentialChips({ potential, max }: { potential: Potential[]; max?: number }) {
  if (potential.length === 0) return null;
  const shown = max ? potential.slice(0, max) : potential;
  const extra = potential.length - shown.length;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Ways to add value">
      {shown.map((p) => (
        <li key={p.key}>
          <Chip title={p.detail}>{p.label}</Chip>
        </li>
      ))}
      {extra > 0 && (
        <li>
          <Chip tone="neutral" title={potential.slice(shown.length).map((p) => p.label).join(", ")}>
            +{extra}
          </Chip>
        </li>
      )}
    </ul>
  );
}
