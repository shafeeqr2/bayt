import type { Metadata } from "next";
import Link from "next/link";

import { ArrowUpRightIcon, CheckIcon, SparklesIcon } from "../icons";
import { Chip, button, card } from "../ui";

export const metadata: Metadata = {
  title: "Why Bayt",
  description:
    "Real estate search powered by AI. Every Toronto listing read by NVIDIA Nemotron, scored for 4 kinds of buyer, and matched to homes like this.",
};

const LIVE = "https://bayt.andalsolutions.com";
const REPO = "https://github.com/shafeeqr2/bayt";
const DEMO = `${LIVE}/listings/30365686/similar?persona=investor`;

const STEPS: { n: string; title: string; body: string }[] = [
  { n: "1", title: "Read", body: "Nemotron reads the listing text, up to 8 photos, and the City's lot and zoning data." },
  { n: "2", title: "Profile for 4 buyers", body: "It writes a score from 1 to 10 and a pitch for a first-time buyer, an investor, a flipper and a builder." },
  { n: "3", title: "Embed", body: "The pitches become vectors in pgvector. Price and location stay out of the vector, on purpose." },
  { n: "4", title: "Rerank with reasons", body: "“More like this” takes the 30 nearest pitches and Nemotron ranks 8, with 1 reason each." },
];

const MODELS: [string, string][] = [
  ["House profile from text, data and photos", "nvidia/Nemotron-3.5-Super-VL"],
  ["Rerank of 30 nearest houses, 1 reason each", "nvidia/Nemotron-3.5-Super-VL"],
  ["“Like this, but…” rewrite of the pitch", "nvidia/Nemotron-3.5-Super-VL"],
  ["Photo labels", "nvidia/Nemotron-3.5-Super-VL"],
  ["Zoning answer with by-law citations", "nvidia/nemotron-3-super-120b-a12b"],
  ["Room completion for the floor plan", "nvidia/nemotron-3-super-120b-a12b"],
  ["Pitch embeddings, 2,048 dimensions", "Qwen/Qwen3-Embedding-8B"],
];

export default function PitchPage() {
  return (
    <div className="space-y-24 pb-8 pt-10 sm:space-y-32 sm:pt-16">
      {/* Hero */}
      <section className="space-y-10">
        <div className="mx-auto max-w-3xl space-y-6 text-center">
          <Chip tone="brand" className="mx-auto">
            <SparklesIcon className="size-3.5" />
            Nebius x NVIDIA Global AI Hackathon
          </Chip>
          <h1 className="display text-4xl font-semibold leading-[1.05] sm:text-6xl">Real estate search powered by AI</h1>
          <p className="mx-auto max-w-2xl text-lg text-muted sm:text-xl">
            Bayt reads every Toronto listing the way a buyer would. Then it finds the homes you would like, and says why.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <a href={LIVE} className={`${button.primary} h-12 px-6 text-base`}>
              Try it live
              <ArrowUpRightIcon className="size-4" />
            </a>
            <a href="#video" className={`${button.secondary} h-12 px-6 text-base`}>
              Watch the 3-minute video
            </a>
          </div>
        </div>

        <figure id="video" className="scroll-mt-28 space-y-3">
          <div className={`${card} overflow-hidden rounded-3xl p-2 shadow-float`}>
            <video
              controls
              preload="metadata"
              poster="/pitch/poster.jpg"
              src="/pitch/bayt.mp4"
              className="aspect-video w-full rounded-2xl bg-foreground"
            >
              Your browser cannot play this video. Open the live site instead.
            </video>
          </div>
          <figcaption className="text-center text-sm text-muted">A walkthrough of the live site: search, “More like this”, steering, lot and zoning, and the Committee of Adjustment pipeline.</figcaption>
        </figure>
      </section>

      {/* Problem */}
      <section className="grid gap-10 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-16">
        <div className="space-y-3">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">The problem</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">Taste is not a filter</h2>
        </div>
        <div className="space-y-5 text-lg leading-relaxed">
          <p>Every search site gives you price, beds and baths. Nobody shops that way.</p>
          <p>
            Buyers open a house they like and ask the one question every realtor hears most:{" "}
            <span className="display text-2xl font-semibold text-accent">“I want a home similar to this.”</span>
          </p>
          <p>
            Similar means different things to different people. The same bungalow is move-in ready to a first-time buyer,
            two rentable doors to an investor, a dated kitchen under the area median to a flipper, and a 33 ft lot in a
            multiplex zone to a builder.
          </p>
          <p className="font-medium">That is what Bayt fixes.</p>
        </div>
      </section>

      {/* How it works */}
      <section className="space-y-10">
        <div className="max-w-2xl space-y-3">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">How it works</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">Inspired by the Netflix recommender</h2>
          <p className="text-lg text-muted">
            Netflix moved from click data to a language model that reads what a title is about. Bayt does the same for
            houses, with the reasons written down and the buyer at the wheel.
          </p>
        </div>
        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.n} className={`${card} relative space-y-3 p-6`}>
              <span className="display flex size-10 items-center justify-center rounded-full bg-accent text-lg font-semibold text-accent-foreground">
                {s.n}
              </span>
              <h3 className="text-lg font-semibold">{s.title}</h3>
              <p className="text-sm leading-relaxed text-muted">{s.body}</p>
              {i < STEPS.length - 1 && (
                <svg aria-hidden="true" viewBox="0 0 24 24" className="absolute -right-4 top-1/2 hidden size-6 -translate-y-1/2 text-border xl:block" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M5 12h14M13 6l6 6-6 6" />
                </svg>
              )}
            </li>
          ))}
        </ol>
        <div className="grid gap-4 sm:grid-cols-3">
          <Stat value="2,261" label="live Toronto listings, every one profiled" />
          <Stat value="4" label="buyers per house: first-time, investor, flipper, builder" />
          <Stat value="8" label="matches per search, each with 1 reason" />
        </div>
      </section>

      {/* More like this and steering */}
      <section className="grid gap-10 lg:grid-cols-2 lg:gap-16">
        <div className="space-y-5">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">More like this</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">Ranked for the buyer you are</h2>
          <p className="text-lg leading-relaxed text-muted">
            Pick who you are. Bayt filters to the same price band within 5 km, finds the nearest pitches, and Nemotron
            ranks the best 8. Every match carries 1 line on why it fits you.
          </p>
          <a href={DEMO} className={button.secondary}>
            See it on 39 Rhydwen Avenue
            <ArrowUpRightIcon className="size-4" />
          </a>
        </div>
        <div className="space-y-4">
          <blockquote className={`${card} space-y-3 p-6`}>
            <p className="text-xs font-medium uppercase tracking-wider text-muted">A real reason line, investor view</p>
            <p className="text-lg leading-relaxed">
              “Finished basement apartment with second kitchen and separate entrance, two rentable doors now, 8.2% gross
              yield and 6.8% cap rate, no condo fees, as-of-right units.”
            </p>
          </blockquote>
          <div className={`${card} space-y-3 p-6`}>
            <p className="flex items-center gap-2 text-base font-semibold">
              <SparklesIcon className="size-5 text-accent" />
              Like this, but…
            </p>
            <p className="rounded-lg border border-border bg-background px-3 py-2.5 text-base text-muted">a bigger backyard and a garage</p>
            <p className="text-sm leading-relaxed text-muted">
              Type the change in words. Nemotron rewrites the pitch, the search runs again, and the reasons say how
              each house meets the ask. Facet chips choose what counts: layout, finish, lot, location, money.
            </p>
          </div>
        </div>
      </section>

      {/* Builders and investors */}
      <section className="space-y-10">
        <div className="max-w-2xl space-y-3">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">For builders and investors</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">See the precedent before you buy</h2>
          <p className="text-lg text-muted">Every house page reads the City of Toronto’s open data for that lot.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Feature title="Lot and zoning" body="Lot area, frontage, coverage against the cap, height limit, as-of-right units, garden suite potential. Drawn to scale, in 2D and 3D." />
          <Feature title="What could you build here?" body="Describe the plan in words. The answer checks it against By-law 569-2013 and cites the clauses and the routes." />
          <Feature
            title="Committee of Adjustment pipeline"
            body="Every decision since 2001 within 500 m: what neighbours asked for and what the committee said."
            proof={
              <div className="flex flex-wrap gap-2 pt-1">
                <Chip tone="neutral">222 files within 500 m</Chip>
                <Chip tone="success">188 approved</Chip>
                <Chip tone="danger">9 refused</Chip>
              </div>
            }
          />
          <Feature title="Possible floor plan" body="The listed rooms fitted into the City’s building outline. Nemotron adds the rooms the description names but the table leaves out." />
        </div>
      </section>

      {/* Stack */}
      <section className="space-y-8">
        <div className="max-w-2xl space-y-3">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">The AI stack</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">Every model call on Nebius Token Factory</h2>
          <p className="text-lg text-muted">
            NVIDIA Nemotron does the reading, the ranking, the steering and the zoning answers. The whole catalogue was
            profiled in 78 minutes for about $8.
          </p>
        </div>
        <div className={`${card} overflow-x-auto`}>
          <table className="w-full min-w-[36rem] text-sm">
            <thead className="text-left text-muted">
              <tr className="border-b border-border">
                <th className="px-5 py-3 font-medium">Job</th>
                <th className="px-5 py-3 font-medium">Model on Token Factory</th>
              </tr>
            </thead>
            <tbody>
              {MODELS.map(([job, model]) => (
                <tr key={job} className="border-b border-border last:border-0">
                  <td className="px-5 py-3">{job}</td>
                  <td className="px-5 py-3 font-mono text-xs text-muted">{model}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Proof */}
      <section className="grid gap-4 sm:grid-cols-3">
        <Proof title="Live today" body="2,261 real listings, no login, answers in 1 to 6 seconds." />
        <Proof title="Open source" body="MIT licence. FastAPI, Postgres with PostGIS and pgvector, Next.js, Docker." />
        <Proof title="Tested" body="More than 300 backend tests, none of them touching the network." />
      </section>

      {/* Close */}
      <section className="rounded-3xl bg-foreground px-6 py-14 text-center text-background sm:px-12">
        <p className="display mx-auto max-w-2xl text-3xl font-semibold leading-tight sm:text-5xl">House search that knows why you like a house.</p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <a href={LIVE} className="inline-flex h-12 cursor-pointer items-center gap-2 rounded-lg bg-background px-6 text-base font-medium text-foreground transition-opacity duration-200 hover:opacity-90">
            Try it live
            <ArrowUpRightIcon className="size-4" />
          </a>
          <a href={REPO} className="inline-flex h-12 cursor-pointer items-center gap-2 rounded-lg border border-background/30 px-6 text-base font-medium text-background transition-colors duration-200 hover:bg-background/10">
            GitHub repo
            <ArrowUpRightIcon className="size-4" />
          </a>
        </div>
        <p className="mt-6 text-sm text-background/70">
          <Link href="/" className="underline-offset-4 hover:underline">
            Back to the search
          </Link>
        </p>
      </section>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className={`${card} p-6`}>
      <p className="display text-4xl font-semibold text-accent">{value}</p>
      <p className="mt-1 text-sm text-muted">{label}</p>
    </div>
  );
}

function Feature({ title, body, proof }: { title: string; body: string; proof?: React.ReactNode }) {
  return (
    <div className={`${card} space-y-2 p-6`}>
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="text-sm leading-relaxed text-muted">{body}</p>
      {proof}
    </div>
  );
}

function Proof({ title, body }: { title: string; body: string }) {
  return (
    <div className={`${card} flex gap-3 p-5`}>
      <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
        <CheckIcon className="size-3.5" strokeWidth={2.5} />
      </span>
      <div>
        <p className="font-semibold">{title}</p>
        <p className="text-sm text-muted">{body}</p>
      </div>
    </div>
  );
}
