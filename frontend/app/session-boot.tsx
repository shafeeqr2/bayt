"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * Mounted only when there is no session cookie yet: asks the server to set one, then re-renders
 * the server components so a page that holds back the model call without a session (the similar
 * panel) gets its answer on the first visit too. A crawler runs no JavaScript, so it never gets here.
 */
export function SessionBoot() {
  const router = useRouter();
  useEffect(() => {
    fetch("/api/session", { method: "POST" })
      .then((res) => {
        if (res.ok) router.refresh();
      })
      .catch(() => {});
  }, [router]);
  return null;
}
