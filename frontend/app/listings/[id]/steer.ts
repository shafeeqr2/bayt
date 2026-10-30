import { FACETS, PERSONAS, type FacetKey, type PersonaKey, type Steer } from "@/lib/api";

const MAX_TEXT = 200;

/** The buyer, as the copy names them. */
export const WHO: Record<PersonaKey, string> = {
  first_time_buyer: "a first-time buyer",
  investor: "an investor",
  flipper: "a flipper",
  builder: "a builder",
};

/**
 * The similar page's state lives in its URL (`/listings/{id}/similar?persona=&steer=&facets=`),
 * so the page is a server component and every control is a link or a GET form. Facets are
 * omitted from the URL when all 5 are on; an empty or all-unknown list falls back to all.
 */
export function parseSteer(query: Record<string, string | string[] | undefined>, fallback: PersonaKey = "first_time_buyer"): Steer {
  const one = (key: string) => (typeof query[key] === "string" ? (query[key] as string) : undefined);
  const persona: PersonaKey = PERSONAS.includes(one("persona") as PersonaKey) ? (one("persona") as PersonaKey) : fallback;
  const text = one("steer")?.replace(/\s+/g, " ").trim().slice(0, MAX_TEXT) || undefined;
  const raw = one("facets");
  const picked = raw === undefined ? undefined : FACETS.filter((f) => raw.split(",").map((p) => p.trim().toLowerCase()).includes(f));
  const facets = picked && picked.length > 0 && picked.length < FACETS.length ? picked : undefined;
  return { persona, text, facets };
}

/** The similar page for one house, with a steer. */
export function similarHref(id: string, steer: Steer): string {
  const params = new URLSearchParams({ persona: steer.persona });
  if (steer.text) params.set("steer", steer.text);
  if (steer.facets && steer.facets.length < FACETS.length) params.set("facets", steer.facets.join(","));
  return `${similarPath(id)}?${params}`;
}

export function similarPath(id: string): string {
  return `/listings/${encodeURIComponent(id)}/similar`;
}

/** "More like this" from a tile: the similar page for that house, for the buyer in view when known. */
export function moreLikeThisHref(id: string, persona?: PersonaKey): string {
  return persona ? `${similarPath(id)}?persona=${persona}` : similarPath(id);
}

/** True when the URL names a buyer; false when the page fell back to a default. */
export function personaGiven(query: Record<string, string | string[] | undefined>): boolean {
  return PERSONAS.includes(query.persona as PersonaKey);
}

/** The active facets, in catalogue order. */
export function activeFacets(steer: Steer): FacetKey[] {
  return steer.facets ?? [...FACETS];
}
