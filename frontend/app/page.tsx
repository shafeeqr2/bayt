import Link from "next/link";

import { getFacets, getListings, PERSONA_LABELS, PERSONAS, type Facets, type PersonaKey } from "@/lib/api";
import { defaultPersona, getSessionState } from "@/lib/session";
import { HeartIcon, SearchIcon, SparklesIcon } from "./icons";
import { PersonaNote } from "./persona-note";
import { ListingCard } from "./listing-card";
import { MapSearchLoader } from "./map-search-loader";
import { Pagination, ViewToggle } from "./search-controls";

const PAGE_SIZE = 24;
const ABOVE_THE_FOLD = 8; // Two rows of four on wide screens.
const FILTER_KEYS = [
  "q",
  "city",
  "building_type",
  "min_price",
  "max_price",
  "min_beds",
  "min_baths",
  "sort",
  "persona",
  "potential",
  "view",
] as const;

type Filters = Partial<Record<(typeof FILTER_KEYS)[number], string>>;

export default async function Home({ searchParams }: PageProps<"/">) {
  const raw = await searchParams;
  const filters: Filters = {};
  for (const key of FILTER_KEYS) {
    const value = raw[key];
    if (typeof value === "string" && value !== "") filters[key] = value;
  }
  const page = Math.max(1, Number(raw.page) || 1);
  const mapView = filters.view === "map";
  const state = await getSessionState();
  const given = PERSONAS.includes(filters.persona as PersonaKey) ? (filters.persona as PersonaKey) : undefined;
  // No buyer in the URL: the one the session's taste summary points at, when it is sure enough.
  const guessed = given ? null : defaultPersona(state);
  const persona = given ?? guessed ?? undefined;
  if (persona) filters.persona = persona;
  else delete filters.persona;

  const apiFilters = Object.fromEntries(Object.entries(filters).filter(([key]) => key !== "view"));
  const query = new URLSearchParams(apiFilters);
  query.set("limit", String(PAGE_SIZE));
  query.set("offset", String((page - 1) * PAGE_SIZE));

  const [listings, facets] = await Promise.all([getListings(query), getFacets()]);
  const pageCount = Math.max(1, Math.ceil(listings.total / PAGE_SIZE));
  const params = new URLSearchParams(filters);
  const filtered = Object.keys(apiFilters).some((key) => key !== "sort");

  return (
    <div className="space-y-8">
      <Hero filters={filters} facets={facets} />

      {state?.taste && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-accent/30 bg-accent-soft/60 px-4 py-2.5 text-sm">
          <SparklesIcon className="size-4 shrink-0 text-accent" />
          <span className="min-w-0 flex-1">{state.taste.summary}</span>
          <Link href="/saved" className="inline-flex shrink-0 items-center gap-1 font-medium text-accent hover:underline">
            <HeartIcon className="size-3.5" />
            Saved ({state.saves.length})
          </Link>
        </p>
      )}
      {guessed && <PersonaNote persona={guessed} href={(p) => `/?${new URLSearchParams({ ...filters, persona: p })}`} />}

      <div className="flex flex-wrap items-center justify-between gap-4">
        <p className="text-sm text-muted">
          <span className="display text-2xl font-semibold text-foreground">{listings.total.toLocaleString("en-CA")}</span>{" "}
          {listings.total === 1 ? "home" : "homes"}
          {persona && (
            <>
              {" "}
              · scored for {article(persona)} <span className="font-medium text-foreground">{PERSONA_LABELS[persona].toLowerCase()}</span>
            </>
          )}
          {filtered && (
            <>
              {" "}
              ·{" "}
              <Link href="/" className="text-accent hover:underline">
                Clear filters
              </Link>
            </>
          )}
        </p>
        <ViewToggle basePath="/" params={params} mapView={mapView} />
      </div>

      {mapView ? (
        <MapSearchLoader query={new URLSearchParams(apiFilters).toString()} total={listings.total} />
      ) : listings.items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border py-24 text-center">
          <p className="display text-xl font-semibold">No homes match these filters</p>
          <p className="mt-1 text-sm text-muted">Widen the price range or clear a filter.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {listings.items.map((listing, i) => (
            <ListingCard key={listing.id} listing={listing} eager={i < ABOVE_THE_FOLD} persona={persona} />
          ))}
        </div>
      )}

      {!mapView && <Pagination basePath="/" params={params} page={page} pageCount={pageCount} />}
    </div>
  );
}

const article = (p: PersonaKey) => (p === "investor" ? "an" : "a");

/** The headline and the search bar: the bar is the call to action, so it carries the weight. */
function Hero({ filters, facets }: { filters: Filters; facets: Facets }) {
  return (
    <section className="space-y-6 pt-8 sm:pt-12">
      <div className="space-y-2">
        <h1 className="display text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">Find the right home in Toronto</h1>
        <p className="text-base text-muted sm:text-lg">Live listings, read and scored for the kind of buyer you are.</p>
      </div>
      <SearchForm filters={filters} facets={facets} />
    </section>
  );
}

// Inputs inside the bar have no border of their own; the bar draws the dividers.
const cell = "h-12 w-full min-w-0 bg-transparent px-4 text-sm outline-none placeholder:text-muted lg:h-14";
const selectCell = `${cell} cursor-pointer appearance-none pr-9 bg-[length:1rem] bg-[right_0.75rem_center] bg-no-repeat`;
const divider = "border-border max-lg:border-b lg:border-l";
// A chevron for the native selects (appearance-none drops the browser's).
const chevron = {
  backgroundImage:
    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%235b6661' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='m6 9 6 6 6-6'/></svg>\")",
};
const pill =
  "inline-flex h-10 cursor-pointer items-center justify-center rounded-full border px-3.5 text-sm font-medium transition-colors duration-200 has-checked:border-foreground has-checked:bg-foreground has-checked:text-background border-border bg-surface text-muted hover:border-foreground/40 hover:text-foreground";
const smallSelect =
  "h-10 cursor-pointer rounded-full border border-border bg-surface pl-3.5 pr-8 text-sm font-medium outline-none transition-colors duration-200 hover:border-foreground/40 focus:border-accent appearance-none bg-[length:1rem] bg-[right_0.6rem_center] bg-no-repeat";

function SearchForm({ filters, facets }: { filters: Filters; facets: Facets }) {
  return (
    <form action="/" method="get" className="space-y-4" role="search" aria-label="Search homes">
      {filters.view && <input type="hidden" name="view" value={filters.view} />}

      <div className="grid overflow-hidden rounded-2xl border border-border bg-surface shadow-float lg:grid-cols-[1.7fr_1fr_1fr_1.5fr_0.9fr_auto]">
        <label className={`flex items-center gap-2 pl-4 ${divider} lg:border-l-0`}>
          <SearchIcon className="size-5 shrink-0 text-muted" />
          <span className="sr-only">Address, area or MLS number</span>
          <input name="q" defaultValue={filters.q} placeholder="Address, area or MLS #" className={`${cell} pl-0`} />
        </label>
        <label className={`grid ${divider}`}>
          <span className="sr-only">City</span>
          <select name="city" defaultValue={filters.city ?? ""} className={selectCell} style={chevron}>
            <option value="">Any city</option>
            {facets.cities.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className={`grid ${divider}`}>
          <span className="sr-only">Home type</span>
          <select name="building_type" defaultValue={filters.building_type ?? ""} className={selectCell} style={chevron}>
            <option value="">Any type</option>
            {facets.building_types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <div className={`grid grid-cols-2 ${divider}`}>
          <label className="grid">
            <span className="sr-only">Minimum price</span>
            <input name="min_price" type="number" min={0} step={50000} inputMode="numeric" defaultValue={filters.min_price} placeholder="Min price" className={cell} />
          </label>
          <label className="grid border-l border-border">
            <span className="sr-only">Maximum price</span>
            <input name="max_price" type="number" min={0} step={50000} inputMode="numeric" defaultValue={filters.max_price} placeholder="Max price" className={cell} />
          </label>
        </div>
        <label className={`grid ${divider}`}>
          <span className="sr-only">Bedrooms</span>
          <select name="min_beds" defaultValue={filters.min_beds ?? ""} className={selectCell} style={chevron}>
            <option value="">Any beds</option>
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}+ beds
              </option>
            ))}
          </select>
        </label>
        <div className="p-2">
          <button
            type="submit"
            className="inline-flex h-11 w-full cursor-pointer items-center justify-center gap-2 rounded-xl bg-accent px-6 text-sm font-semibold text-accent-foreground transition-colors duration-200 hover:bg-accent/90 lg:h-10 lg:w-auto"
          >
            <SearchIcon className="size-4" strokeWidth={2.25} />
            Search
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="sr-only">I am a</legend>
          <span className="text-sm text-muted">I am</span>
          <label className={pill}>
            <input type="radio" name="persona" value="" defaultChecked={!filters.persona} className="sr-only" />
            any buyer
          </label>
          {PERSONAS.map((p) => (
            <label key={p} className={pill}>
              <input type="radio" name="persona" value={p} defaultChecked={filters.persona === p} className="sr-only" />
              {article(p)} {PERSONA_LABELS[p].toLowerCase()}
            </label>
          ))}
        </fieldset>

        <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
          <label className="grid">
            <span className="sr-only">Bathrooms</span>
            <select name="min_baths" defaultValue={filters.min_baths ?? ""} className={smallSelect} style={chevron}>
              <option value="">Any baths</option>
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n}+ baths
                </option>
              ))}
            </select>
          </label>
          <label className="grid">
            <span className="sr-only">Sort</span>
            <select name="sort" defaultValue={filters.sort ?? "newest"} className={smallSelect} style={chevron}>
              <option value="newest">Newest</option>
              <option value="price_asc">Price: low to high</option>
              <option value="price_desc">Price: high to low</option>
              <option value="fit">Best fit</option>
            </select>
          </label>
          <button
            type="submit"
            className="inline-flex h-10 cursor-pointer items-center rounded-full px-3.5 text-sm font-medium text-accent transition-colors duration-200 hover:bg-accent-soft"
          >
            Apply
          </button>
        </div>
      </div>
    </form>
  );
}
