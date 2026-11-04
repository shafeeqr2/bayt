"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

/*
  Mounted only when there is no valid session cookie yet. Runs the Cloudflare Turnstile check,
  posts the token to /api/session, which sets the signed cookie, then re-renders the server
  components so a page that holds back the model call without a session (the similar panel)
  gets its answer on the first visit too.

  Turnstile is invisible for almost everyone ("interaction-only": the box at the bottom right
  only appears when Cloudflare wants a click). A crawler runs no JavaScript and never gets here;
  a script that does run a browser has to pass as a human first. With no site key (development)
  the post goes out without a token and the server accepts it.
*/

const SCRIPT = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";

type Turnstile = {
  render: (
    el: HTMLElement,
    opts: {
      sitekey: string;
      appearance?: "always" | "execute" | "interaction-only";
      callback?: (token: string) => void;
      "error-callback"?: () => void;
      "expired-callback"?: () => void;
    },
  ) => string | undefined;
  remove: (id: string) => void;
};

declare global {
  interface Window {
    turnstile?: Turnstile;
  }
}

/** The Turnstile API once its script has loaded (one script tag per page, however many callers). */
function loadTurnstile(): Promise<Turnstile> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  return new Promise((resolve, reject) => {
    let tag = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT}"]`);
    if (!tag) {
      tag = document.createElement("script");
      tag.src = SCRIPT;
      tag.async = true;
      tag.defer = true;
      document.head.appendChild(tag);
    }
    tag.addEventListener("load", () => (window.turnstile ? resolve(window.turnstile) : reject(new Error("turnstile missing"))));
    tag.addEventListener("error", () => reject(new Error("turnstile script failed")));
  });
}

export function SessionBoot({ siteKey }: { siteKey: string | null }) {
  const router = useRouter();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    let widget: string | undefined;

    const start = (token?: string) =>
      fetch("/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ token }),
      })
        .then((res) => {
          if (res.ok && !cancelled) router.refresh();
        })
        .catch(() => {});

    if (!siteKey) {
      start();
    } else {
      loadTurnstile()
        .then((turnstile) => {
          if (cancelled || !box.current) return;
          widget = turnstile.render(box.current, {
            sitekey: siteKey,
            appearance: "interaction-only",
            callback: (token) => void start(token),
          });
        })
        .catch(() => {});
    }

    return () => {
      cancelled = true;
      if (widget) window.turnstile?.remove(widget);
    };
  }, [router, siteKey]);

  // Empty unless Cloudflare asks the visitor for a click; then it is a 300 x 65 box.
  return <div ref={box} className="fixed bottom-4 right-4 z-50" />;
}
