import { fetchBackend } from "@/lib/backend";

/**
 * Pins for the search map. The map fetches these itself rather than receiving
 * them as page props, because all matches together are a few hundred KB.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const upstream = await fetchBackend(`/api/listings/map?${searchParams}`);
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": "application/json", "cache-control": "private, max-age=60" },
  });
}
