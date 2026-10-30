import Image from "next/image";
import Link from "next/link";

import {
  FACET_LABELS,
  FACETS,
  getHouseProfile,
  getSimilarHomes,
  PERSONA_LABELS,
  PERSONAS,
  type ListingDetail,
  type PersonaKey,
  type SimilarHome,
  type Steer,
} from "@/lib/api";
import { bedsLabel, formatPrice, formatSqft } from "@/lib/format";
import { BathIcon, BedIcon, RulerIcon, SparklesIcon } from "../../icons";
import { DismissButton, SaveButton } from "../../save-buttons";
import { Help, ScoreBar, button, card } from "../../ui";
import { WHO, activeFacets, moreLikeThisHref, similarHref } from "./steer";

/**
 * The body of the "More like this" page. Left: the source house, the buyer switch (with this
 * house's score per buyer), the "like this, but..." box, 5 facet chips and the pitch the search
 * runs from. Right: the reranked matches, best first, with one reason line each.
 *
 * Every control writes the page URL (`?persona=&steer=&facets=`), so this is a server component;
 * the backend caches the rewrite and the rerank.
 */
export async function SimilarPanel({ listing, steer }: { listing: ListingDetail; steer: Steer }) {
  const { persona } = steer;
  const id = listing.id;
  const [profile, similar] = await Promise.all([getHouseProfile(id), getSimilarHomes(id, steer)]);
  const scores = new Map((profile?.personas ?? []).map((p) => [p.persona, p.score]));
  const view = profile?.personas.find((p) => p.persona === persona) ?? null;
  const facets = activeFacets(steer);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-10">
      <div className="space-y-5 lg:sticky lg:top-24 lg:self-start">
        <SourceHouse listing={listing} />

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wider text-muted">I am</p>
          <PersonaSwitch id={id} steer={steer} scores={scores} />
        </div>

        <SteerControls id={id} steer={steer} />

        {similar?.steered && similar.target ? (
          <div className="space-y-1 rounded-xl border border-accent/40 bg-accent-soft/60 p-4 text-sm">
            <p className="text-xs font-medium uppercase tracking-wide text-accent">Looking for: like this, but {similar.steer}</p>
            <p className="leading-relaxed">{similar.target}</p>
          </div>
        ) : (
          view && (
            <div className="space-y-2 rounded-xl border border-border bg-surface p-4 text-sm">
              <p className="text-xs font-medium uppercase tracking-wide text-muted">Why {WHO[persona]} likes this house</p>
              <p className="leading-relaxed">{view.pitch}</p>
              {(view.signals.length > 0 || view.concerns.length > 0) && (
                <details>
                  <summary className="cursor-pointer text-accent hover:underline">Why {view.score}/10</summary>
                  <div className="mt-2 grid gap-3 text-muted sm:grid-cols-2">
                    {view.signals.length > 0 && (
                      <div>
                        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-foreground">For</p>
                        <ul className="space-y-0.5">
                          {view.signals.map((s) => (
                            <li key={s}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {view.concerns.length > 0 && (
                      <div>
                        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-foreground">Against</p>
                        <ul className="space-y-0.5">
                          {view.concerns.map((s) => (
                            <li key={s}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </details>
              )}
            </div>
          )
        )}

        {similar && similar.items.length > 0 && (
          <div className="space-y-2 text-sm">
            {similar.distinct && (
              <p>
                <span className="font-medium">What sets this home apart:</span> <span className="text-muted">{similar.distinct}</span>
              </p>
            )}
            <p className="text-xs text-muted">
              {similar.candidates} candidates · {similar.filters.join(", ")} · compared on{" "}
              {facets.map((f) => FACET_LABELS[f].toLowerCase()).join(", ")}
              {similar.reranked && similar.model ? ` · ranked by ${similar.model.split("/").pop()}` : " · nearest by profile"}
              {similar.note ? ` · ${similar.note}` : ""}
            </p>
          </div>
        )}
      </div>

      {!similar || similar.items.length === 0 ? (
        <p className="self-start rounded-xl border border-dashed border-border p-5 text-sm text-muted">
          {similar?.note ? `No matches yet: ${similar.note}.` : "No matches yet. The profile for this home is still being prepared."}
        </p>
      ) : (
        <ol className="space-y-3" aria-label="Similar homes, best match first">
          {similar.items.map((item, i) => (
            <li key={item.listing.id}>
              <SimilarCard item={item} rank={i + 1} eager={i < 3} persona={persona} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** The house the search starts from: photo, price, facts, and a way back to its page. */
function SourceHouse({ listing }: { listing: ListingDetail }) {
  const facts = [bedsLabel(listing.bedrooms_text), listing.bathrooms != null ? `${listing.bathrooms} ba` : null, formatSqft(listing.sqft_min, listing.sqft_max)]
    .filter(Boolean)
    .join(" · ");
  return (
    <Link href={`/listings/${listing.id}`} className={`${card} group flex cursor-pointer gap-4 p-3 transition-shadow duration-200 hover:shadow-float`}>
      <div className="relative aspect-[4/3] w-28 shrink-0 overflow-hidden rounded-lg bg-border">
        {listing.cover_photo && <Image src={listing.cover_photo} alt={listing.address ?? "Listing photo"} fill sizes="112px" className="object-cover" />}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium uppercase tracking-wider text-muted">Like this house</p>
        <p className="display text-xl font-semibold">{formatPrice(listing.price)}</p>
        <p className="truncate text-sm">{listing.address}</p>
        <p className="truncate text-sm text-muted">{[facts, listing.community].filter(Boolean).join(" · ")}</p>
      </div>
    </Link>
  );
}

/** The 4 personas as a 2 x 2 switch, each with this house's score for that buyer. */
function PersonaSwitch({ id, steer, scores }: { id: string; steer: Steer; scores: Map<PersonaKey, number> }) {
  return (
    <nav className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-surface p-1" aria-label="Buyer persona">
      {PERSONAS.map((key) => {
        const active = key === steer.persona;
        const score = scores.get(key);
        return (
          <Link
            key={key}
            href={similarHref(id, { ...steer, persona: key })}
            scroll={false}
            aria-current={active ? "true" : undefined}
            className={`flex items-center justify-between gap-1.5 rounded-md px-3 py-2 text-sm transition-colors duration-200 ${
              active ? "bg-foreground font-medium text-background" : "text-muted hover:bg-surface-2 hover:text-foreground"
            }`}
          >
            {PERSONA_LABELS[key]}
            {score != null && <span className={`tabular-nums ${active ? "opacity-70" : "text-foreground/70"}`}>{score}</span>}
          </Link>
        );
      })}
    </nav>
  );
}

/** The "like this, but..." box (a GET form that keeps the persona and the facets) and the 5 facet chips (links). */
function SteerControls({ id, steer }: { id: string; steer: Steer }) {
  const facets = activeFacets(steer);
  return (
    <div className="space-y-3">
      <form action={`/listings/${encodeURIComponent(id)}/similar`} method="get" className={`${card} space-y-3 p-4`}>
        <input type="hidden" name="persona" value={steer.persona} />
        {steer.facets && <input type="hidden" name="facets" value={steer.facets.join(",")} />}
        <label className="block space-y-2">
          <span className="flex items-center gap-2 text-base font-semibold">
            <SparklesIcon className="size-5 text-accent" />
            Like this, but…
          </span>
          <textarea
            name="steer"
            defaultValue={steer.text ?? ""}
            maxLength={200}
            rows={3}
            placeholder="a bigger backyard and a garage · the same kitchen, any neighbourhood"
            className="w-full resize-y rounded-lg border border-border bg-background px-3 py-2.5 text-base leading-relaxed outline-none transition-colors duration-200 placeholder:text-muted/70 focus:border-accent"
          />
        </label>
        <div className="flex items-center gap-2">
          <button type="submit" className={`${button.primary} flex-1`}>
            <SparklesIcon className="size-4" />
            Find homes like this
          </button>
          {steer.text && (
            <Link href={similarHref(id, { ...steer, text: undefined })} scroll={false} className={button.ghost}>
              Clear
            </Link>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs" role="group" aria-label="Compare on">
          <span className="mr-1 text-muted">Compare on</span>
          {FACETS.map((f) => {
            const on = facets.includes(f);
            const last = on && facets.length === 1;
            const next = on ? facets.filter((x) => x !== f) : FACETS.filter((x) => x === f || facets.includes(x));
            const className = `rounded-full border px-2.5 py-1 transition-colors duration-200 ${
              on ? "border-accent/40 bg-accent-soft text-accent" : "border-dashed border-border text-muted line-through"
            } ${last ? "cursor-default" : "cursor-pointer hover:border-accent"}`;
            if (last) {
              return (
                <span key={f} className={className} aria-pressed="true" title="Keep at least 1 facet on">
                  {FACET_LABELS[f]}
                </span>
              );
            }
            return (
              <Link key={f} href={similarHref(id, { ...steer, facets: next })} scroll={false} aria-pressed={on} className={className}>
                {FACET_LABELS[f]}
              </Link>
            );
          })}
          {steer.facets && (
            <Link href={similarHref(id, { ...steer, facets: undefined })} scroll={false} className="px-1 text-muted hover:text-foreground">
              All
            </Link>
          )}
          <Help label="What these mean">
            Layout is rooms, levels and suites; finish is kitchens, baths and condition; lot is size, parking and outdoor
            space; location keeps the search within 5 km; money keeps it within 25% of the price. Turn one off to ignore it.
          </Help>
        </div>
      </form>
    </div>
  );
}

/** One ranked match: rank and photo on the left, price, facts and the model's reason on the right. */
function SimilarCard({ item, rank, eager, persona }: { item: SimilarHome; rank: number; eager: boolean; persona: PersonaKey }) {
  const { listing } = item;
  const facts = [
    [BedIcon, bedsLabel(listing.bedrooms_text)],
    [BathIcon, listing.bathrooms != null ? `${listing.bathrooms} ba` : null],
    [RulerIcon, formatSqft(listing.sqft_min, listing.sqft_max)],
  ] as const;
  return (
    <article data-tile className="group relative flex gap-4 rounded-card border border-border bg-surface p-3 shadow-card transition-shadow duration-200 hover:shadow-float sm:gap-5">
      <div className="relative aspect-[4/3] w-28 shrink-0 overflow-hidden rounded-lg bg-border sm:w-40">
        {listing.cover_photo && (
          <Image
            src={listing.cover_photo}
            alt={listing.address ?? "Listing photo"}
            fill
            loading={eager ? "eager" : "lazy"}
            sizes="(min-width: 640px) 160px, 112px"
            className="object-cover transition-transform duration-300 group-hover:scale-[1.02]"
          />
        )}
        <span className="display absolute left-2 top-2 flex size-7 items-center justify-center rounded-full bg-foreground/90 text-sm font-semibold tabular-nums text-background backdrop-blur">
          {rank}
        </span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-start justify-between gap-3">
          {/* The whole card is this link (the ::after overlay); the "more like this" button sits above it. */}
          <Link href={`/listings/${listing.id}?persona=${persona}&via=similar`} className="display text-xl font-semibold after:absolute after:inset-0 after:rounded-card">
            {formatPrice(listing.price)}
          </Link>
          <ScoreBar score={item.score} />
        </div>
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-sm tabular-nums" aria-label="Key facts">
          {facts
            .filter(([, value]) => value)
            .map(([Icon, value]) => (
              <li key={value} className="flex items-center gap-1.5">
                <Icon className="size-4 text-muted" />
                {value}
              </li>
            ))}
        </ul>
        <p className="truncate text-sm text-muted">
          {listing.address}
          {listing.community ? `, ${listing.community}` : ""}
        </p>
        <p className="line-clamp-2 pt-1 text-sm leading-snug sm:line-clamp-3">{item.reason}</p>
      </div>
      {/* In flow, not floating over the reason text: a column of actions down the right edge. */}
      <div className="flex shrink-0 flex-col items-center justify-end gap-1.5 self-stretch">
        <DismissButton id={listing.id} via="similar" persona={persona} />
        <SaveButton id={listing.id} via="similar" persona={persona} />
        <MoreLikeThis id={listing.id} persona={persona} />
      </div>
    </article>
  );
}

/** The "more like this" button on a tile: opens the similar page with that house as the one to match. */
export function MoreLikeThis({ id, persona, className = "" }: { id: string; persona?: PersonaKey; className?: string }) {
  return (
    <Link
      href={moreLikeThisHref(id, persona)}
      title="More like this"
      aria-label="More like this"
      className={`z-10 inline-flex size-9 cursor-pointer items-center justify-center rounded-full border border-border bg-surface/95 text-accent shadow-card backdrop-blur transition-colors duration-200 hover:bg-accent hover:text-accent-foreground ${className}`}
    >
      <SparklesIcon className="size-4" />
    </Link>
  );
}
