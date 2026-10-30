"use client";

import Image from "next/image";
import { useCallback, useEffect, useState } from "react";

import type { PhotoFacts, PhotoLabel } from "@/lib/api";
import { ChevronLeftIcon, ChevronRightIcon, ImagesIcon, XIcon } from "../../icons";

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

/**
 * The photos as a real-estate grid: 1 large and 4 small on wide screens, a single cover
 * with arrows on phones. Any photo opens the lightbox, where the photo labels (when the
 * listing's photos have been read) sit under the image.
 */
export function Gallery({ photos, alt, labels = [] }: { photos: Photo[]; alt: string; labels?: PhotoLabel[] }) {
  const [open, setOpen] = useState<number | null>(null);
  const [cover, setCover] = useState(0);
  const count = photos.length;

  if (count === 0) {
    return (
      <div className="flex aspect-[3/2] items-center justify-center rounded-2xl bg-border text-muted lg:aspect-[21/9]">
        No photos
      </div>
    );
  }

  const tiles = photos.slice(0, 5);
  const show = (i: number) => setOpen(i);

  return (
    <>
      {/* Wide screens: the grid. */}
      <div className="relative hidden h-[30rem] grid-cols-4 grid-rows-2 gap-2 overflow-hidden rounded-2xl lg:grid">
        {tiles.map((photo, i) => (
          <button
            key={photo.high}
            type="button"
            onClick={() => show(i)}
            aria-label={`Open photo ${i + 1} of ${count}`}
            className={`group relative cursor-pointer overflow-hidden bg-border ${i === 0 ? "col-span-2 row-span-2" : ""}`}
          >
            <Image
              src={photo.high}
              alt={`${alt}, photo ${i + 1}`}
              fill
              loading="eager"
              fetchPriority={i === 0 ? "high" : "auto"}
              sizes={i === 0 ? "(min-width: 1280px) 640px, 50vw" : "(min-width: 1280px) 320px, 25vw"}
              className="object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            />
          </button>
        ))}
        {tiles.length < 5 &&
          Array.from({ length: 5 - tiles.length }, (_, i) => <div key={i} className="bg-surface-2" />)}
        <button
          type="button"
          onClick={() => show(0)}
          className="absolute bottom-4 right-4 inline-flex h-10 cursor-pointer items-center gap-2 rounded-lg border border-border bg-white/90 px-4 text-sm font-medium text-[#161b18] shadow-card backdrop-blur transition-colors duration-200 hover:bg-white"
        >
          <ImagesIcon className="size-4" />
          Show all {count} photos
        </button>
      </div>

      {/* Phones and tablets: one cover with arrows. */}
      <div className="relative aspect-[3/2] overflow-hidden rounded-2xl bg-border lg:hidden">
        <button type="button" onClick={() => show(cover)} aria-label={`Open photo ${cover + 1} of ${count}`} className="absolute inset-0 cursor-pointer">
          <Image
            key={photos[cover].high}
            src={photos[cover].high}
            alt={`${alt}, photo ${cover + 1}`}
            fill
            loading="eager"
            fetchPriority="high"
            sizes="100vw"
            className="object-cover"
          />
        </button>
        {count > 1 && (
          <>
            <Arrow side="left" onClick={() => setCover((i) => (i - 1 + count) % count)} />
            <Arrow side="right" onClick={() => setCover((i) => (i + 1) % count)} />
          </>
        )}
        <span className="pointer-events-none absolute bottom-3 right-3 inline-flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-xs tabular-nums text-white">
          <ImagesIcon className="size-3.5" />
          {cover + 1} / {count}
        </span>
      </div>

      {open !== null && <Lightbox photos={photos} alt={alt} labels={labels} start={open} onClose={() => setOpen(null)} />}
    </>
  );
}

function Arrow({ side, onClick }: { side: "left" | "right"; onClick: () => void }) {
  const Icon = side === "left" ? ChevronLeftIcon : ChevronRightIcon;
  return (
    <button
      type="button"
      aria-label={side === "left" ? "Previous photo" : "Next photo"}
      onClick={onClick}
      className={`absolute top-1/2 flex size-10 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full bg-white/90 text-[#161b18] shadow-card backdrop-blur transition-colors duration-200 hover:bg-white ${
        side === "left" ? "left-3" : "right-3"
      }`}
    >
      <Icon className="size-5" />
    </button>
  );
}

function Lightbox({
  photos,
  alt,
  labels,
  start,
  onClose,
}: {
  photos: Photo[];
  alt: string;
  labels: PhotoLabel[];
  start: number;
  onClose: () => void;
}) {
  const count = photos.length;
  const [index, setIndex] = useState(start);
  const prev = useCallback(() => setIndex((i) => (i - 1 + count) % count), [count]);
  const next = useCallback(() => setIndex((i) => (i + 1) % count), [count]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") prev();
    }
    window.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [next, prev, onClose]);

  const label = labels[index]?.facts ?? null;

  return (
    <div role="dialog" aria-modal="true" aria-label="Photos" className="fixed inset-0 z-50 flex flex-col bg-black/95 text-white">
      <div className="flex items-center justify-between px-4 py-3 text-sm">
        <span className="tabular-nums text-white/80">
          {index + 1} / {count}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close photos"
          className="flex size-10 cursor-pointer items-center justify-center rounded-full transition-colors duration-200 hover:bg-white/10"
        >
          <XIcon className="size-5" />
        </button>
      </div>

      <div className="relative min-h-0 flex-1">
        <Image
          key={photos[index].high}
          src={photos[index].high}
          alt={`${alt}, photo ${index + 1}`}
          fill
          priority
          sizes="100vw"
          className="object-contain"
        />
        {count > 1 && (
          <>
            <button
              type="button"
              aria-label="Previous photo"
              onClick={prev}
              className="absolute left-3 top-1/2 flex size-11 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full bg-white/10 transition-colors duration-200 hover:bg-white/20"
            >
              <ChevronLeftIcon className="size-6" />
            </button>
            <button
              type="button"
              aria-label="Next photo"
              onClick={next}
              className="absolute right-3 top-1/2 flex size-11 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full bg-white/10 transition-colors duration-200 hover:bg-white/20"
            >
              <ChevronRightIcon className="size-6" />
            </button>
          </>
        )}
      </div>

      <div className="space-y-3 px-4 pb-4 pt-3">
        <div className="mx-auto min-h-10 max-w-3xl text-center" aria-live="polite">
          {label && (
            <>
              <p className="text-sm">
                <span className="font-medium">{label.title}</span>
                <span className="ml-2 text-xs text-white/60">
                  {[
                    label.kind === "interior" ? null : KIND_LABELS[label.kind],
                    label.room && label.room.toLowerCase() !== label.title.toLowerCase() ? label.room : null,
                    label.kind === "interior" && label.level && label.level !== "unknown" ? LEVEL_LABELS[label.level] : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </p>
              <p className="text-sm text-white/70">{label.caption}</p>
            </>
          )}
        </div>
        {count > 1 && (
          <div className="flex justify-center gap-2 overflow-x-auto pb-1">
            {photos.map((photo, i) => (
              <button
                key={photo.high}
                type="button"
                aria-label={`Show photo ${i + 1}`}
                onClick={() => setIndex(i)}
                className={`relative aspect-[4/3] w-20 shrink-0 cursor-pointer overflow-hidden rounded-md border-2 transition-opacity duration-200 ${
                  i === index ? "border-white" : "border-transparent opacity-60 hover:opacity-100"
                }`}
              >
                <Image src={photo.medium} alt="" fill sizes="80px" className="object-cover" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
