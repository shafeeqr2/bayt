export default function Loading() {
  const block = "animate-pulse rounded-xl bg-border";
  return (
    <div className="space-y-6 pt-6">
      <div className={`${block} h-4 w-64`} />
      <div className="hidden h-[30rem] grid-cols-4 grid-rows-2 gap-2 overflow-hidden rounded-2xl lg:grid">
        <div className="col-span-2 row-span-2 animate-pulse bg-border" />
        <div className="animate-pulse bg-border" />
        <div className="animate-pulse bg-border" />
        <div className="animate-pulse bg-border" />
        <div className="animate-pulse bg-border" />
      </div>
      <div className={`${block} aspect-[3/2] rounded-2xl lg:hidden`} />
      <div className="grid gap-8 lg:grid-cols-[minmax(0,7fr)_minmax(0,4fr)]">
        <div className="space-y-4">
          <div className={`${block} h-10 w-56`} />
          <div className={`${block} h-6 w-80`} />
          <div className={`${block} h-4 w-64`} />
          <div className={`${block} h-16 w-full`} />
          <div className={`${block} h-32 w-full`} />
        </div>
        <div className="space-y-4">
          <div className={`${block} h-56 w-full`} />
          <div className={`${block} h-64 w-full`} />
        </div>
      </div>
    </div>
  );
}
