import { randomBytes } from "node:crypto";

import { cookies } from "next/headers";

import { isLegacySid, parseSid, signSid } from "@/lib/sid";
import { verifyTurnstile } from "@/lib/turnstile";

const SID_COOKIE = "bayt_sid";
const YEAR = 60 * 60 * 24 * 365;

/**
 * Start a session: set the signed httpOnly session cookie when there is no valid one.
 *
 * The body carries the Turnstile token the browser just earned (`{ "token": "..." }`). Only a
 * token Cloudflare accepts gets a cookie, and only a cookie gets a paid model call (the similar
 * rerank and the zoning answer), so a script without a browser is stopped here rather than at
 * the spend caps. The browser never sees the id.
 */
export async function POST(request: Request) {
  const jar = await cookies();
  const current = jar.get(SID_COOKIE)?.value;
  if (parseSid(current)) return new Response(null, { status: 204 });

  let token: string | undefined;
  try {
    token = ((await request.json()) as { token?: unknown }).token as string | undefined;
  } catch {
    token = undefined;
  }
  const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || null;
  if (!(await verifyTurnstile(typeof token === "string" ? token : undefined, ip))) {
    return Response.json({ error: "verification failed" }, { status: 403 });
  }

  // A visitor from before cookies were signed keeps their id, and with it their saves.
  const id = isLegacySid(current) ? current : randomBytes(16).toString("hex");
  jar.set(SID_COOKIE, signSid(id), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: YEAR,
  });
  return new Response(null, { status: 204 });
}
