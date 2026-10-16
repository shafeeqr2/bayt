"use client";

import dynamic from "next/dynamic";

/** MapLibre needs the DOM and WebGL, so the scene only loads in the browser. */
export const LotSceneLoader = dynamic(() => import("./lot-scene").then((m) => m.LotScene), {
  ssr: false,
  loading: () => <div className="h-96 w-full animate-pulse rounded-xl bg-border" />,
});
