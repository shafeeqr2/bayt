import { randomBytes } from "node:crypto";

import { cookies } from "next/headers";

const SID_COOKIE = "bayt_sid";
const YEAR = 60 * 60 * 24 * 365;

/** Start a session: set the httpOnly session cookie when there is none. The browser never sees the id. */
export async function POST() {
  const jar = await cookies();
  if (!jar.get(SID_COOKIE)?.value) {
    jar.set(SID_COOKIE, randomBytes(16).toString("hex"), {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: YEAR,
    });
  }
  return new Response(null, { status: 204 });
}
