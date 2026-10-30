import { FACETS, PERSONAS, type FacetKey, type PersonaKey, type Steer } from "@/lib/api";

const MAX_TEXT = 200;

/**
 * The similar row's state lives in the page URL (`?persona=&steer=&facets=`), so the row
 * is a server component and every control is a link or a GET form. Facets are omitted
 * from the URL when all 5 are on; an empty or all-unknown list falls back to all.
 */
export function parseSteer(query: Record<string, string | string[] | undefined>): Steer {
  const one = (key: string) => (typeof query[key] === "string" ? (query[key] as string) : undefined);
  const persona: PersonaKey = PERSONAS.includes(one("persona") as PersonaKey) ? (one("persona") as PersonaKey) : "first_time_buyer";
  const text = one("steer")?.replace(/\s+/g, " ").trim().slice(0, MAX_TEXT) || undefined;
  const raw = one("facets");
  const picked = raw === undefined ? undefined : FACETS.filter((f) => raw.split(",").map((p) => p.trim().toLowerCase()).includes(f));
  const facets = picked && picked.length > 0 && picked.length < FACETS.length ? picked : undefined;
  return { persona, text, facets };
}

/** The page URL for a steer, pointing at the similar row. */
export function similarHref(steer: Steer): string {
  const params = new URLSearchParams({ persona: steer.persona });
  if (steer.text) params.set("steer", steer.text);
  if (steer.facets && steer.facets.length < FACETS.length) params.set("facets", steer.facets.join(","));
  return `?${params}#similar`;
}

/** The active facets, in catalogue order. */
export function activeFacets(steer: Steer): FacetKey[] {
  return steer.facets ?? [...FACETS];
}
