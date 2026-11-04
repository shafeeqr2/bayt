import { cookies } from "next/headers";

import { BACKEND_URL } from "@/lib/backend";
import { parseSid } from "@/lib/sid";

const SID_COOKIE = "bayt_sid";

/**
 * The plan in plain words (and any detail fields) -> the zoning analysis and a cited written answer.
 * The form in the browser posts here; the backend reads the text and calls the model.
 *
 * Only a visitor with a valid session cookie gets through (401 otherwise): the cookie is
 * signed and is only issued after the Turnstile check, so a script cannot make this server
 * spend on the model without first passing for a human in a browser.
 * The visitor's address goes along as X-Forwarded-For (Caddy set it from the connection),
 * so the backend's per-client spend cap counts the visitor, not this server.
 */
export async function POST(request: Request, { params }: RouteContext<"/api/listings/[id]/zoning/ask">) {
  const { id } = await params;
  if (!parseSid((await cookies()).get(SID_COOKIE)?.value)) {
    return Response.json({ error: "no session" }, { status: 401 });
  }
  const body = await request.text();
  const clientIp = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  try {
    const upstream = await fetch(`${BACKEND_URL}/api/listings/${encodeURIComponent(id)}/zoning/ask`, {
      method: "POST",
      headers: { "content-type": "application/json", ...(clientIp ? { "x-forwarded-for": clientIp } : {}) },
      body,
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "content-type": "application/json", "cache-control": "no-store" },
    });
  } catch (err) {
    return new Response(`Backend unreachable: ${err instanceof Error ? err.message : String(err)}`, { status: 502 });
  }
}
