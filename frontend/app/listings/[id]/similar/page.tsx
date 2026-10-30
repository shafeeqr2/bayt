import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { getListing, type PersonaKey } from "@/lib/api";
import { defaultPersona, getSessionState } from "@/lib/session";
import { PersonaNote } from "../../../persona-note";
import { ArrowLeftIcon } from "../../../icons";
import { Help } from "../../../ui";
import { SimilarPanel } from "../similar-row";
import { WHO, parseSteer, personaGiven, similarHref } from "../steer";

export async function generateMetadata({ params }: PageProps<"/listings/[id]/similar">): Promise<Metadata> {
  const { id } = await params;
  const listing = await getListing(id);
  return { title: listing?.address ? `More like ${listing.address}` : "More like this" };
}

/** "More like this": the similar-homes search for one house, steered by the buyer. */
export default async function SimilarPage({ params, searchParams }: PageProps<"/listings/[id]/similar">) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  const [listing, state] = await Promise.all([getListing(id), getSessionState()]);
  if (!listing) notFound();
  const guessed = personaGiven(query) ? null : defaultPersona(state);
  const steer = parseSteer(query, guessed ?? "first_time_buyer");
  const withPersona = (p: PersonaKey) => similarHref(listing.id, { ...steer, persona: p });

  return (
    <div className="space-y-8 pt-6">
      <div className="space-y-4">
        <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm text-muted">
          <Link href={`/listings/${listing.id}`} className="flex items-center gap-1.5 transition-colors hover:text-foreground">
            <ArrowLeftIcon className="size-4" />
            {listing.address ?? "The house"}
          </Link>
        </nav>
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">AI picks for {WHO[steer.persona]}</p>
          <h1 className="display text-3xl font-semibold sm:text-4xl">More like this</h1>
          <div className="max-w-2xl text-sm text-muted">
            Homes in the same price band within 5 km, ranked by what matters to {WHO[steer.persona]}.{" "}
            <Help>
              Each listing has an AI profile with a pitch per buyer. The matches are the listings whose pitch is closest to
              this one, re-ranked and explained by the model. Type a change to move the search, and switch facets off to
              ignore them.
            </Help>
          </div>
          {guessed && <PersonaNote persona={guessed} href={withPersona} />}
        </div>
      </div>

      {/* One cached model call on the backend, so it streams in. */}
      <Suspense fallback={<Skeleton />}>
        <SimilarPanel listing={listing} steer={steer} />
      </Suspense>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-10">
      <div className="space-y-4">
        <div className="h-28 animate-pulse rounded-2xl bg-border" />
        <div className="h-24 animate-pulse rounded-xl bg-border" />
        <div className="h-48 animate-pulse rounded-2xl bg-border" />
      </div>
      <div className="space-y-3">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="h-36 animate-pulse rounded-2xl bg-border" />
        ))}
      </div>
    </div>
  );
}
