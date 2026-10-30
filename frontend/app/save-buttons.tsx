"use client";

import { useState } from "react";

import type { PersonaKey } from "@/lib/api";
import { HeartIcon, XIcon } from "./icons";

const round =
  "z-10 inline-flex size-9 cursor-pointer items-center justify-center rounded-full border border-border bg-surface/95 shadow-card backdrop-blur transition-colors duration-200";

function post(kind: "save" | "unsave" | "dismiss", id: string, via: string | undefined, persona: PersonaKey | undefined) {
  fetch("/api/session/events", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ kind, listing_id: id, via, persona }),
    keepalive: true,
  }).catch(() => {});
}

/** The heart: save or unsave, optimistic. Sits above a tile's stretched link, so it stops the click. */
export function SaveButton({ id, saved = false, via, persona, className = "" }: { id: string; saved?: boolean; via?: string; persona?: PersonaKey; className?: string }) {
  const [on, setOn] = useState(saved);
  return (
    <button
      type="button"
      aria-pressed={on}
      aria-label={on ? "Saved. Click to remove" : "Save this home"}
      title={on ? "Saved" : "Save"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setOn(!on);
        post(on ? "unsave" : "save", id, via, persona);
      }}
      className={`${round} ${on ? "border-accent bg-accent text-accent-foreground hover:bg-accent/90" : "text-foreground hover:border-accent hover:text-accent"} ${className}`}
    >
      <HeartIcon className="size-4" fill={on ? "currentColor" : "none"} />
    </button>
  );
}

/** "Not for me": records a dismissal and fades the tile out. */
export function DismissButton({ id, via, persona, className = "" }: { id: string; via?: string; persona?: PersonaKey; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      aria-pressed={done}
      aria-label={done ? "Marked not for you" : "Not for me"}
      title={done ? "Not for you" : "Not for me"}
      disabled={done}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setDone(true);
        post("dismiss", id, via, persona);
        const tile = (e.currentTarget as HTMLElement).closest("[data-tile]") as HTMLElement | null;
        if (tile) tile.style.opacity = "0.45";
      }}
      className={`${round} text-muted hover:border-danger hover:text-danger disabled:cursor-default disabled:opacity-60 ${className}`}
    >
      <XIcon className="size-4" />
    </button>
  );
}
