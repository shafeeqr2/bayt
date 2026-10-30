import Link from "next/link";

import { ChevronLeftIcon, ChevronRightIcon, ListIcon, MapIcon } from "./icons";
import { button } from "./ui";

/** Links that keep every current search parameter and change one thing: the view or the page. */

function href(basePath: string, params: URLSearchParams): string {
  const qs = params.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

export function ViewToggle({ basePath, params, mapView }: { basePath: string; params: URLSearchParams; mapView: boolean }) {
  const to = (view: "list" | "map") => {
    const next = new URLSearchParams(params);
    next.delete("page");
    if (view === "map") next.set("view", "map");
    else next.delete("view");
    return href(basePath, next);
  };
  const base = "inline-flex h-10 cursor-pointer items-center gap-1.5 px-3.5 text-sm font-medium transition-colors duration-200";
  const on = "bg-foreground text-background";
  const off = "text-muted hover:bg-surface-2 hover:text-foreground";
  return (
    <nav className="flex overflow-hidden rounded-lg border border-border bg-surface" aria-label="View">
      <Link href={to("list")} className={`${base} ${mapView ? off : on}`} aria-current={mapView ? undefined : "page"}>
        <ListIcon className="size-4" />
        List
      </Link>
      <Link href={to("map")} className={`${base} ${mapView ? on : off}`} aria-current={mapView ? "page" : undefined}>
        <MapIcon className="size-4" />
        Map
      </Link>
    </nav>
  );
}

export function Pagination({
  basePath,
  params,
  page,
  pageCount,
}: {
  basePath: string;
  params: URLSearchParams;
  page: number;
  pageCount: number;
}) {
  if (pageCount <= 1) return null;
  const to = (p: number) => {
    const next = new URLSearchParams(params);
    next.set("page", String(p));
    return href(basePath, next);
  };
  const disabled = `${button.secondary} pointer-events-none opacity-40`;

  return (
    <nav className="flex items-center justify-center gap-3 pt-4" aria-label="Pagination">
      {page > 1 ? (
        <Link href={to(page - 1)} className={button.secondary} rel="prev">
          <ChevronLeftIcon className="size-4" />
          Previous
        </Link>
      ) : (
        <span className={disabled} aria-disabled="true">
          <ChevronLeftIcon className="size-4" />
          Previous
        </span>
      )}
      <span className="px-2 text-sm tabular-nums text-muted">
        Page {page} of {pageCount}
      </span>
      {page < pageCount ? (
        <Link href={to(page + 1)} className={button.secondary} rel="next">
          Next
          <ChevronRightIcon className="size-4" />
        </Link>
      ) : (
        <span className={disabled} aria-disabled="true">
          Next
          <ChevronRightIcon className="size-4" />
        </span>
      )}
    </nav>
  );
}
