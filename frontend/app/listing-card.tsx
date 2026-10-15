import Image from "next/image";
import Link from "next/link";

import type { ListingSummary } from "@/lib/api";
import { bedsLabel, formatPrice, formatSqft } from "@/lib/format";

export function ListingCard({ listing, eager }: { listing: ListingSummary; eager: boolean }) {
  const facts = [
    bedsLabel(listing.bedrooms_text),
    listing.bathrooms != null ? `${listing.bathrooms} ba` : null,
    formatSqft(listing.sqft_min, listing.sqft_max),
  ].filter(Boolean);

  return (
    <Link
      href={`/listings/${listing.id}`}
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
      </div>
      <div className="space-y-1 p-4">
        <p className="text-lg font-semibold tabular-nums">{formatPrice(listing.price)}</p>
        <p className="text-sm tabular-nums">{facts.join(" · ")}</p>
        <p className="truncate text-sm text-muted">
          {listing.address}
          {listing.community ? `, ${listing.community}` : ""}
        </p>
      </div>
    </Link>
  );
}
