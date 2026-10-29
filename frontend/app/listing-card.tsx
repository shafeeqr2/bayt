import Image from "next/image";
import Link from "next/link";

import { bestPersona, PERSONA_LABELS, type ListingSummary, type PersonaKey } from "@/lib/api";
import { bedsLabel, formatPrice, formatSqft } from "@/lib/format";
import { PotentialChips } from "./potential-chips";

/**
 * One search result. With a `persona` the badge is that buyer's score from the house
 * profile; without one it is the persona the house suits best. No badge until the
 * profile is written.
 */
export function ListingCard({ listing, eager, persona }: { listing: ListingSummary; eager: boolean; persona?: PersonaKey }) {
  const facts = [
    bedsLabel(listing.bedrooms_text),
    listing.bathrooms != null ? `${listing.bathrooms} ba` : null,
    formatSqft(listing.sqft_min, listing.sqft_max),
  ].filter(Boolean);
  const chosen = persona && listing.persona_scores?.[persona] != null ? { persona, score: listing.persona_scores[persona]! } : null;
  const badge = chosen ?? bestPersona(listing.persona_scores);
  const href = `/listings/${listing.id}${persona ? `?persona=${persona}` : badge ? `?persona=${badge.persona}` : ""}`;

  return (
    <Link
      href={href}
      className="group overflow-hidden rounded-xl border border-border bg-surface transition-shadow hover:shadow-lg"
    >
      <div className="relative aspect-[4/3] bg-border">
        {listing.cover_photo && (
          <Image
            src={listing.cover_photo}
            alt={listing.address ?? "Listing photo"}
            fill
            loading={eager ? "eager" : "lazy"}
            fetchPriority={eager ? "high" : "auto"}
            sizes="(min-width: 1280px) 25vw, (min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
            className="object-cover transition-transform duration-300 group-hover:scale-[1.02]"
          />
        )}
        {listing.building_type && (
          <span className="absolute left-3 top-3 rounded-full bg-surface/90 px-2.5 py-1 text-xs font-medium backdrop-blur">
            {listing.building_type}
          </span>
        )}
        {badge && (
          <span
            className="absolute right-3 top-3 rounded-full bg-foreground/90 px-2.5 py-1 text-xs font-medium tabular-nums text-background backdrop-blur"
            title={`${PERSONA_LABELS[badge.persona]} fit, from the house profile`}
          >
            {PERSONA_LABELS[badge.persona]} {badge.score}/10
          </span>
        )}
      </div>
      <div className="space-y-1 p-4">
        <p className="text-lg font-semibold tabular-nums">{formatPrice(listing.price)}</p>
        <p className="text-sm tabular-nums">{facts.join(" · ")}</p>
        <p className="truncate text-sm text-muted">
          {listing.address}
          {listing.community ? `, ${listing.community}` : ""}
        </p>
        {listing.investment && listing.investment.potential.length > 0 && (
          <div className="pt-1">
            <PotentialChips potential={listing.investment.potential} max={3} />
          </div>
        )}
      </div>
    </Link>
  );
}
