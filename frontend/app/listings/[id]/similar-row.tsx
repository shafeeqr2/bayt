import Image from "next/image";
import Link from "next/link";

import { FACET_LABELS, FACETS, getHouseProfile, getSimilarHomes, PERSONA_LABELS, PERSONAS, type PersonaKey, type SimilarHome, type Steer } from "@/lib/api";
import { bedsLabel, formatPrice, formatSqft } from "@/lib/format";
import { activeFacets, similarHref } from "./steer";

/**
 * "Similar homes" for one persona, steered by the buyer: the persona toggle (with this
 * house's score per persona), a "like this, but..." box, 5 facet chips, the source house's
 * signals (or the rewritten target when steered), and the reranked neighbours with one
 * reason line each.
 *
 * Every control writes the page URL (`?persona=&steer=&facets=`), so the row is a server
 * component and the page re-renders; the backend caches the rewrite and the rerank.
 */
export async function SimilarRow({ id, steer }: { id: string; steer: Steer }) {
  const { persona } = steer;
  const [profile, similar] = await Promise.all([getHouseProfile(id), getSimilarHomes(id, steer)]);
  const scores = new Map((profile?.personas ?? []).map((p) => [p.persona, p.score]));
  const view = profile?.personas.find((p) => p.persona === persona) ?? null;
  const facets = activeFacets(steer);

  return (
    <section id="similar" className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Similar homes</h2>
        <p className="text-sm text-muted">
          The same house appeals to different buyers for different reasons. Pick who you are, say what to change, and choose what counts.
        </p>
      </div>

      <nav className="flex flex-wrap gap-2" aria-label="Buyer persona">
        {PERSONAS.map((key) => {
          const active = key === persona;
          const score = scores.get(key);
          return (
            <Link
              key={key}
              href={similarHref({ ...steer, persona: key })}
              scroll={false}
              aria-current={active ? "true" : undefined}
              className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                active ? "border-foreground bg-foreground text-background" : "border-border bg-surface hover:border-foreground/40"
              }`}
            >
              {PERSONA_LABELS[key]}
              {score != null && <span className={`ml-1.5 tabular-nums ${active ? "opacity-80" : "text-muted"}`}>{score}/10</span>}
            </Link>
          );
        })}
      </nav>

      <SteerControls steer={steer} />

      {similar?.steered && similar.target ? (
        <div className="space-y-2 rounded-xl border border-accent/40 bg-surface p-5 text-sm">
          <p className="text-xs font-medium uppercase tracking-wide text-muted">Looking for: like this, but {similar.steer}</p>
          <p className="leading-relaxed">{similar.target}</p>
        </div>
      ) : (
        view && (
          <div className="space-y-2 rounded-xl border border-border bg-surface p-5 text-sm">
            <p className="leading-relaxed">{view.pitch}</p>
            {view.signals.length > 0 && (
              <p className="text-muted">
                <span className="font-medium text-foreground">Why {view.score}/10:</span> {view.signals.join(" · ")}
                {view.concerns.length > 0 && (
                  <>
                    {" "}
                    <span className="font-medium text-foreground">Against:</span> {view.concerns.join(" · ")}
                  </>
                )}
              </p>
            )}
          </div>
        )
      )}

      {!similar || similar.items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-border p-5 text-sm text-muted">
          {similar?.note ? `No matches yet: ${similar.note}.` : "No matches yet. The profile for this home is still being prepared."}
        </p>
      ) : (
        <>
          {similar.distinct && (
            <p className="text-sm">
              <span className="font-medium">What sets this home apart:</span> <span className="text-muted">{similar.distinct}</span>
            </p>
          )}
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {similar.items.map((item, i) => (
              <li key={item.listing.id}>
                <SimilarCard item={item} eager={i < 4} persona={persona} />
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted">
            {similar.candidates} candidates, {similar.filters.join(", ")}, compared on {facets.map((f) => FACET_LABELS[f].toLowerCase()).join(", ")}.{" "}
            {similar.reranked ? `Ranked and explained by ${similar.model}.` : "Nearest by profile."}
            {similar.note ? ` ${similar.note[0].toUpperCase()}${similar.note.slice(1)}.` : ""}
          </p>
        </>
      )}
    </section>
  );
}

/** The "like this, but..." box (a GET form that keeps the persona and the facets) and the 5 facet chips (links). */
function SteerControls({ steer }: { steer: Steer }) {
  const facets = activeFacets(steer);
  return (
    <div className="space-y-3">
      <form action="#similar" method="get" className="flex flex-col gap-2 sm:flex-row">
        <input type="hidden" name="persona" value={steer.persona} />
        {steer.facets && <input type="hidden" name="facets" value={steer.facets.join(",")} />}
        <input
          name="steer"
          defaultValue={steer.text ?? ""}
          maxLength={200}
          placeholder="Like this, but… bigger backyard · same kitchen, any neighbourhood · closer to the subway"
          aria-label="Like this, but"
          className="h-10 flex-1 rounded-lg border border-border bg-surface px-3 text-sm outline-none focus:border-accent"
        />
        <div className="flex gap-2">
          <button type="submit" className="h-10 rounded-lg bg-accent px-4 text-sm font-medium text-accent-foreground hover:opacity-90">
            Steer
          </button>
          {steer.text && (
            <Link
              href={similarHref({ ...steer, text: undefined })}
              scroll={false}
              className="flex h-10 items-center rounded-lg px-3 text-sm text-muted hover:text-foreground"
            >
              Clear
            </Link>
          )}
        </div>
      </form>

      <div className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label="Compare on">
        <span className="text-muted">Compare on</span>
        {FACETS.map((f) => {
          const on = facets.includes(f);
          const last = on && facets.length === 1;
          const next = on ? facets.filter((x) => x !== f) : FACETS.filter((x) => x === f || facets.includes(x));
          const className = `rounded-full border px-3 py-1 transition-colors ${
            on ? "border-foreground/60 bg-surface" : "border-dashed border-border text-muted line-through"
          } ${last ? "cursor-default" : "hover:border-foreground"}`;
          if (last) {
            return (
              <span key={f} className={className} aria-pressed="true" title="Keep at least 1 facet on">
                {FACET_LABELS[f]}
              </span>
            );
          }
          return (
            <Link key={f} href={similarHref({ ...steer, facets: next })} scroll={false} aria-pressed={on} className={className}>
              {FACET_LABELS[f]}
            </Link>
          );
        })}
        {steer.facets && (
          <Link href={similarHref({ ...steer, facets: undefined })} scroll={false} className="px-1 text-muted hover:text-foreground">
            All
          </Link>
        )}
      </div>
    </div>
  );
}

function SimilarCard({ item, eager, persona }: { item: SimilarHome; eager: boolean; persona: PersonaKey }) {
  const { listing } = item;
  const facts = [
    bedsLabel(listing.bedrooms_text),
    listing.bathrooms != null ? `${listing.bathrooms} ba` : null,
    formatSqft(listing.sqft_min, listing.sqft_max),
  ].filter(Boolean);
  return (
    <Link
      href={`/listings/${listing.id}?persona=${persona}`}
      className="group flex h-full flex-col overflow-hidden rounded-xl border border-border bg-surface transition-shadow hover:shadow-lg"
    >
      <div className="relative aspect-[4/3] bg-border">
        {listing.cover_photo && (
          <Image
            src={listing.cover_photo}
            alt={listing.address ?? "Listing photo"}
            fill
            loading={eager ? "eager" : "lazy"}
            sizes="(min-width: 1024px) 25vw, (min-width: 640px) 50vw, 100vw"
            className="object-cover transition-transform duration-300 group-hover:scale-[1.02]"
          />
        )}
        <span className="absolute right-3 top-3 rounded-full bg-surface/90 px-2.5 py-1 text-xs font-medium tabular-nums backdrop-blur">
          {item.score}/10
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-4">
        <p className="text-lg font-semibold tabular-nums">{formatPrice(listing.price)}</p>
        <p className="text-sm tabular-nums">{facts.join(" · ")}</p>
        <p className="truncate text-sm text-muted">
          {listing.address}
          {listing.community ? `, ${listing.community}` : ""}
        </p>
        <p className="pt-1 text-sm leading-snug">{item.reason}</p>
      </div>
    </Link>
  );
}
