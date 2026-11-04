import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";

/*
  The session id and its signature.

  The cookie used to hold a bare random id, and the similar page spent a model call for
  any request that carried one. A crawler never sends the cookie, which was the point,
  but a script can: `curl -b bayt_sid=anything` was enough to make the server pay.

  Now the cookie is `<id>.<hmac>`. Only POST /api/session writes it, and only after the
  visitor passes the Turnstile check (lib/turnstile.ts), so a valid cookie means "a
  browser that Cloudflare took for a human sat behind this id at least once". Reading it
  back verifies the signature, so a made-up cookie is the same as no cookie.
*/

const ID = /^[A-Za-z0-9_-]{8,64}$/;

/** The signing key. SESSION_SECRET, else the Turnstile secret (already private), else none (development). */
const SECRET = process.env.SESSION_SECRET || process.env.TURNSTILE_SECRET_KEY || "";

if (!SECRET && process.env.NODE_ENV === "production") {
  console.warn("[bayt] SESSION_SECRET and TURNSTILE_SECRET_KEY are both unset: the session cookie is not signed");
}

function mac(id: string): string {
  return createHmac("sha256", SECRET).update(id).digest("base64url");
}

/** The cookie value for an id: signed when a secret is configured, bare otherwise. */
export function signSid(id: string): string {
  return SECRET ? `${id}.${mac(id)}` : id;
}

/** The id inside a cookie value, or null when the value is malformed or the signature is wrong. */
export function parseSid(value: string | undefined): string | null {
  if (!value) return null;
  const dot = value.indexOf(".");
  const id = dot === -1 ? value : value.slice(0, dot);
  if (!ID.test(id)) return null;
  if (!SECRET) return dot === -1 ? id : null;
  if (dot === -1) return null;
  const given = Buffer.from(value.slice(dot + 1));
  const want = Buffer.from(mac(id));
  return given.length === want.length && timingSafeEqual(given, want) ? id : null;
}

/** True when the cookie value is a bare, well-formed id from before cookies were signed. */
export function isLegacySid(value: string | undefined): value is string {
  return !!value && !value.includes(".") && ID.test(value);
}
