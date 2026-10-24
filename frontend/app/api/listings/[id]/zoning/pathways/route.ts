import { BACKEND_URL } from "@/lib/backend";

/**
 * Zoning gaps and playbook pathways for a proposal on this listing's lot.
 * The form in the browser posts the intent here; the backend does the analysis.
 */
export async function POST(request: Request, { params }: RouteContext<"/api/listings/[id]/zoning/pathways">) {
  const { id } = await params;
  const body = await request.text();
  try {
    const upstream = await fetch(`${BACKEND_URL}/api/listings/${encodeURIComponent(id)}/zoning/pathways`, {
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
