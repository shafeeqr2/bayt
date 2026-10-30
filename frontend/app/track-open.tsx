"use client";

import { useEffect } from "react";

import type { PersonaKey } from "@/lib/api";

/** Posts one "open" event when a listing page mounts. `via` says how the visitor got here. */
export function TrackOpen({ id, via, persona }: { id: string; via: string | null; persona: PersonaKey }) {
  useEffect(() => {
    fetch("/api/session/events", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kind: "open", listing_id: id, via: via ?? "direct", persona }),
      keepalive: true,
    }).catch(() => {});
  }, [id, via, persona]);
  return null;
}
