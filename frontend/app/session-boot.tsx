"use client";

import { useEffect } from "react";

/** Mounted only when there is no session cookie yet: asks the server to set one. */
export function SessionBoot() {
  useEffect(() => {
    fetch("/api/session", { method: "POST" }).catch(() => {});
  }, []);
  return null;
}
