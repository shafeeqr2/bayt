import { BACKEND_URL } from "@/lib/backend";

/**
 * The plan in plain words (and any detail fields) -> the zoning analysis and a cited written answer.
 * The form in the browser posts here; the backend reads the text and calls the model.
 */
export async function POST(request: Request, { params }: RouteContext<"/api/listings/[id]/zoning/ask">) {
  const { id } = await params;
  const body = await request.text();
  try {
    const upstream = await fetch(`${BACKEND_URL}/api/listings/${encodeURIComponent(id)}/zoning/ask`, {
      method: "POST",
      headers: { "content-type": "application/json" },
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
