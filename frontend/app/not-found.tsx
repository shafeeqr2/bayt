import Link from "next/link";

import { HomeIcon } from "./icons";
import { button } from "./ui";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center gap-4 py-28 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
        <HomeIcon className="size-6" />
      </span>
      <p className="text-xs font-medium uppercase tracking-wider text-accent">404</p>
      <h1 className="display text-3xl font-semibold">This home isn&apos;t here</h1>
      <p className="max-w-sm text-sm text-muted">The listing may have sold or come off the market, or the link is wrong.</p>
      <Link href="/" className={`${button.primary} mt-2`}>
        Browse homes
      </Link>
    </div>
  );
}
