"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import type { PhotoFacts, PhotoLabel } from "@/lib/api";

type Photo = { high: string; medium: string };

const KIND_LABELS: Record<PhotoFacts["kind"], string> = {
  exterior_front: "Front",
  exterior_back: "Back",
  exterior_side: "Side",
  street: "Street",
  aerial: "From above",
  interior: "Inside",
  floor_plan: "Floor plan",
  other: "Other",
};

const LEVEL_LABELS = { basement: "Basement", main: "Main floor", second: "Second floor", third: "Third floor", unknown: "" } as const;

/** The photos with, when the listing's photos have been read, a title and one sentence about the house under each. */
export function Gallery({ photos, alt, labels = [] }: { photos: Photo[]; alt: string; labels?: PhotoLabel[] }) {
  const [index, setIndex] = useState(0);
  const count = photos.length;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight") setIndex((i) => (i + 1) % count);
      if (e.key === "ArrowLeft") setIndex((i) => (i - 1 + count) % count);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count]);

  if (count === 0) {
    return (
      <div className="flex aspect-[3/2] items-center justify-center rounded-xl bg-border text-muted">
        No photos
      </div>
    );
  }

  const label = labels[index]?.facts ?? null;
  const arrowClass =
    "absolute top-1/2 -translate-y-1/2 flex size-10 items-center justify-center rounded-full bg-surface/90 text-lg shadow backdrop-blur hover:bg-surface";

  return (
    <div className="space-y-3">
      <div className="relative aspect-[3/2] overflow-hidden rounded-xl bg-border">
        <Image
          key={photos[index].high}
          src={photos[index].high}
          alt={`${alt}, photo ${index + 1}`}
          fill
          loading="eager"
          fetchPriority="high"
          sizes="(min-width: 1024px) 60vw, 100vw"
          className="object-cover"
        />
        {count > 1 && (
          <>
            <button
              type="button"
              aria-label="Previous photo"
              onClick={() => setIndex((i) => (i - 1 + count) % count)}
              className={`${arrowClass} left-3`}
            >
              ‹
            </button>
            <button
              type="button"
              aria-label="Next photo"
              onClick={() => setIndex((i) => (i + 1) % count)}
              className={`${arrowClass} right-3`}
            >
              ›
            </button>
          </>
        )}
        <span className="absolute bottom-3 right-3 rounded-full bg-black/60 px-2.5 py-1 text-xs tabular-nums text-white">
          {index + 1} / {count}
        </span>
      </div>
      {label && (
        <div className="space-y-0.5" aria-live="polite">
          <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
            <span className="font-medium">{label.title}</span>
            <span className="text-xs text-muted">
              {[
                label.kind === "interior" ? null : KIND_LABELS[label.kind],
                label.room && label.room.toLowerCase() !== label.title.toLowerCase() ? label.room : null,
                label.kind === "interior" && label.level && label.level !== "unknown" ? LEVEL_LABELS[label.level] : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </p>
          <p className="text-sm text-muted">{label.caption}</p>
        </div>
      )}
      {count > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {photos.map((photo, i) => (
            <button
              key={photo.high}
              type="button"
              aria-label={`Show photo ${i + 1}`}
              onClick={() => setIndex(i)}
              className={`relative aspect-[4/3] w-24 shrink-0 overflow-hidden rounded-md border-2 ${
                i === index ? "border-accent" : "border-transparent opacity-70 hover:opacity-100"
              }`}
            >
              {/* The 256px "medium" photo, not "high": a thumbnail sharing the main image's URL
                  would make Next.js treat the main image as lazy-loaded. */}
              <Image src={photo.medium} alt="" fill sizes="96px" className="object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
