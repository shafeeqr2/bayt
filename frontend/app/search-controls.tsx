import Link from "next/link";

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
  const base = "px-3 py-1.5 text-sm transition-colors";
  const on = "bg-accent text-accent-foreground";
  const off = "text-muted hover:text-foreground";
  return (
    <nav className="flex overflow-hidden rounded-lg border border-border bg-surface" aria-label="View">
      <Link href={to("list")} className={`${base} ${mapView ? off : on}`} aria-current={mapView ? undefined : "page"}>
        List
      </Link>
      <Link href={to("map")} className={`${base} ${mapView ? on : off}`} aria-current={mapView ? "page" : undefined}>
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
  const linkClass = "rounded-lg border border-border bg-surface px-4 py-2 text-sm hover:border-accent";

  return (
    <nav className="flex items-center justify-center gap-3 pt-2" aria-label="Pagination">
      {page > 1 ? (
        <Link href={to(page - 1)} className={linkClass}>
          Previous
        </Link>
      ) : (
        <span className={`${linkClass} pointer-events-none opacity-40`}>Previous</span>
      )}
      <span className="text-sm tabular-nums text-muted">
        Page {page} of {pageCount}
      </span>
      {page < pageCount ? (
        <Link href={to(page + 1)} className={linkClass}>
          Next
        </Link>
      ) : (
        <span className={`${linkClass} pointer-events-none opacity-40`}>Next</span>
      )}
    </nav>
  );
}
