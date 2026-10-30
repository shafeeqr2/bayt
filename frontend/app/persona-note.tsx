import Link from "next/link";

import { PERSONA_LABELS, PERSONAS, type PersonaKey } from "@/lib/api";
import { SparklesIcon } from "./icons";

/**
 * One quiet line shown when the buyer was set from the session's taste summary rather than
 * the URL: which buyer, why, and a link per buyer to change it. `href(persona)` builds the
 * same page with that buyer in the URL.
 */
export function PersonaNote({ persona, href }: { persona: PersonaKey; href: (p: PersonaKey) => string }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
      <SparklesIcon className="size-3.5 text-accent" />
      <span>
        Set for you: <span className="font-medium text-foreground">{PERSONA_LABELS[persona]}</span>, from what you have opened and saved.
      </span>
      <span className="flex items-center gap-1">
        <span>Change:</span>
        {PERSONAS.filter((p) => p !== persona).map((p) => (
          <Link key={p} href={href(p)} className="text-accent hover:underline">
            {PERSONA_LABELS[p]}
          </Link>
        ))}
      </span>
    </p>
  );
}
