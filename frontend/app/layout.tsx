import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";

import { getSid } from "@/lib/session";
import "./globals.css";
import { HomeIcon } from "./icons";
import { SessionBoot } from "./session-boot";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  axes: ["opsz", "SOFT"],
});

export const metadata: Metadata = {
  title: { default: "Bayt · Toronto homes for sale", template: "%s · Bayt" },
  description: "Toronto home search that knows why you like a house. Every listing read by AI, scored for 4 kinds of buyer, with lot and zoning facts from the City.",
};

const NAV = [
  { href: "/", label: "Buy" },
  { href: "/?view=map", label: "Map" },
  { href: "/?persona=investor&sort=fit", label: "Investors" },
  { href: "/?persona=builder&sort=fit", label: "Builders" },
  { href: "/saved", label: "Saved" },
  { href: "/pitch", label: "Why Bayt" },
];

/** Reads the cookie inside a Suspense boundary (it is runtime data) and mounts the boot only on a first visit. */
async function SessionGate() {
  return (await getSid()) ? null : <SessionBoot />;
}

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <Suspense fallback={null}>
          <SessionGate />
        </Suspense>
        <header className="sticky top-0 z-40 border-b border-border/80 bg-surface/85 backdrop-blur supports-[backdrop-filter]:bg-surface/70">
          <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-4 sm:px-6">
            <Link href="/" className="flex items-center gap-2.5" aria-label="Bayt home">
              <span className="flex size-8 items-center justify-center rounded-lg bg-accent text-accent-foreground">
                <HomeIcon className="size-4.5" strokeWidth={2} />
              </span>
              <span className="display text-xl font-semibold tracking-tight">Bayt</span>
            </Link>
            <nav className="hidden items-center gap-1 sm:flex" aria-label="Primary">
              {NAV.map((item) => (
                <Link
                  key={item.label}
                  href={item.href}
                  className="rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors duration-200 hover:bg-surface-2 hover:text-foreground"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
            <span className="hidden items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-medium text-muted md:inline-flex">
              <span className="size-1.5 rounded-full bg-success" />
              Toronto, ON
            </span>
            <nav className="flex items-center gap-1 sm:hidden" aria-label="Primary">
              <Link href="/?view=map" className="rounded-lg px-3 py-2 text-sm font-medium text-muted">
                Map
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-16 sm:px-6">{children}</main>
        <footer className="border-t border-border bg-surface">
          <div className="mx-auto grid max-w-7xl gap-8 px-4 py-10 text-sm sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
            <div className="space-y-3">
              <p className="display text-lg font-semibold">Bayt</p>
              <p className="max-w-sm leading-relaxed text-muted">
                Toronto home search that explains itself. Every listing is read by AI and scored for 4 kinds of buyer,
                with lot, zoning and permit facts from City of Toronto open data.
              </p>
            </div>
            <div className="space-y-2">
              <p className="font-medium">Search</p>
              <ul className="space-y-1.5 text-muted">
                {NAV.map((item) => (
                  <li key={item.label}>
                    <Link href={item.href} className="transition-colors hover:text-foreground">
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
            <div className="space-y-2">
              <p className="font-medium">About the data</p>
              <ul className="space-y-1.5 text-muted">
                <li>Listings from the REALTOR.ca public feed.</li>
                <li>Lot, zoning and permits: City of Toronto open data.</li>
                <li>AI: NVIDIA Nemotron on Nebius Token Factory.</li>
              </ul>
            </div>
          </div>
          <div className="border-t border-border">
            <p className="mx-auto max-w-7xl px-4 py-4 text-xs text-muted sm:px-6">
              Scores, estimates and zoning notes are informational, not advice. Verify with the City and a licensed
              professional before you buy or build.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
