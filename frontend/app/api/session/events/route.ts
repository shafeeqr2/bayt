import { cookies } from "next/headers";

import { BACKEND_URL } from "@/lib/backend";

const SID_COOKIE = "bayt_sid";

/** Forward one session event (open, save, unsave, dismiss) to the backend under the cookie's session id. */
export async function POST(request: Request) {
  const sid = (await cookies()).get(SID_COOKIE)?.value;
  if (!sid || !/^[A-Za-z0-9_-]{8,64}$/.test(sid)) return new Response(null, { status: 204 });
  const body = await request.text();
  const upstream = await fetch(`${BACKEND_URL}/api/session/${encodeURIComponent(sid)}/events`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  return new Response(upstream.body, { status: upstream.status, headers: { "content-type": "application/json" } });
}
