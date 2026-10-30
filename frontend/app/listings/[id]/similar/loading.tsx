export default function Loading() {
  return (
    <div className="space-y-8 pt-6">
      <div className="space-y-3">
        <div className="h-4 w-40 animate-pulse rounded bg-border" />
        <div className="h-9 w-64 animate-pulse rounded bg-border" />
        <div className="h-4 w-96 max-w-full animate-pulse rounded bg-border" />
      </div>
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
    </div>
  );
}
