import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-3 py-24 text-center">
      <p className="text-sm font-medium text-accent">404</p>
      <h1 className="text-2xl font-semibold">This home isn&apos;t here</h1>
      <p className="max-w-sm text-muted">
        The listing may have been sold or taken off the market, or the link is wrong.
      </p>
      <Link
        href="/"
        className="mt-3 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-accent-foreground hover:opacity-90"
      >
        Browse homes
      </Link>
    </div>
  );
}
