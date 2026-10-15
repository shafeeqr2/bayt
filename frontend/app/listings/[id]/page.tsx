import Link from "next/link";
import { notFound } from "next/navigation";

import { getListing } from "@/lib/api";
import { formatPrice, formatSqft } from "@/lib/format";
import { Gallery } from "./gallery";

export default async function ListingPage({ params }: PageProps<"/listings/[id]">) {
  const { id } = await params;
  const listing = await getListing(id);
  if (!listing) notFound();

  const bedrooms =
    listing.bedrooms_below
      ? `${listing.bedrooms_above} + ${listing.bedrooms_below} below grade`
      : listing.bedrooms_text;

  const facts: [string, string | number | null][] = [
    ["Bedrooms", bedrooms],
    ["Bathrooms", listing.bathrooms],
    ["Interior", formatSqft(listing.sqft_min, listing.sqft_max)],
    ["Type", listing.building_type],
    ["Ownership", listing.ownership_type],
    ["Storeys", listing.stories],
    ["Lot", listing.lot_size],
    ["Parking", listing.parking_spaces],
    ["Property tax", listing.tax_annual ? `${formatPrice(listing.tax_annual)} / yr` : null],
    [
      "Maintenance",
      listing.maintenance_fee_monthly ? `${formatPrice(listing.maintenance_fee_monthly)} / mo` : null,
    ],
    ["Cross streets", listing.cross_streets],
    ["MLS #", listing.mls_number],
  ];

  return (
    <div className="space-y-6">
      <Link href="/" className="inline-block text-sm text-muted hover:text-foreground">
        ← All homes
      </Link>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Gallery photos={listing.photos.map((p) => p.high)} alt={listing.address ?? "Listing"} />

        <div className="space-y-6">
          <div className="space-y-1">
            <p className="text-3xl font-semibold tabular-nums">{formatPrice(listing.price)}</p>
            <h1 className="text-lg">{listing.address}</h1>
            <p className="text-sm text-muted">
              {[listing.community, listing.city, listing.postal_code].filter(Boolean).join(", ")}
            </p>
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 rounded-xl border border-border bg-surface p-5 text-sm">
            {facts
              .filter(([, value]) => value != null && value !== "")
              .map(([label, value]) => (
                <div key={label}>
                  <dt className="text-muted">{label}</dt>
                  <dd className="font-medium tabular-nums">{value}</dd>
                </div>
              ))}
          </dl>

          {listing.url && (
            <a
              href={listing.url}
              target="_blank"
              rel="noreferrer"
              className="inline-block text-sm text-accent hover:underline"
            >
              View on REALTOR.ca ↗
            </a>
          )}
        </div>
      </div>

      {listing.description && (
        <section className="max-w-3xl space-y-2">
          <h2 className="text-lg font-semibold">About this home</h2>
          <p className="whitespace-pre-line leading-relaxed text-foreground/90">{listing.description}</p>
        </section>
      )}

      {listing.rooms.length > 0 && (
        <section className="max-w-3xl space-y-2">
          <h2 className="text-lg font-semibold">Rooms</h2>
          <div className="overflow-x-auto rounded-xl border border-border bg-surface">
            <table className="w-full text-sm">
              <thead className="text-left text-muted">
                <tr className="border-b border-border">
                  <th className="px-4 py-2 font-medium">Room</th>
                  <th className="px-4 py-2 font-medium">Level</th>
                  <th className="px-4 py-2 font-medium">Size</th>
                </tr>
              </thead>
              <tbody>
                {listing.rooms.map((room, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td className="px-4 py-2">{room.type}</td>
                    <td className="px-4 py-2 text-muted">{room.level}</td>
                    <td className="px-4 py-2 tabular-nums">{room.dimension}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
