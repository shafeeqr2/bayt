import Image from "next/image";
import Link from "next/link";

import { bestPersona, PERSONA_LABELS, type ListingSummary, type PersonaKey } from "@/lib/api";
import { formatPrice, formatSqft } from "@/lib/format";
import { BathIcon, BedIcon, RulerIcon } from "./icons";
import { MoreLikeThis } from "./listings/[id]/similar-row";
import { PotentialChips } from "./potential-chips";
import { SaveButton } from "./save-buttons";

/**
 * One search result. With a `persona` the badge is that buyer's score from the house
 * profile; without one it is the persona the house suits best. No badge until the
 * profile is written.
 */
export function ListingCard({
  listing,
  eager,
  persona,
  saved = false,
  via = "search",
}: {
  listing: ListingSummary;
  eager: boolean;
  persona?: PersonaKey;
  saved?: boolean;
  via?: string;
}) {
  const chosen = persona && listing.persona_scores?.[persona] != null ? { persona, score: listing.persona_scores[persona]! } : null;
  const badge = chosen ?? bestPersona(listing.persona_scores);
  const query = new URLSearchParams({ via });
  if (persona ?? badge) query.set("persona", (persona ?? badge!.persona) as string);
  const href = `/listings/${listing.id}?${query}`;
  const beds = listing.bedrooms_text?.replace(/\s+/g, "") ?? null;
  const sqft = formatSqft(listing.sqft_min, listing.sqft_max);
  const where = [listing.address, listing.community ?? listing.city].filter(Boolean).join(", ");

  return (
    <article data-tile className="group relative flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-card transition-shadow duration-200 hover:shadow-float">
      <div className="relative aspect-[4/3] overflow-hidden bg-border">
        {listing.cover_photo && (
          <Image
            src={listing.cover_photo}
            alt={listing.address ?? "Listing photo"}
            fill
            loading={eager ? "eager" : "lazy"}
            fetchPriority={eager ? "high" : "auto"}
            sizes="(min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
            className="object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        )}
        {listing.building_type && (
          <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-xs font-medium text-[#161b18] shadow-sm backdrop-blur">
            {listing.building_type}
          </span>
        )}
        {badge && (
          <span
            className="absolute right-3 top-3 inline-flex items-center gap-1.5 rounded-full bg-[#161b18]/85 py-1 pl-2.5 pr-1 text-xs font-medium text-white backdrop-blur"
            title={`${PERSONA_LABELS[badge.persona]} fit, 1 to 10, from the house profile`}
          >
            {PERSONA_LABELS[badge.persona]}
            <span className="rounded-full bg-white/15 px-1.5 py-0.5 tabular-nums">{badge.score}</span>
          </span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-2 p-4">
        {/* The whole tile is this link (the ::after overlay); the "more like this" button sits above it. */}
        <Link href={href} className="display text-xl font-semibold tabular-nums transition-colors duration-200 after:absolute after:inset-0 group-hover:text-accent">
          {formatPrice(listing.price)}
        </Link>
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm tabular-nums" aria-label="Key facts">
          {beds && (
            <li className="flex items-center gap-1.5">
              <BedIcon className="size-4 text-muted" />
              <span>
                {beds} <span className="text-muted">bd</span>
              </span>
            </li>
          )}
          {listing.bathrooms != null && (
            <li className="flex items-center gap-1.5">
              <BathIcon className="size-4 text-muted" />
              <span>
                {listing.bathrooms} <span className="text-muted">ba</span>
              </span>
            </li>
          )}
          {sqft && (
            <li className="flex items-center gap-1.5">
              <RulerIcon className="size-4 text-muted" />
              <span>{sqft}</span>
            </li>
          )}
        </ul>
        <p className="truncate text-sm text-muted" title={where}>
          {where}
        </p>
        {listing.investment && listing.investment.potential.length > 0 && (
          <div className="mt-auto pt-1">
            <PotentialChips potential={listing.investment.potential} max={2} />
          </div>
        )}
      </div>
      <div className="absolute bottom-3 right-3 flex items-center gap-1.5">
        <SaveButton id={listing.id} saved={saved} via={via} persona={persona ?? badge?.persona} />
        <MoreLikeThis id={listing.id} persona={persona ?? badge?.persona} />
      </div>
    </article>
  );
}
