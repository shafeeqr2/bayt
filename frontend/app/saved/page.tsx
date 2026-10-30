import type { Metadata } from "next";
import Link from "next/link";

import { PERSONA_LABELS, type PersonaKey } from "@/lib/api";
import { defaultPersona, getSessionState } from "@/lib/session";
import { HeartIcon, SparklesIcon } from "../icons";
import { ListingCard } from "../listing-card";
import { Chip, button, card } from "../ui";

export const metadata: Metadata = { title: "Saved homes" };

/** The homes this visitor saved, with what the AI makes of their taste so far. No login: the session cookie. */
export default async function SavedPage() {
  const state = await getSessionState();
  const saves = state?.saves ?? [];
  const taste = state?.taste ?? null;
  const persona = defaultPersona(state) ?? undefined;

  return (
    <div className="space-y-8 pt-8">
      <div className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wider text-accent">Your session</p>
        <h1 className="display text-3xl font-semibold sm:text-4xl">Saved homes</h1>
        <p className="text-sm text-muted">Saved on this device, no account needed. {state ? `${state.actions} actions so far.` : ""}</p>
      </div>

      {taste && (
        <section className={`${card} space-y-3 p-5`} aria-labelledby="taste">
          <h2 id="taste" className="flex items-center gap-2 text-base font-semibold">
            <SparklesIcon className="size-4 text-accent" />
            What you seem to like
          </h2>
          <p className="max-w-prose text-sm leading-relaxed">{taste.summary}</p>
          {taste.likes.length > 0 && (
            <ul className="flex flex-wrap gap-1.5" aria-label="Likes">
              {taste.likes.map((like) => (
                <li key={like}>
                  <Chip>{like}</Chip>
                </li>
              ))}
            </ul>
          )}
          {taste.persona && taste.confidence != null && (
            <p className="text-xs text-muted">
              Best fit: <span className="font-medium text-foreground">{PERSONA_LABELS[taste.persona as PersonaKey] ?? taste.persona}</span>,{" "}
              {Math.round(taste.confidence * 100)}% sure{persona ? ". Searches now default to this buyer." : "."}
            </p>
          )}
        </section>
      )}

      {saves.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border py-20 text-center">
          <HeartIcon className="mx-auto size-8 text-muted" />
          <p className="display mt-3 text-xl font-semibold">Nothing saved yet</p>
          <p className="mt-1 text-sm text-muted">Tap the heart on any home. After 5 actions the AI sums up your taste.</p>
          <Link href="/" className={`${button.primary} mt-5`}>
            Browse homes
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {saves.map((listing, i) => (
            <ListingCard key={listing.id} listing={listing} eager={i < 8} persona={persona} saved via="saved" />
          ))}
        </div>
      )}
    </div>
  );
}
