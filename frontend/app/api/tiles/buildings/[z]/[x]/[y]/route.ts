import { fetchBackend } from "@/lib/backend";

/** City building outline tiles for the 3D search map, streamed from the backend. */
export async function GET(_request: Request, { params }: RouteContext<"/api/tiles/buildings/[z]/[x]/[y]">) {
  const { z, x, y } = await params;
  try {
    const upstream = await fetchBackend(`/api/tiles/buildings/${z}/${x}/${y}`);
    if (upstream.status === 204) return new Response(null, { status: 204 });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: {
        "content-type": upstream.headers.get("content-type") ?? "application/vnd.mapbox-vector-tile",
        "cache-control": "public, max-age=86400",
      },
    });
  } catch (err) {
    return new Response(`Backend unreachable: ${err instanceof Error ? err.message : String(err)}`, { status: 502 });
  }
}
