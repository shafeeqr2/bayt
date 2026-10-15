export default function Loading() {
  return (
    <div className="grid gap-8 pt-9 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="aspect-[3/2] animate-pulse rounded-xl bg-border" />
      <div className="space-y-3">
        <div className="h-9 w-1/2 animate-pulse rounded bg-border" />
        <div className="h-5 w-3/4 animate-pulse rounded bg-border" />
        <div className="h-48 animate-pulse rounded-xl bg-border" />
      </div>
    </div>
  );
}
