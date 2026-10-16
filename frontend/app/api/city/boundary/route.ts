import { fetchBackend } from "@/lib/backend";

/** Toronto's limits as GeoJSON; 404 until city data is loaded. */
export async function GET() {
  try {
    const upstream = await fetchBackend("/api/city/boundary");
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "content-type": "application/geo+json", "cache-control": "public, max-age=86400" },
    });
  } catch (err) {
    return new Response(`Backend unreachable: ${err instanceof Error ? err.message : String(err)}`, { status: 502 });
  }
}
