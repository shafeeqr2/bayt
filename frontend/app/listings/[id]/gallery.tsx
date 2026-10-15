"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

export function Gallery({ photos, alt }: { photos: string[]; alt: string }) {
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

  const arrowClass =
    "absolute top-1/2 -translate-y-1/2 flex size-10 items-center justify-center rounded-full bg-surface/90 text-lg shadow backdrop-blur hover:bg-surface";

  return (
    <div className="space-y-3">
      <div className="relative aspect-[3/2] overflow-hidden rounded-xl bg-border">
        <Image
          key={photos[index]}
          src={photos[index]}
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
      {count > 1 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {photos.map((src, i) => (
            <button
              key={src}
              type="button"
              aria-label={`Show photo ${i + 1}`}
              onClick={() => setIndex(i)}
              className={`relative aspect-[4/3] w-24 shrink-0 overflow-hidden rounded-md border-2 ${
                i === index ? "border-accent" : "border-transparent opacity-70 hover:opacity-100"
              }`}
            >
              <Image src={src} alt="" fill sizes="96px" className="object-cover" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
