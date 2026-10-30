import "server-only";

import { cookies } from "next/headers";

import { BACKEND_URL } from "./backend";
import { PERSONAS, type ListingSummary, type PersonaKey } from "./api";

/*
  Session taste (similar homes, phase 4). The visitor's session is a random id in an
  httpOnly cookie; the backend keeps the opens, saves and dismissals and, every 5
  actions, a taste summary with a persona guess. No login.
*/

export const SID_COOKIE = "bayt_sid";

export type Taste = {
  summary: string;
  persona: string | null;
  confidence: number | null;
  likes: string[];
  actions: number;
  /** The buyer to preselect; null below the backend's confidence threshold (0.7). */
  default_persona: string | null;
};

export type SessionState = { actions: number; saves: ListingSummary[]; taste: Taste | null };

/** The session id from the cookie, or null on a first visit (the client sets it after the first render). */
export async function getSid(): Promise<string | null> {
  const jar = await cookies();
  const value = jar.get(SID_COOKIE)?.value;
  return value && /^[A-Za-z0-9_-]{8,64}$/.test(value) ? value : null;
}

/** The saves and the taste for this visitor, or null without a session yet. Never calls the model. */
export async function getSessionState(): Promise<SessionState | null> {
  const sid = await getSid();
  if (!sid) return null;
  try {
    const res = await fetch(`${BACKEND_URL}/api/session/${encodeURIComponent(sid)}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as SessionState;
  } catch {
    return null;
  }
}

/** The buyer the taste summary points at, when the backend is sure enough. */
export function defaultPersona(state: SessionState | null): PersonaKey | null {
  const guess = state?.taste?.default_persona;
  return guess && PERSONAS.includes(guess as PersonaKey) ? (guess as PersonaKey) : null;
}
