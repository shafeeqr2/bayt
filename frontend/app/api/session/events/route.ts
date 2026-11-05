import { cookies } from "next/headers";

import { BACKEND_URL } from "@/lib/backend";
import { parseSid } from "@/lib/sid";

const SID_COOKIE = "bayt_sid";

/**
 * Forward one session event (open, save, unsave, dismiss) to the backend under the cookie's session id.
 * The visitor's address goes along as X-Forwarded-For (Caddy set it from the connection), so the
 * backend's per-client spend cap counts the visitor for the taste summary call, not this server.
 */
export async function POST(request: Request) {
  const sid = parseSid((await cookies()).get(SID_COOKIE)?.value);
  if (!sid) return new Response(null, { status: 204 });
  const body = await request.text();
  const clientIp = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  const upstream = await fetch(`${BACKEND_URL}/api/session/${encodeURIComponent(sid)}/events`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(clientIp ? { "x-forwarded-for": clientIp } : {}) },
    body,
  });
  return new Response(upstream.body, { status: upstream.status, headers: { "content-type": "application/json" } });
}
