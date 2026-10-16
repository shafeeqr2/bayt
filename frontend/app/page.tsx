import Link from "next/link";

import { getFacets, getListings, type Facets } from "@/lib/api";
import { ListingCard } from "./listing-card";
import { MapSearchLoader } from "./map-search-loader";

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

  const apiFilters = Object.fromEntries(Object.entries(filters).filter(([key]) => key !== "view"));
  const query = new URLSearchParams(apiFilters);
  query.set("limit", String(PAGE_SIZE));
  query.set("offset", String((page - 1) * PAGE_SIZE));

  const [listings, facets] = await Promise.all([getListings(query), getFacets()]);
  const pageCount = Math.max(1, Math.ceil(listings.total / PAGE_SIZE));

  return (
    <div className="space-y-6">
      <FilterBar filters={filters} facets={facets} />

      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-muted">
          {listings.total.toLocaleString("en-CA")} {listings.total === 1 ? "home" : "homes"}
        </p>
        <ViewToggle filters={filters} mapView={mapView} />
      </div>

      {mapView ? (
        <MapSearchLoader query={new URLSearchParams(apiFilters).toString()} total={listings.total} />
      ) : listings.items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border py-20 text-center text-muted">
          No homes match these filters.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {listings.items.map((listing, i) => (
            <ListingCard key={listing.id} listing={listing} eager={i < ABOVE_THE_FOLD} />
          ))}
        </div>
      )}

      {!mapView && <Pagination filters={filters} page={page} pageCount={pageCount} />}
    </div>
  );
}

function ViewToggle({ filters, mapView }: { filters: Filters; mapView: boolean }) {
  const href = (view: "list" | "map") => {
    const params = new URLSearchParams(filters);
    if (view === "map") params.set("view", "map");
    else params.delete("view");
    const qs = params.toString();
    return qs ? `/?${qs}` : "/";
  };
  const base = "px-3 py-1.5 text-sm transition-colors";
  const on = "bg-accent text-accent-foreground";
  const off = "text-muted hover:text-foreground";
  return (
    <nav className="flex overflow-hidden rounded-lg border border-border bg-surface" aria-label="View">
      <Link href={href("list")} className={`${base} ${mapView ? off : on}`} aria-current={mapView ? undefined : "page"}>
        List
      </Link>
      <Link href={href("map")} className={`${base} ${mapView ? on : off}`} aria-current={mapView ? "page" : undefined}>
        Map
      </Link>
    </nav>
  );
}

const inputClass =
  "h-10 w-full rounded-lg border border-border bg-surface px-3 text-sm outline-none focus:border-accent";

function FilterBar({ filters, facets }: { filters: Filters; facets: Facets }) {
  return (
    <form className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-surface p-4 md:grid-cols-4 lg:grid-cols-8">
      {filters.view && <input type="hidden" name="view" value={filters.view} />}
      <input
        name="q"
        defaultValue={filters.q}
        placeholder="Address, area or MLS #"
        aria-label="Search"
        className={`${inputClass} col-span-2`}
      />
      <select name="city" defaultValue={filters.city ?? ""} aria-label="City" className={inputClass}>
        <option value="">Any city</option>
        {facets.cities.map((c) => (
          <option key={c}>{c}</option>
        ))}
      </select>
      <select
        name="building_type"
        defaultValue={filters.building_type ?? ""}
        aria-label="Home type"
        className={inputClass}
      >
        <option value="">Any type</option>
        {facets.building_types.map((t) => (
          <option key={t}>{t}</option>
        ))}
      </select>
      <input
        name="min_price"
        type="number"
        min={0}
        step={50000}
        defaultValue={filters.min_price}
        placeholder="Min price"
        aria-label="Min price"
        className={inputClass}
      />
      <input
        name="max_price"
        type="number"
        min={0}
        step={50000}
        defaultValue={filters.max_price}
        placeholder="Max price"
        aria-label="Max price"
        className={inputClass}
      />
      <select name="min_beds" defaultValue={filters.min_beds ?? ""} aria-label="Bedrooms" className={inputClass}>
        <option value="">Any beds</option>
        {[1, 2, 3, 4, 5].map((n) => (
          <option key={n} value={n}>
            {n}+ beds
          </option>
        ))}
      </select>
      <select name="min_baths" defaultValue={filters.min_baths ?? ""} aria-label="Bathrooms" className={inputClass}>
        <option value="">Any baths</option>
        {[1, 2, 3, 4].map((n) => (
          <option key={n} value={n}>
            {n}+ baths
          </option>
        ))}
      </select>
      <select
        name="sort"
        defaultValue={filters.sort ?? "newest"}
        aria-label="Sort"
        className={`${inputClass} lg:col-span-2`}
      >
        <option value="newest">Newest</option>
        <option value="price_asc">Price: low to high</option>
        <option value="price_desc">Price: high to low</option>
      </select>
      <div className="col-span-1 flex justify-end gap-2 md:col-span-3 lg:col-span-6">
        <Link
          href="/"
          className="flex h-10 items-center rounded-lg px-4 text-sm text-muted hover:text-foreground"
        >
          Reset
        </Link>
        <button
          type="submit"
          className="h-10 rounded-lg bg-accent px-5 text-sm font-medium text-accent-foreground hover:opacity-90"
        >
          Search
        </button>
      </div>
    </form>
  );
}

function Pagination({ filters, page, pageCount }: { filters: Filters; page: number; pageCount: number }) {
  if (pageCount <= 1) return null;
  const href = (p: number) => `/?${new URLSearchParams({ ...filters, page: String(p) })}`;
  const linkClass = "rounded-lg border border-border bg-surface px-4 py-2 text-sm hover:border-accent";

  return (
    <nav className="flex items-center justify-center gap-3 pt-2" aria-label="Pagination">
      {page > 1 ? (
        <Link href={href(page - 1)} className={linkClass}>
          Previous
        </Link>
      ) : (
        <span className={`${linkClass} pointer-events-none opacity-40`}>Previous</span>
      )}
      <span className="text-sm tabular-nums text-muted">
        Page {page} of {pageCount}
      </span>
      {page < pageCount ? (
        <Link href={href(page + 1)} className={linkClass}>
          Next
        </Link>
      ) : (
        <span className={`${linkClass} pointer-events-none opacity-40`}>Next</span>
      )}
    </nav>
  );
}
