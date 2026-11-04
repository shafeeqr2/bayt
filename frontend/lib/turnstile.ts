import "server-only";

/*
  Cloudflare Turnstile, the "probably a human" check in front of the session cookie.

  The browser renders the widget (app/session-boot.tsx) and gets a one-time token; this
  module asks Cloudflare whether that token is good. A token is valid for 300 seconds and
  can be verified once. Without TURNSTILE_SECRET_KEY (development) every token passes, so
  `./start.sh` needs no Cloudflare account.
*/

const SECRET = process.env.TURNSTILE_SECRET_KEY || "";
const VERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

/** The site key the browser needs, or null when Turnstile is off. Safe to send to the client. */
export const TURNSTILE_SITE_KEY: string | null = SECRET ? process.env.TURNSTILE_SITE_KEY || null : null;

/** Whether Cloudflare accepts the token for this visitor. Fails closed on any error. */
export async function verifyTurnstile(token: string | undefined, remoteip: string | null): Promise<boolean> {
  if (!SECRET) return true;
  if (!token || token.length > 2048) return false;
  const form = new URLSearchParams({ secret: SECRET, response: token });
  if (remoteip) form.set("remoteip", remoteip);
  try {
    const res = await fetch(VERIFY, { method: "POST", body: form, signal: AbortSignal.timeout(5000) });
    if (!res.ok) return false;
    const data = (await res.json()) as { success?: boolean; hostname?: string };
    return data.success === true;
  } catch {
    return false;
  }
}
