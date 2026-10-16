"use client";

import dynamic from "next/dynamic";

/** MapLibre needs the DOM and WebGL, so the search map only loads in the browser. */
export const MapSearchLoader = dynamic(() => import("./map-search").then((m) => m.MapSearch), {
  ssr: false,
  loading: () => <div className="h-[70vh] min-h-[28rem] w-full animate-pulse rounded-xl bg-border" />,
});
