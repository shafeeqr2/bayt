import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Production: `next build` writes a self-contained server to .next/standalone,
  // which frontend/Dockerfile copies into the image. `next dev` ignores this.
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  images: {
    // Listing photos are served from REALTOR.ca's CDN.
    remotePatterns: [{ protocol: "https", hostname: "cdn.realtor.ca", pathname: "/listings/**" }],
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
