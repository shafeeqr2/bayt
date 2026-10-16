import "server-only";

/** Where the FastAPI backend lives, as seen from the Next.js server. */
export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

/** Raw backend response, for route handlers that stream binary or large payloads to the browser. */
export async function fetchBackend(path: string): Promise<Response> {
  return fetch(`${BACKEND_URL}${path}`);
}
