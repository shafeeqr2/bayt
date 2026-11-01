import type { MetadataRoute } from "next";

/*
  Why this file exists. The site went public on 2026-10-30 without it. Anthropic's
  ClaudeBot then crawled every "More like this" URL (2,261 listings x 4 personas x
  facet subsets), and each render made 1 paid model call on the backend: 233,001
  calls in 43 hours, which drained the model balance. The similar pages and the API
  are off limits to every crawler, and the AI training crawlers are off the whole
  site. The paid call also no longer fires without a session cookie, so a crawler
  that ignores this file still spends nothing.
*/

const AI_CRAWLERS = [
  "ClaudeBot",
  "Claude-SearchBot",
  "Claude-User",
  "anthropic-ai",
  "GPTBot",
  "ChatGPT-User",
  "OAI-SearchBot",
  "CCBot",
  "Bytespider",
  "Amazonbot",
  "PerplexityBot",
  "meta-externalagent",
  "FacebookBot",
  "Google-Extended",
  "Applebot-Extended",
  "cohere-ai",
  "Diffbot",
  "AI2Bot",
  "ImagesiftBot",
  "omgili",
  "YouBot",
];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      { userAgent: AI_CRAWLERS, disallow: "/" },
      { userAgent: "*", disallow: ["/api/", "/listings/*/similar"], crawlDelay: 5 },
    ],
  };
}
