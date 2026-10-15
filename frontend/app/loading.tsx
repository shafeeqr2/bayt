export default function Loading() {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }, (_, i) => (
        <div key={i} className="overflow-hidden rounded-xl border border-border bg-surface">
          <div className="aspect-[4/3] animate-pulse bg-border" />
          <div className="space-y-2 p-4">
            <div className="h-5 w-1/2 animate-pulse rounded bg-border" />
            <div className="h-4 w-3/4 animate-pulse rounded bg-border" />
          </div>
        </div>
      ))}
    </div>
  );
}
