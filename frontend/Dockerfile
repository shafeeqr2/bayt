# syntax=docker/dockerfile:1
# Production image for the Next.js frontend. Built by docker-compose.prod.yml.
#
# 3 stages: install dependencies, build, then copy only the standalone output
# (next.config.ts sets output: "standalone") into a small runtime image.
# BACKEND_URL is read at request time on the server (frontend/lib/backend.ts),
# so it is set when the container starts, not when the image is built.

FROM node:24-alpine AS base
WORKDIR /app
# Some native modules expect glibc symbols; this shim is the usual fix on Alpine.
RUN apk add --no-cache libc6-compat
ENV NEXT_TELEMETRY_DISABLED=1

FROM base AS deps
# postinstall runs scripts/copy-maplibre-worker.mjs, so the script must be present.
COPY package.json package-lock.json ./
COPY scripts ./scripts
RUN --mount=type=cache,target=/root/.npm npm ci

FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# public/maplibre-gl-worker.mjs is git-ignored; make sure it exists in the build.
RUN node scripts/copy-maplibre-worker.mjs && npm run build

FROM base AS runner
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
# The standalone build ships its own server.js; `next start` is not used with it.
CMD ["node", "server.js"]
