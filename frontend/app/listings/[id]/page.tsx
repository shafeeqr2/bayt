import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { getListing, getPhotoLabels } from "@/lib/api";
import { formatParking, formatPrice, formatSqft } from "@/lib/format";
import { CitySection } from "./city-section";
import { FloorPlanSection } from "./floor-plan";
import { Gallery } from "./gallery";
import { PotentialChips } from "../../potential-chips";

export default async function ListingPage({ params }: PageProps<"/listings/[id]">) {
  const { id } = await params;
  const [listing, photoLabels] = await Promise.all([getListing(id), getPhotoLabels(id)]);
  if (!listing) notFound();

  const bedrooms =
    listing.bedrooms_below
      ? // TRREB's "+1" is an extra room: usually a den in condos, a basement bedroom in houses.
        `${listing.bedrooms_above} + ${listing.bedrooms_below} (${listing.building_type === "Apartment" ? "den" : "basement or den"})`
      : listing.bedrooms_text;

  const facts: [string, string | number | null][] = [
    ["Bedrooms", bedrooms],
    ["Bathrooms", listing.bathrooms],
    ["Interior", formatSqft(listing.sqft_min, listing.sqft_max)],
    ["Type", listing.building_type],
    ["Ownership", listing.ownership_type],
    ["Storeys", listing.stories],
    ["Lot", listing.lot_size],
    ["Parking", formatParking(listing.parking_spaces, listing.parking_type)],
    ["Property tax", listing.tax_annual ? `${formatPrice(listing.tax_annual)} / yr` : null],
    [
      "Maintenance",
      listing.maintenance_fee_monthly ? `${formatPrice(listing.maintenance_fee_monthly)} / mo` : null,
    ],
    ["Cross streets", listing.cross_streets],
    ["MLS #", listing.mls_number],
  ];

  const potential = listing.investment?.potential ?? [];

  return (
    <div className="space-y-6">
      <Link href="/" className="inline-block text-sm text-muted hover:text-foreground">
        ← All homes
      </Link>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Gallery photos={listing.photos} alt={listing.address ?? "Listing"} labels={photoLabels?.photos} />

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

          {potential.length > 0 && (
            <section className="space-y-3 rounded-xl border border-border bg-surface p-5">
              <div className="space-y-2">
                <h2 className="text-sm font-semibold">Ways to add value</h2>
                <PotentialChips potential={potential} />
              </div>
              <ul className="space-y-1.5 text-sm">
                {potential.map((p) => (
                  <li key={p.key}>
                    <span className="font-medium">{p.label}.</span>{" "}
                    <span className="text-muted">{p.detail}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

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
        <section className="max-w-4xl space-y-2">
          <h2 className="text-lg font-semibold">About this home</h2>
          <p className="whitespace-pre-line leading-relaxed text-foreground/90">{listing.description}</p>
        </section>
      )}

      <div className="max-w-4xl">
        <Suspense fallback={<div className="h-64 animate-pulse rounded-xl bg-border" />}>
          <CitySection id={listing.id} />
        </Suspense>
      </div>

      {listing.rooms.length > 0 && (
        <div className="max-w-4xl">
          {/* Needs the lot analysis, which may call the city's GIS, so it streams in. */}
          <Suspense fallback={<div className="h-80 animate-pulse rounded-xl bg-border" />}>
            <FloorPlanSection id={listing.id} />
          </Suspense>
        </div>
      )}

      {listing.rooms.length > 0 && (
        <section className="max-w-4xl space-y-2">
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
