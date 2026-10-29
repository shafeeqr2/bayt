import Image from "next/image";
import Link from "next/link";

import { getHouseProfile, getSimilarHomes, PERSONA_LABELS, PERSONAS, type PersonaKey, type SimilarHome } from "@/lib/api";
import { bedsLabel, formatPrice, formatSqft } from "@/lib/format";

/**
 * "Similar homes" for one persona: the persona toggle (with this house's score per persona),
 * the source house's signals, and the reranked neighbours with one reason line each.
 *
 * The toggle is 4 links on `?persona=`, so the row is a server component and the page
 * re-renders with the new persona; the backend caches the rerank per candidate set.
 */
export async function SimilarRow({ id, persona }: { id: string; persona: PersonaKey }) {
  const [profile, similar] = await Promise.all([getHouseProfile(id), getSimilarHomes(id, persona)]);
  const scores = new Map((profile?.personas ?? []).map((p) => [p.persona, p.score]));
  const view = profile?.personas.find((p) => p.persona === persona) ?? null;

  return (
    <section id="similar" className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Similar homes</h2>
        <p className="text-sm text-muted">
          The same house appeals to different buyers for different reasons. Pick who you are; the matches and the reasons change.
        </p>
      </div>

      <nav className="flex flex-wrap gap-2" aria-label="Buyer persona">
        {PERSONAS.map((key) => {
          const active = key === persona;
          const score = scores.get(key);
          return (
            <Link
              key={key}
              href={`?persona=${key}#similar`}
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

      {view && (
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
            {similar.candidates} candidates, {similar.filters.join(", ")}.{" "}
            {similar.reranked ? `Ranked and explained by ${similar.model}.` : `Nearest by profile${similar.note ? ` (${similar.note})` : ""}.`}
          </p>
        </>
      )}
    </section>
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
