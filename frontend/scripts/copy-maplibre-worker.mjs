// MapLibre runs its tile parsing in a web worker that it loads from a file next
// to its own bundle. Turbopack does not emit that file, so we serve it from
// public/ and point MapLibre at it (see app/listings/[id]/lot-scene.tsx). Copying
// at install time keeps the worker and the main bundle at the same version.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "node_modules", "maplibre-gl", "dist", "maplibre-gl-worker.mjs");
const dest = join(root, "public", "maplibre-gl-worker.mjs");
mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
