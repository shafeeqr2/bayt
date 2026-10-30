export default function Loading() {
  return (
    <div className="space-y-8 pt-8">
      <div className="space-y-4">
        <div className="h-10 w-80 max-w-full animate-pulse rounded-lg bg-border" />
        <div className="h-16 animate-pulse rounded-2xl bg-border" />
      </div>
      <div className="flex items-center justify-between">
        <div className="h-7 w-32 animate-pulse rounded bg-border" />
        <div className="h-10 w-40 animate-pulse rounded-lg bg-border" />
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="overflow-hidden rounded-2xl border border-border bg-surface">
            <div className="aspect-[4/3] animate-pulse bg-border" />
            <div className="space-y-2.5 p-4">
              <div className="h-6 w-1/2 animate-pulse rounded bg-border" />
              <div className="h-4 w-3/4 animate-pulse rounded bg-border" />
              <div className="h-4 w-2/3 animate-pulse rounded bg-border" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
