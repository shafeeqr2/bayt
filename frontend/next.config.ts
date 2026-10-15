import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
