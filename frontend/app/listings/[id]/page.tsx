import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense, type ReactNode } from "react";

import { getListing, getPhotoLabels, PERSONA_LABELS, PERSONAS, type ListingDetail, type PersonaKey } from "@/lib/api";
import { defaultPersona, getSessionState } from "@/lib/session";
import { PersonaNote } from "../../persona-note";
import { DismissButton, SaveButton } from "../../save-buttons";
import { TrackOpen } from "../../track-open";
import { formatParking, formatPrice, formatSqft } from "@/lib/format";
import {
  ArrowLeftIcon,
  ArrowUpRightIcon,
  BathIcon,
  BedIcon,
  BuildingIcon,
  CarIcon,
  HomeIcon,
  LandIcon,
  RulerIcon,
  SparklesIcon,
} from "../../icons";
import { Chip, Disclosure, Fact, ScoreBar, button, card } from "../../ui";
import { CitySection } from "./city-section";
import { FloorPlanSection } from "./floor-plan";
import { Gallery } from "./gallery";
import { parseSteer, personaGiven, similarHref } from "./steer";

const SECTIONS: [string, string][] = [
  ["overview", "Overview"],
  ["lot", "Lot & zoning"],
  ["build", "Build"],
  ["layout", "Layout"],
  ["rooms", "Rooms"],
];

export default async function ListingPage({ params, searchParams }: PageProps<"/listings/[id]">) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const [listing, photoLabels, state] = await Promise.all([getListing(id), getPhotoLabels(id), getSessionState()]);
  if (!listing) notFound();
  // No buyer in the URL: the one the session's taste summary points at, when it is sure enough.
  const guessed = personaGiven(query) ? null : defaultPersona(state);
  const steer = parseSteer(query, guessed ?? "first_time_buyer");
  const persona = steer.persona;
  const via = typeof query.via === "string" ? query.via : null;
  const saved = state?.saves.some((s) => s.id === listing.id) ?? false;
  const withPersona = (p: PersonaKey) => `/listings/${listing.id}?persona=${p}`;

  const isApartment = listing.building_type === "Apartment";
  const bedrooms = listing.bedrooms_below
    ? // TRREB's "+1" is an extra room: usually a den in condos, a basement bedroom in houses.
      `${listing.bedrooms_above} + ${listing.bedrooms_below} (${isApartment ? "den" : "basement or den"})`
    : null;
  const parking = formatParking(listing.parking_spaces, listing.parking_type);

  const strip: { icon: ReactNode; label: string; value: string | null }[] = [
    { icon: <BedIcon className="size-5" />, label: "Bedrooms", value: listing.bedrooms_text ? `${listing.bedrooms_text.replace(/\s+/g, "")} bd` : null },
    { icon: <BathIcon className="size-5" />, label: "Bathrooms", value: listing.bathrooms != null ? `${listing.bathrooms} ba` : null },
    { icon: <RulerIcon className="size-5" />, label: "Interior", value: formatSqft(listing.sqft_min, listing.sqft_max) },
    { icon: <LandIcon className="size-5" />, label: "Lot", value: listing.lot_size },
    { icon: <CarIcon className="size-5" />, label: "Parking", value: parking },
    { icon: isApartment ? <BuildingIcon className="size-5" /> : <HomeIcon className="size-5" />, label: "Type", value: listing.building_type },
  ];

  const details: [string, string | number | null][] = [
    ["Bedrooms", bedrooms],
    ["Ownership", listing.ownership_type],
    ["Storeys", listing.stories],
    ["Property tax", listing.tax_annual ? `${formatPrice(listing.tax_annual)} / yr` : null],
    ["Maintenance", listing.maintenance_fee_monthly ? `${formatPrice(listing.maintenance_fee_monthly)} / mo` : null],
    ["Cross streets", listing.cross_streets],
    ["MLS #", listing.mls_number],
  ];

  const potential = listing.investment?.potential ?? [];
  const sections = SECTIONS.filter(([key]) => key !== "rooms" || listing.rooms.length > 0);

  return (
    <div className="space-y-10">
      <TrackOpen id={listing.id} via={via} persona={persona} />
      <nav
        className="sticky top-16 z-30 -mx-4 border-b border-border/80 bg-surface/85 px-4 backdrop-blur supports-[backdrop-filter]:bg-surface/70 sm:-mx-6 sm:px-6"
        aria-label="On this page"
      >
        <ul className="mx-auto flex max-w-7xl gap-1 overflow-x-auto py-2 text-sm">
          {sections.map(([key, label]) => (
            <li key={key} className="shrink-0">
              <a
                href={`#${key}`}
                className="block rounded-lg px-3 py-1.5 font-medium text-muted transition-colors duration-200 hover:bg-surface-2 hover:text-foreground"
              >
                {label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div id="overview" className="scroll-mt-28 space-y-6">
        <Breadcrumb listing={listing} />

        <Gallery photos={listing.photos} alt={listing.address ?? "Listing"} labels={photoLabels?.photos} />

        <div className="grid gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,4fr)] lg:gap-12">
          <div className="space-y-8">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="display text-4xl font-semibold sm:text-5xl">{formatPrice(listing.price)}</p>
                <div className="flex items-center gap-2">
                  <DismissButton id={listing.id} via={via ?? undefined} persona={persona} />
                  <SaveButton id={listing.id} saved={saved} via={via ?? undefined} persona={persona} />
                  <Link href={similarHref(listing.id, steer)} className={button.primary}>
                    <SparklesIcon className="size-4" />
                    More like this
                  </Link>
                </div>
              </div>
              {guessed && <PersonaNote persona={guessed} href={withPersona} />}
              <h1 className="text-xl font-medium">{listing.address}</h1>
              <p className="text-sm text-muted">{[listing.community, listing.city, listing.postal_code].filter(Boolean).join(", ")}</p>
            </div>

            <ul className="flex flex-wrap gap-x-7 gap-y-4" aria-label="Key facts">
              {strip
                .filter((f) => f.value)
                .map((f) => (
                  <li key={f.label} className="flex items-center gap-2.5">
                    <span className="flex size-9 items-center justify-center rounded-lg bg-surface-2 text-muted">{f.icon}</span>
                    <span>
                      <span className="block text-[11px] uppercase tracking-wide text-muted">{f.label}</span>
                      <span className="block font-medium tabular-nums">{f.value}</span>
                    </span>
                  </li>
                ))}
            </ul>

            {listing.description && <About text={listing.description} />}

            <section className="space-y-4" aria-labelledby="details">
              <h2 id="details" className="text-base font-semibold">
                Details
              </h2>
              <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm sm:grid-cols-3">
                {details
                  .filter(([, value]) => value != null && value !== "")
                  .map(([label, value]) => (
                    <Fact key={label} label={label} value={value} />
                  ))}
              </dl>
              {potential.length > 0 && (
                <div className="space-y-2 border-t border-border pt-4">
                  <h3 className="text-sm font-semibold">Ways to add value</h3>
                  <ul className="flex flex-wrap gap-1.5" aria-label="Ways to add value">
                    {potential.map((p) => (
                      <li key={p.key}>
                        <Chip title={p.detail}>{p.label}</Chip>
                      </li>
                    ))}
                  </ul>
                  <details className="text-sm">
                    <summary className="w-fit cursor-pointer text-accent hover:underline">What this is based on</summary>
                    <ul className="mt-2 max-w-prose space-y-1.5 text-muted">
                      {potential.map((p) => (
                        <li key={p.key}>
                          <span className="font-medium text-foreground">{p.label}.</span> {p.detail}
                        </li>
                      ))}
                    </ul>
                  </details>
                </div>
              )}
            </section>
          </div>

          <aside className="space-y-4 lg:sticky lg:top-28 lg:self-start">
            {listing.persona_scores && (
              <section className={`${card} space-y-3 p-5`} aria-labelledby="buyer-fit">
                <div className="space-y-1">
                  <h2 id="buyer-fit" className="text-base font-semibold">
                    Who this home suits
                  </h2>
                  <p className="text-sm text-muted">Scores from the AI house profile. Pick a buyer to see homes like this for them.</p>
                </div>
                <ul className="space-y-1.5">
                  {PERSONAS.map((key) => {
                    const score = listing.persona_scores?.[key];
                    if (score == null) return null;
                    const active = key === persona;
                    return (
                      <li key={key}>
                        <Link
                          href={similarHref(listing.id, { ...steer, persona: key })}
                          aria-current={active ? "true" : undefined}
                          className={`flex items-center justify-between gap-4 rounded-lg border px-3 py-2 text-sm transition-colors duration-200 ${
                            active ? "border-accent bg-accent-soft font-medium" : "border-transparent hover:bg-surface-2"
                          }`}
                        >
                          <span>{PERSONA_LABELS[key]}</span>
                          <ScoreBar score={score} />
                        </Link>
                      </li>
                    );
                  })}
                </ul>
                <Link href={similarHref(listing.id, steer)} className={`${button.primary} w-full`}>
                  <SparklesIcon className="size-4" />
                  More like this for {PERSONA_LABELS[persona].toLowerCase()}s
                </Link>
                {listing.url && (
                  <a href={listing.url} target="_blank" rel="noreferrer" className={`${button.secondary} w-full`}>
                    View on REALTOR.ca
                    <ArrowUpRightIcon className="size-4" />
                  </a>
                )}
              </section>
            )}
            {!listing.persona_scores && listing.url && (
              <a href={listing.url} target="_blank" rel="noreferrer" className={`${button.secondary} w-full`}>
                View on REALTOR.ca
                <ArrowUpRightIcon className="size-4" />
              </a>
            )}
          </aside>
        </div>
      </div>

      <Suspense fallback={<div className="h-64 animate-pulse rounded-xl bg-border" />}>
        <CitySection id={listing.id} />
      </Suspense>

      {listing.rooms.length > 0 && (
        // Needs the lot analysis, which may call the city's GIS, so it streams in.
        <Suspense fallback={<div className="h-80 animate-pulse rounded-xl bg-border" />}>
          <FloorPlanSection id={listing.id} />
        </Suspense>
      )}

      {listing.rooms.length > 0 && (
        <div id="rooms" className="scroll-mt-28">
          <Disclosure title="Rooms" count={listing.rooms.length} level={2}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-muted">
                  <tr className="border-b border-border">
                    <th className="px-5 py-2.5 font-medium">Room</th>
                    <th className="px-5 py-2.5 font-medium">Level</th>
                    <th className="px-5 py-2.5 font-medium">Size</th>
                  </tr>
                </thead>
                <tbody>
                  {listing.rooms.map((room, i) => (
                    <tr key={i} className="border-b border-border last:border-0">
                      <td className="px-5 py-2.5">{room.type}</td>
                      <td className="px-5 py-2.5 text-muted">{room.level}</td>
                      <td className="px-5 py-2.5 tabular-nums">{room.dimension}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Disclosure>
        </div>
      )}
    </div>
  );
}

function Breadcrumb({ listing }: { listing: ListingDetail }) {
  const crumbs = [
    { href: "/", label: "Buy" },
    listing.community
      ? { href: `/?q=${encodeURIComponent(listing.community)}`, label: listing.community }
      : listing.city
        ? { href: `/?city=${encodeURIComponent(listing.city)}`, label: listing.city }
        : null,
  ].filter((c): c is { href: string; label: string } => c != null);
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm text-muted">
      <Link href="/" className="flex items-center gap-1.5 transition-colors hover:text-foreground sm:hidden" aria-label="Back to all homes">
        <ArrowLeftIcon className="size-4" />
        Back
      </Link>
      <ol className="hidden items-center gap-2 sm:flex">
        {crumbs.map((c) => (
          <li key={c.href} className="flex items-center gap-2">
            <Link href={c.href} className="transition-colors hover:text-foreground">
              {c.label}
            </Link>
            <span aria-hidden="true">/</span>
          </li>
        ))}
        <li className="truncate text-foreground" aria-current="page">
          {listing.address}
        </li>
      </ol>
    </nav>
  );
}

const LONG = 420;

/** The listing text, clamped to a few lines; a native disclosure shows the rest with no JavaScript. */
function About({ text }: { text: string }) {
  const body = "whitespace-pre-line leading-relaxed text-foreground/90";
  return (
    <section className="max-w-prose space-y-2" aria-labelledby="about">
      <h2 id="about" className="text-base font-semibold">
        About this home
      </h2>
      {text.length <= LONG ? (
        <p className={body}>{text}</p>
      ) : (
        // The clamped copy sits outside the disclosure (a closed <details> hides its body);
        // :has() hides it once the full text is open.
        <div className="space-y-2 [&:has(details[open])>.clamped]:hidden">
          <p className={`clamped ${body} line-clamp-5`}>{text}</p>
          <details className="group">
            <summary className="w-fit cursor-pointer text-sm font-medium text-accent hover:underline">
              <span className="group-open:hidden">Read more</span>
              <span className="hidden group-open:inline">Read less</span>
            </summary>
            <p className={`${body} mt-2`}>{text}</p>
          </details>
        </div>
      )}
    </section>
  );
}
