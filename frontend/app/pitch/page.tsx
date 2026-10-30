import type { Metadata } from "next";
import Link from "next/link";

import { ArrowUpRightIcon, CheckIcon, SparklesIcon } from "../icons";
import { Chip, button, card } from "../ui";

export const metadata: Metadata = {
  title: "Why Bayt",
  description:
    "Search by taste, not by filters. Bayt reads every Toronto listing the way a buyer would, then finds the homes you would love and says why.",
};

const LIVE = "https://bayt.andalsolutions.com";
const REPO = "https://github.com/shafeeqr2/bayt";
const DEMO = `${LIVE}/listings/30365686/similar?persona=investor`;
const TEAM = ["Shareq Rabbani", "Shafeeq Rabbani", "Khaja Kamil"];

/* Everything the narrated video says is on this page too, in the same order: the problem,
   Taste Match built like the Netflix recommender, steering, Taste Profile, Precedent Check
   and Build Check, Floor Sketch, the models and why, the close. */

const STEPS: { n: string; title: string; body: string }[] = [
  { n: "1", title: "Read", body: "Nemotron 3.5 Super VL reads the listing text, the room list, up to 8 photos, and the City's lot and zoning data." },
  { n: "2", title: "Profile for 4 buyers", body: "It writes a House Profile: a pitch and a score from 1 to 10 for a first-time buyer, an investor, a flipper and a builder." },
  { n: "3", title: "Embed", body: "The pitches become 2,048-dimension vectors in pgvector. Price and location stay out of the vector, on purpose." },
  { n: "4", title: "Rerank with reasons", body: "Open a house: the 30 nearest pitches in its price band within 5 km light up, and Nemotron ranks the best 8 with 1 reason each." },
];

const PROFILE: { buyer: string; pitch: string; score: number }[] = [
  { buyer: "First-time buyer", pitch: "move-in ready, parking", score: 8 },
  { buyer: "Investor", pitch: "two rentable doors, 7% yield", score: 8 },
  { buyer: "Flipper", pitch: "dated kitchen, under median", score: 5 },
  { buyer: "Builder", pitch: "33 ft lot, multiplex zone", score: 6 },
];

const RANKED: { price: string; reason: string }[] = [
  { price: "$920,000", reason: "Finished basement apartment with second kitchen and separate entrance, two rentable doors now, 8.2% gross yield." },
  { price: "$939,900", reason: "Separate entrance, two rentable doors now, 7.6% gross yield, priced 28% below area median, as-of-right four units." },
  { price: "$839,900", reason: "Basement apartment with kitchen and separate entrance, 8.1% gross yield, garden suite likely." },
];

const BUILD_STEPS: { title: string; body: string }[] = [
  { title: "Your plan, in words", body: "“Keep the house and add a second storey, about 9 m high.” Nemotron reads it into an intent; a form holds the exact numbers when you have them." },
  { title: "The gaps", body: "A deterministic check against Zoning By-law 569-2013 for this lot: height, setbacks, coverage, units, the 4-unit rule since May 2023." },
  { title: "The routes and risks", body: "For each gap, the public route: a minor variance at the Committee of Adjustment, site plan, or rezoning, with the risk and time each one carries." },
  { title: "The cited answer", body: "Nemotron 3 Super writes the answer. Every citation is checked against the by-law clauses and the nearby Committee files; a citation it cannot back is dropped." },
];

const MODELS: { name: string; id: string; nvidia: boolean; jobs: string; why: string }[] = [
  {
    name: "Nemotron 3.5 Super VL",
    id: "nvidia/Nemotron-3.5-Super-VL",
    nvidia: true,
    jobs: "Reads text and up to 8 photos and writes the House Profile. Re-ranks the 30 nearest homes with 1 reason each. Rewrites the pitch for “Like this, but…”. Labels the photos.",
    why: "One vision-language model that follows a strict JSON schema and reads 8 photos in about 6 seconds. The whole catalogue, 2,261 homes, was profiled in 78 minutes for about $8.",
  },
  {
    name: "Nemotron 3 Super, 120B MoE",
    id: "nvidia/nemotron-3-super-120b-a12b",
    nvidia: true,
    jobs: "Writes the Build Check answer with citations. Completes the room list for Floor Sketch. Writes the Taste Profile.",
    why: "Strong reasoning over long by-law text at a low cost per token. Bayt runs it with thinking off, so even the cited zoning answer arrives in seconds.",
  },
  {
    name: "Qwen3-Embedding-8B",
    id: "Qwen/Qwen3-Embedding-8B",
    nvidia: false,
    jobs: "Turns every pitch into a 2,048-dimension vector for the pgvector search behind Taste Match.",
    why: "The one embedding model Token Factory serves today. A Nemotron embedder would be the first swap when one is listed.",
  },
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
          <h1 className="display text-4xl font-semibold leading-[1.05] sm:text-6xl">Search by taste, not by filters.</h1>
          <p className="mx-auto max-w-2xl text-lg text-muted sm:text-xl">
            Bayt reads every listing the way a buyer would, then finds the homes you would love and says why.
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
            <video controls preload="metadata" poster="/pitch/poster.jpg" src="/pitch/bayt.mp4" className="aspect-video w-full rounded-2xl bg-foreground">
              Your browser cannot play this video. Open the live site instead.
            </video>
          </div>
          <figcaption className="text-center text-sm text-muted">
            A narrated walkthrough of the live site: Taste Match, Taste Profile, Precedent Check, Build Check and Floor Sketch.
          </figcaption>
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
            Ask a realtor what they hear most:{" "}
            <span className="display text-2xl font-semibold text-accent">“I want a home similar to this one.”</span> Filters cannot
            answer that.
          </p>
          <p>
            Similar means different things to different people. The same bungalow is move-in ready to a first-time buyer, two
            rentable doors to an investor, a dated kitchen under the area median to a flipper, and a 33 ft lot in a multiplex zone
            to a builder.
          </p>
          <p className="font-medium">Bayt is live with 2,261 Toronto listings. Say who you are, and every tile carries a score for that buyer, because a model has already read each house.</p>
        </div>
      </section>

      {/* Taste Match: how it works */}
      <section className="space-y-10">
        <div className="max-w-2xl space-y-3">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">Taste Match · how it works</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">Built like the Netflix recommender</h2>
          <p className="text-lg text-muted">
            Netflix moved from counting clicks to a language model that reads what a title is about. Taste Match does the same for
            houses: a model reads what each house is about, and the match is made on meaning, not on filters.
          </p>
        </div>

        <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {STEPS.map((s, i) => (
            <li key={s.n} className={`${card} relative space-y-3 p-6`}>
              <span className="display flex size-10 items-center justify-center rounded-full bg-accent text-lg font-semibold text-accent-foreground">{s.n}</span>
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

        {/* The diagram from the video, as a still: one listing -> model -> House Profile -> vector space -> ranked list */}
        <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,4fr)_minmax(0,5fr)]">
          <div className={`${card} space-y-4 p-6`}>
            <p className="text-xs font-medium uppercase tracking-wider text-muted">One listing</p>
            <p className="text-sm text-muted">Text · room list · City lot and zoning data · 8 photos</p>
            <div className="grid grid-cols-4 gap-1.5">
              {Array.from({ length: 8 }, (_, i) => (
                <span key={i} className="aspect-[4/3] rounded bg-gradient-to-br from-accent/60 to-accent/25" />
              ))}
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-sm">
              <span className="font-semibold">Nemotron 3.5 Super VL</span>
              <NvidiaTag />
            </div>
            <p className="text-xs text-muted">Reads text and photos. Writes strict JSON. About 6 s per house, via Nebius Token Factory.</p>
          </div>

          <div className={`${card} space-y-3 p-6`}>
            <p className="text-xs font-medium uppercase tracking-wider text-muted">House Profile</p>
            <ul className="divide-y divide-border text-sm">
              {PROFILE.map((p) => (
                <li key={p.buyer} className="flex items-baseline justify-between gap-3 py-2.5">
                  <span>
                    <span className="font-medium">{p.buyer}</span> <span className="text-muted">· “{p.pitch}”</span>
                  </span>
                  <span className="display text-xl font-semibold tabular-nums">{p.score}</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted">4 pitches, 4 scores. Each pitch becomes a vector. No street, no neighbourhood, no price in the text.</p>
          </div>

          <div className={`${card} space-y-3 p-6`}>
            <p className="text-xs font-medium uppercase tracking-wider text-muted">Ranked for an investor</p>
            <VectorSpace />
            <ol className="space-y-2 text-sm">
              {RANKED.map((r, i) => (
                <li key={r.price} className="flex gap-3">
                  <span className="display flex size-6 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-semibold text-background">{i + 1}</span>
                  <span>
                    <span className="font-medium">{r.price}</span> <span className="text-muted">{r.reason}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <Stat value="2,261" label="live Toronto listings, every one profiled" />
          <Stat value="4" label="buyers per house: first-time, investor, flipper, builder" />
          <Stat value="8" label="matches per search, each with 1 reason" />
        </div>
      </section>

      {/* Steering and Taste Profile */}
      <section className="grid gap-10 lg:grid-cols-2 lg:gap-16">
        <div className="space-y-5">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">Taste Match, in use</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">Ranked for the buyer you are</h2>
          <p className="text-lg leading-relaxed text-muted">
            39 Rhydwen Avenue: one house, four scores, four reasons. Press <span className="font-medium text-foreground">More like this</span>. Eight
            homes ranked for an investor, each with a reason in plain words.
          </p>
          <div className={`${card} space-y-3 p-6`}>
            <p className="flex items-center gap-2 text-base font-semibold">
              <SparklesIcon className="size-5 text-accent" />
              Like this, but…
            </p>
            <p className="rounded-lg border border-border bg-background px-3 py-2.5 text-base text-muted">a bigger backyard and a garage</p>
            <p className="text-sm leading-relaxed text-muted">
              Say the change in words. Nemotron rewrites what you are looking for, the query moves in the vector space, the search runs
              again, and every reason answers the ask. Five facet chips choose what counts: layout, finish, lot, location, money.
            </p>
          </div>
          <a href={DEMO} className={button.secondary}>
            See it on 39 Rhydwen Avenue
            <ArrowUpRightIcon className="size-4" />
          </a>
        </div>
        <div className="space-y-5">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">Taste Profile</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">It learns your taste as you browse</h2>
          <p className="text-lg leading-relaxed text-muted">
            Save a few homes, dismiss a few. No login, one cookie. After 5 actions Nemotron sums up your taste, guesses the buyer you
            are, and makes it your default across the site.
          </p>
          <blockquote className={`${card} space-y-3 p-6`}>
            <p className="text-xs font-medium uppercase tracking-wider text-muted">A Taste Profile written during testing</p>
            <p className="text-lg leading-relaxed">
              “You keep saving homes with basement apartments that offer immediate rental income through a separate entrance and second kitchen.”
            </p>
            <div className="flex flex-wrap gap-2">
              <Chip tone="solid">Investor · 90% sure</Chip>
              <Chip>basement apartment with separate entrance</Chip>
              <Chip>second kitchen</Chip>
              <Chip>rent from two doors</Chip>
            </div>
          </blockquote>
        </div>
      </section>

      {/* Precedent Check and Build Check */}
      <section className="space-y-10">
        <div className="max-w-2xl space-y-3">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">Precedent Check · Build Check</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">See the precedent before you buy</h2>
          <p className="text-lg text-muted">
            Builders and investors need precedent. Precedent Check reads every Committee of Adjustment decision since 2001 within 500 m
            of the house: what neighbours asked for, and what the committee decided.
          </p>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className={`${card} space-y-4 p-6`}>
            <p className="text-xs font-medium uppercase tracking-wider text-muted">500 m around 39 Rhydwen Avenue</p>
            <PrecedentMap />
            <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
              <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-success" /> approved</li>
              <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-danger" /> refused</li>
              <li className="flex items-center gap-1.5"><span className="size-2.5 rounded-full bg-border" /> withdrawn or pending</li>
            </ul>
          </div>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat value="222" label="files since 2001" />
              <Stat value="188" label="approved" />
              <Stat value="9" label="refused" />
              <Stat value="95%" label="approval rate" />
            </div>
            <div className={`${card} space-y-2 p-6`}>
              <p className="font-semibold">Precedent, not a promise</p>
              <p className="text-sm leading-relaxed text-muted">
                The City publishes each decision and its description, not the variance table. So an approval nearby tells you what the
                committee has allowed on this street. It does not approve your plan. Bayt says so on every page.
              </p>
            </div>
            <div className={`${card} space-y-2 p-6`}>
              <p className="font-semibold">Lot and zoning, drawn to scale</p>
              <p className="text-sm leading-relaxed text-muted">
                Lot area, frontage, coverage against the cap, height limit, as-of-right units and garden suite potential from City of
                Toronto open data, in 2D and 3D, with the building permits on record.
              </p>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <h3 className="display text-2xl font-semibold">Build Check: from a plan in words to a cited answer</h3>
          <ol className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {BUILD_STEPS.map((s, i) => (
              <li key={s.title} className={`${card} space-y-2 p-6`}>
                <span className="display text-sm font-semibold text-accent">Step {i + 1}</span>
                <h4 className="font-semibold">{s.title}</h4>
                <p className="text-sm leading-relaxed text-muted">{s.body}</p>
              </li>
            ))}
          </ol>
          <div className="flex items-center gap-2 text-sm text-muted">
            <span className="font-semibold text-foreground">Nemotron 3 Super</span>
            <NvidiaTag />
            <span>writes the answer in seconds, citing the by-law clauses and the nearby files.</span>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Feature
            title="Floor Sketch"
            body="Listings rarely include a floor plan. Floor Sketch fits the listed rooms into the City's building outline, level by level, and Nemotron adds the rooms the description names but the table leaves out. A best guess, marked as one."
          />
          <Feature
            title="Photo labels"
            body="Nemotron 3.5 Super VL names what each photo shows, which room it is and on which floor. The labels feed Floor Sketch and the gallery."
          />
        </div>
      </section>

      {/* Models */}
      <section className="space-y-8">
        <div className="max-w-2xl space-y-3">
          <p className="text-xs font-medium uppercase tracking-wider text-accent">The models · all via Nebius Token Factory</p>
          <h2 className="display text-3xl font-semibold sm:text-4xl">Three models, one OpenAI-style API</h2>
          <p className="text-lg text-muted">
            Every call runs on Nebius Token Factory. Postgres holds it all: pgvector for the pitches, PostGIS for the lots and the
            Committee files.
          </p>
        </div>
        <div className={`${card} overflow-x-auto`}>
          <table className="w-full min-w-[48rem] text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-muted">
              <tr className="border-b border-border">
                <th className="px-5 py-3 font-medium">Model</th>
                <th className="px-5 py-3 font-medium">What it does in Bayt</th>
                <th className="px-5 py-3 font-medium">Why this model</th>
              </tr>
            </thead>
            <tbody>
              {MODELS.map((m) => (
                <tr key={m.id} className="border-b border-border align-top last:border-0">
                  <td className="px-5 py-4">
                    <p className="flex flex-wrap items-center gap-2 font-semibold">
                      {m.name}
                      {m.nvidia && <NvidiaTag />}
                    </p>
                    <p className="mt-1 font-mono text-xs text-muted">{m.id}</p>
                  </td>
                  <td className="px-5 py-4 leading-relaxed">{m.jobs}</td>
                  <td className="px-5 py-4 leading-relaxed text-muted">{m.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm text-muted">
          Thinking is on by default on Token Factory. Bayt turns it off with <code className="font-mono text-xs">chat_template_kwargs.enable_thinking</code> for
          every “write JSON from this material” call, which brought the profile call from a timeout to about 6 seconds.
        </p>
      </section>

      {/* Proof */}
      <section className="grid gap-4 sm:grid-cols-3">
        <Proof title="Live today" body="2,261 real listings, no login, answers in 1 to 6 seconds." />
        <Proof title="Open source" body="MIT licence. FastAPI, Postgres with PostGIS and pgvector, Next.js, Docker, push-to-deploy." />
        <Proof title="Tested" body="319 backend tests, none of them touching the network." />
      </section>

      {/* Close */}
      <section className="rounded-3xl bg-foreground px-6 py-14 text-center text-background sm:px-12">
        <p className="display mx-auto max-w-2xl text-3xl font-semibold leading-tight sm:text-5xl">Bayt. Search by taste.</p>
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
        <p className="mt-8 text-sm text-background/70">Built by {TEAM.join(", ")}.</p>
        <p className="mt-2 text-sm text-background/70">
          <Link href="/" className="underline-offset-4 hover:underline">
            Back to the search
          </Link>
        </p>
      </section>
    </div>
  );
}

function NvidiaTag() {
  return <span className="rounded bg-[#76b900] px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-[#161b18]">NVIDIA</span>;
}

/** A small deterministic generator, so the figures render the same on every request. */
function* lcg(seed: number) {
  let s = seed >>> 0;
  for (;;) {
    s = (s * 1664525 + 1013904223) >>> 0;
    yield s / 4294967296;
  }
}

/** The vector space from the video: pitches as dots, the query house, the 30 nearest inside the price-band ring. */
function VectorSpace() {
  const rnd = lcg(7);
  const next = () => rnd.next().value as number;
  const dots = Array.from({ length: 90 }, () => {
    const x = 10 + next() * 180;
    const y = 10 + next() * 100;
    const d = Math.hypot(x - 118, y - 62);
    return { x, y, near: d < 34 };
  });
  return (
    <svg viewBox="0 0 200 120" className="w-full rounded-lg bg-surface-2" role="img" aria-label="Pitches as points; the query house and its 30 nearest neighbours">
      <circle cx="118" cy="62" r="34" className="fill-accent/10 stroke-accent/40" strokeDasharray="3 2" strokeWidth="0.8" />
      {dots.map((p, i) => (
        <circle key={i} cx={p.x.toFixed(1)} cy={p.y.toFixed(1)} r={p.near ? 2.2 : 1.6} className={p.near ? "fill-accent" : "fill-muted/40"} />
      ))}
      <circle cx="118" cy="62" r="4" className="fill-foreground stroke-background" strokeWidth="1.2" />
      <text x="124" y="59" fontSize="6" className="fill-foreground">this house</text>
      <text x="12" y="114" fontSize="5.5" className="fill-muted">30 nearest pitches, same price band, within 5 km</text>
    </svg>
  );
}

/** The Precedent Check map from the video: a pin, the 500 m circle, 222 files coloured by outcome. */
function PrecedentMap() {
  const rnd = lcg(42);
  const next = () => rnd.next().value as number;
  const files: { x: number; y: number; tone: string; r: number }[] = [];
  const outcomes = [...Array(188).fill("fill-success"), ...Array(9).fill("fill-danger"), ...Array(25).fill("fill-border")];
  // Shuffle so the refused ones are spread out, then place each inside the circle.
  for (let i = outcomes.length - 1; i > 0; i--) {
    const j = Math.floor(next() * (i + 1));
    [outcomes[i], outcomes[j]] = [outcomes[j], outcomes[i]];
  }
  for (const tone of outcomes) {
    const a = next() * Math.PI * 2;
    const d = Math.sqrt(next()) * 86;
    files.push({ x: 100 + Math.cos(a) * d, y: 100 + Math.sin(a) * d, tone, r: tone === "fill-danger" ? 2.6 : 1.8 });
  }
  return (
    <svg viewBox="0 0 200 200" className="w-full rounded-lg bg-surface-2" role="img" aria-label="222 Committee of Adjustment files within 500 m, coloured by outcome">
      <g className="stroke-border" strokeWidth="0.5">
        {[50, 100, 150].map((v) => (
          <g key={v}>
            <line x1={v} y1="0" x2={v} y2="200" />
            <line x1="0" y1={v} x2="200" y2={v} />
          </g>
        ))}
      </g>
      <circle cx="100" cy="100" r="88" className="fill-accent/5 stroke-accent/50" strokeDasharray="3 2" strokeWidth="0.8" />
      {files.map((f, i) => (
        <circle key={i} cx={f.x.toFixed(1)} cy={f.y.toFixed(1)} r={f.r} className={f.tone} />
      ))}
      <g transform="translate(100 100)">
        <circle r="7" className="fill-accent" />
        <circle r="2.4" className="fill-background" />
      </g>
      <text x="100" y="12" textAnchor="middle" fontSize="6.5" className="fill-accent font-semibold">500 m radius</text>
    </svg>
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

