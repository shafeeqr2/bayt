export default function Loading() {
  return (
    <div className="space-y-8 pt-8">
      <div className="space-y-3">
        <div className="h-4 w-28 animate-pulse rounded bg-border" />
        <div className="h-9 w-56 animate-pulse rounded bg-border" />
      </div>
      <div className="h-32 animate-pulse rounded-2xl bg-border" />
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-80 animate-pulse rounded-2xl bg-border" />
        ))}
      </div>
    </div>
  );
}
