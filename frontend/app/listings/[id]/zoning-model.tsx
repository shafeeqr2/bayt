"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import { GLOSSARY } from "@/lib/zoning-glossary";
import type { Gap, PathwayAnalysis } from "@/lib/zoning";

/**
 * The zoning check as a picture: a schematic lot (frontage by depth, street along the front), the
 * planned building as a box, the most the by-law allows as a translucent blue box, and 1 dimension
 * line per standard. Green fits, orange is short, grey dashed is unknown. Hover or tap a line for
 * the plain-words definition; the table and the model share the same active standard.
 *
 * The scene is SVG with an orthographic projection, so it has no WebGL and no library, works on a
 * phone, and prints. The 4 views are camera angles; drag to rotate between them.
 */

type Vec = [number, number, number]; // x across the frontage (m), y back from the street (m), z up (m)
type View = { yaw: number; pitch: number }; // degrees

export const VIEWS: Record<string, View> = {
  street: { yaw: 0, pitch: 14 },
  side: { yaw: 90, pitch: 12 },
  top: { yaw: 0, pitch: 90 },
  iso: { yaw: 38, pitch: 34 },
};
const VIEW_LABELS: [keyof typeof VIEWS, string][] = [
  ["street", "Street"],
  ["side", "Side"],
  ["top", "Top"],
  ["iso", "3D"],
];

const VIEW_W = 640;
const VIEW_H = 400;
const PAD = 44;

/** What the box is drawn from when a value is unknown; the line then shows "?" and the card says so. */
const FALLBACK = { front: 6, side: 1.2, height: 7, storeyHeight: 3 };

type Status = Gap["status"];

export type Measure = {
  standard: string;
  /** The segment drawn, in metres. A polygon measure (coverage, area) has 4 or more points. */
  points: Vec[];
  polygon?: boolean;
  status: Status;
  label: string;
  /** Where the label sits, in metres. */
  at: Vec;
  /** The value the box was drawn with when the plan gave none. */
  placeholder?: number;
};

export type Scene = {
  W: number;
  D: number;
  plan: { x0: number; x1: number; y0: number; y1: number; h: number };
  allowed: { x0: number; x1: number; y0: number; y1: number; h: number } | null;
  existing: { x0: number; x1: number; y0: number; y1: number } | null;
  measures: Measure[];
  /** Standards with no geometry: shown as badges under the scene. */
  badges: { standard: string; status: Status; label: string }[];
  approximate: boolean;
};

function fmt(value: number | null | undefined, unit: string): string {
  if (value == null) return "?";
  const text = Number.isInteger(value) ? String(value) : value.toFixed(unit === "x lot area" ? 2 : 1);
  if (unit === "%") return `${text}%`;
  if (unit === "x lot area") return `${text} FSI`;
  if (unit === "m2") return `${text} m²`;
  if (unit === "units" || unit === "storeys") return text;
  return `${text} ${unit}`;
}

/** Turn the analysis into boxes and lines. Pure, so it is easy to reason about. */
export function buildScene(a: PathwayAnalysis): Scene {
  const gap = new Map(a.gaps.map((g) => [g.standard, g]));
  const g = (id: string) => gap.get(id);
  const plan = (id: string) => g(id)?.proposed ?? null;
  const req = (id: string) => (g(id)?.required_status === "known" ? g(id)?.required ?? null : null);
  const ex = a.lot.existing;

  const W = a.lot.frontage_m ?? g("lot_frontage")?.existing ?? 12;
  const D = a.lot.depth_m ?? (a.lot.area_m2 > 0 ? a.lot.area_m2 / W : 30);

  // The planned building. The analysis already picked the plan value, the existing wall or a derived number.
  const front = plan("front_setback") ?? ex?.front_setback_m ?? req("front_setback") ?? FALLBACK.front;
  const exSideMin =
    ex?.side_setback_left_m != null && ex?.side_setback_right_m != null
      ? Math.min(ex.side_setback_left_m, ex.side_setback_right_m)
      : ex?.side_setback_left_m ?? ex?.side_setback_right_m ?? null;
  const sideMin = plan("side_setback") ?? exSideMin ?? req("side_setback") ?? FALLBACK.side;
  const sideOther = ex?.side_setback_right_m != null && ex?.side_setback_left_m != null
    ? Math.max(ex.side_setback_left_m, ex.side_setback_right_m)
    : sideMin;
  const rear = plan("rear_setback") ?? ex?.rear_setback_m ?? null;
  const length = plan("building_length") ?? ex?.building_length_m ?? null;
  const rearFallback = Math.max(7.5, 0.25 * D);
  const yRear = rear != null ? D - rear : length != null ? front + length : D - rearFallback;
  const h = plan("height") ?? ex?.height_m ?? FALLBACK.height;
  const x0 = Math.min(sideMin, W / 2 - 1);
  const x1 = Math.max(W - sideOther, x0 + 2);
  const y1 = Math.max(Math.min(yRear, D - 0.5), front + 2);
  const box = { x0, x1, y0: front, y1, h: Math.max(h, 2.5) };

  // The most the by-law allows: required setbacks, depth and length caps, height limit.
  const fReq = req("front_setback");
  const sReq = req("side_setback");
  const rReq = req("rear_setback");
  const dReq = req("building_depth");
  const lReq = req("building_length");
  const hReq = req("height");
  const rearCandidates = [
    rReq != null ? D - rReq : null,
    dReq != null ? (fReq ?? front) + dReq : null,
    lReq != null ? front + lReq : null,
  ].filter((v): v is number => v != null);
  const anyReq = [fReq, sReq, rReq, dReq, lReq, hReq].some((v) => v != null);
  const allowed = anyReq
    ? {
        x0: sReq ?? x0,
        x1: W - (sReq ?? W - x1),
        y0: fReq ?? front,
        y1: rearCandidates.length ? Math.min(...rearCandidates) : y1,
        h: hReq ?? box.h,
      }
    : null;

  const existing =
    ex && ex.front_setback_m != null && ex.rear_setback_m != null && ex.side_setback_left_m != null && ex.side_setback_right_m != null
      ? { x0: ex.side_setback_left_m, x1: W - ex.side_setback_right_m, y0: ex.front_setback_m, y1: D - ex.rear_setback_m }
      : null;

  const measures: Measure[] = [];
  const badges: Scene["badges"] = [];
  const push = (standard: string, points: Vec[], at: Vec, placeholder?: number, polygon = false) => {
    const row = g(standard);
    if (!row || row.status === "not_applicable") return;
    measures.push({
      standard,
      points,
      polygon,
      status: row.status,
      label: `${GLOSSARY[standard]?.name ?? row.label} ${row.proposed == null ? "?" : fmt(row.proposed, row.unit)}`,
      at,
      placeholder: row.proposed == null ? placeholder : undefined,
    });
  };

  push("lot_area", [[0, 0, 0], [W, 0, 0], [W, D, 0], [0, D, 0]], [W / 2, D - 1.2, 0], undefined, true);
  push("lot_coverage", [[x0, front, 0], [x1, front, 0], [x1, y1, 0], [x0, y1, 0]], [(x0 + x1) / 2, (front + y1) / 2, 0], undefined, true);
  push("lot_frontage", [[0, -1.6, 0], [W, -1.6, 0]], [W / 2, -2.6, 0]);
  push("front_setback", [[W * 0.28, 0, 0], [W * 0.28, front, 0]], [W * 0.28 - 0.6, front / 2, 0], plan("front_setback") == null ? front : undefined);
  push("rear_setback", [[W * 0.5, y1, 0], [W * 0.5, D, 0]], [W * 0.5 - 0.6, (y1 + D) / 2, 0], rear == null ? D - y1 : undefined);
  const ySide = front + (y1 - front) * 0.22;
  push("side_setback", [[0, ySide, 0], [x0, ySide, 0]], [x0 / 2, ySide, 0], plan("side_setback") == null ? x0 : undefined);
  push("building_length", [[x0, front, box.h], [x0, y1, box.h]], [x0 - 0.6, (front + y1) / 2, box.h + 0.4], length == null ? y1 - front : undefined);
  push("building_depth", [[W + 1.6, fReq ?? front, 0], [W + 1.6, y1, 0]], [W + 2.4, ((fReq ?? front) + y1) / 2, 0], plan("building_depth") == null ? y1 - (fReq ?? front) : undefined);
  push("height", [[x1 + 0.9, front - 0.9, 0], [x1 + 0.9, front - 0.9, box.h]], [x1 + 1.5, front - 0.9, box.h / 2], plan("height") == null ? box.h : undefined);

  for (const id of ["storeys", "fsi", "units"]) {
    const row = g(id);
    if (!row || row.status === "not_applicable") continue;
    badges.push({ standard: id, status: row.status, label: `${GLOSSARY[id]?.name ?? row.label} ${fmt(row.proposed, row.unit)}` });
  }

  return { W, D, plan: box, allowed, existing, measures, badges, approximate: a.lot.irregular || a.lot.frontage_m == null || a.lot.depth_m == null };
}

// -- projection ---------------------------------------------------------------

type Camera = { yaw: number; pitch: number; scale: number; cx: number; cy: number; ox: number; oy: number };

function rad(deg: number) {
  return (deg * Math.PI) / 180;
}

/** Orthographic: rotate about z by yaw, tilt by pitch (0 = from the street at eye level, 90 = from above). */
function project([x, y, z]: Vec, c: Camera): [number, number, number] {
  const a = rad(c.yaw);
  const p = rad(c.pitch);
  const dx = x - c.cx;
  const dy = y - c.cy;
  const X = dx * Math.cos(a) - dy * Math.sin(a);
  const Y = dx * Math.sin(a) + dy * Math.cos(a);
  const sx = c.ox + X * c.scale;
  const sy = c.oy - (z * Math.cos(p) + Y * Math.sin(p)) * c.scale;
  const depth = Y * Math.cos(p) - z * Math.sin(p);
  return [sx, sy, depth];
}

/** Unit vector from the scene towards the camera, in world coordinates; a face is visible when its normal points this way. */
function towardsCamera(c: Camera): Vec {
  const a = rad(c.yaw);
  const p = rad(c.pitch);
  return [-Math.sin(a) * Math.cos(p), -Math.cos(a) * Math.cos(p), Math.sin(p)];
}

function fitCamera(scene: Scene, view: View): Camera {
  const zTop = Math.max(scene.plan.h, scene.allowed?.h ?? 0) + 1;
  const corners: Vec[] = [];
  for (const x of [-3, scene.W + 3]) for (const y of [-13, scene.D + 1]) for (const z of [0, zTop]) corners.push([x, y, z]);
  const base: Camera = { ...view, scale: 1, cx: scene.W / 2, cy: scene.D / 2, ox: 0, oy: 0 };
  const pts = corners.map((v) => project(v, base));
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const w = Math.max(...xs) - Math.min(...xs);
  const hh = Math.max(...ys) - Math.min(...ys);
  const scale = Math.min((VIEW_W - 2 * PAD) / w, (VIEW_H - 2 * PAD) / hh);
  const midX = ((Math.max(...xs) + Math.min(...xs)) / 2) * scale;
  const midY = ((Math.max(...ys) + Math.min(...ys)) / 2) * scale;
  return { ...base, scale, ox: VIEW_W / 2 - midX, oy: VIEW_H / 2 - midY };
}

type Box = { x0: number; x1: number; y0: number; y1: number; h: number };

/** The 5 visible faces of a box (no floor), each with its outward normal. */
function boxFaces(b: Box, z0 = 0): { points: Vec[]; normal: Vec }[] {
  const { x0, x1, y0, y1, h } = b;
  return [
    { points: [[x0, y0, h], [x1, y0, h], [x1, y1, h], [x0, y1, h]], normal: [0, 0, 1] },
    { points: [[x0, y0, z0], [x1, y0, z0], [x1, y0, h], [x0, y0, h]], normal: [0, -1, 0] },
    { points: [[x1, y1, z0], [x0, y1, z0], [x0, y1, h], [x1, y1, h]], normal: [0, 1, 0] },
    { points: [[x0, y1, z0], [x0, y0, z0], [x0, y0, h], [x0, y1, h]], normal: [-1, 0, 0] },
    { points: [[x1, y0, z0], [x1, y1, z0], [x1, y1, h], [x1, y0, h]], normal: [1, 0, 0] },
  ];
}

function dot(a: Vec, b: Vec) {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function path(points: Vec[], c: Camera): string {
  return points.map((p, i) => `${i ? "L" : "M"}${project(p, c)[0].toFixed(1)} ${project(p, c)[1].toFixed(1)}`).join(" ") + " Z";
}

// -- colours ------------------------------------------------------------------

const STROKE: Record<Status, string> = {
  complies: "stroke-success",
  short: "stroke-danger",
  unknown: "stroke-muted",
  not_applicable: "stroke-muted",
};
const FILL: Record<Status, string> = {
  complies: "fill-success/15",
  short: "fill-danger/20",
  unknown: "fill-muted/10",
  not_applicable: "fill-transparent",
};
const TEXT: Record<Status, string> = {
  complies: "fill-success",
  short: "fill-danger",
  unknown: "fill-muted",
  not_applicable: "fill-muted",
};

// -- component ----------------------------------------------------------------

export type ZoningModelProps = {
  analysis: PathwayAnalysis;
  /** The standard shown in the card: hovered or pinned. */
  active: string | null;
  onHover: (standard: string | null) => void;
  onPin: (standard: string | null) => void;
};

export function ZoningModel({ analysis, active, onHover, onPin }: ZoningModelProps) {
  const scene = useMemo(() => buildScene(analysis), [analysis]);
  const [view, setView] = useState<View>(VIEWS.iso);
  const [preset, setPreset] = useState<string | null>("iso");
  const target = useRef<View>(VIEWS.iso);
  const frame = useRef<number | null>(null);
  const drag = useRef<{ x: number; y: number; yaw: number; pitch: number } | null>(null);

  // Tween to a preset so the eye can follow which way the lot turned.
  function goTo(name: string) {
    const to = VIEWS[name];
    setPreset(name);
    target.current = to;
    if (frame.current) cancelAnimationFrame(frame.current);
    const from = { ...view };
    let t0: number | null = null;
    const step = (now: number) => {
      if (t0 === null) t0 = now;
      const t = Math.min(1, (now - t0) / 320);
      const e = 1 - Math.pow(1 - t, 3);
      let dYaw = ((to.yaw - from.yaw + 540) % 360) - 180;
      if (Math.abs(dYaw) < 0.01) dYaw = 0;
      setView({ yaw: from.yaw + dYaw * e, pitch: from.pitch + (to.pitch - from.pitch) * e });
      if (t < 1) frame.current = requestAnimationFrame(step);
    };
    frame.current = requestAnimationFrame(step);
  }
  useEffect(() => {
    // A pointer released outside the SVG (or a lost capture) must not leave the model stuck to the pointer.
    const release = () => {
      drag.current = null;
    };
    window.addEventListener("pointerup", release);
    window.addEventListener("pointercancel", release);
    return () => {
      window.removeEventListener("pointerup", release);
      window.removeEventListener("pointercancel", release);
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, []);

  function onPointerDown(e: ReactPointerEvent<SVGSVGElement>) {
    if (e.button !== 0) return;
    drag.current = { x: e.clientX, y: e.clientY, yaw: view.yaw, pitch: view.pitch };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e: ReactPointerEvent<SVGSVGElement>) {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) setPreset(null);
    setView({ yaw: d.yaw + dx * 0.5, pitch: Math.max(4, Math.min(90, d.pitch + dy * 0.4)) });
  }
  function onPointerUp(e: ReactPointerEvent<SVGSVGElement>) {
    drag.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  }

  const cam = fitCamera(scene, view);
  const eye = towardsCamera(cam);
  const faces = [
    ...boxFaces(scene.plan).map((f) => ({ ...f, kind: "plan" as const })),
    ...(scene.allowed ? boxFaces(scene.allowed).map((f) => ({ ...f, kind: "allowed" as const })) : []),
  ]
    .filter((f) => dot(f.normal, eye) > 0.02)
    .map((f) => ({ ...f, depth: f.points.reduce((s, p) => s + project(p, cam)[2], 0) / f.points.length }))
    .sort((a, b) => b.depth - a.depth);

  const floor = scene.measures.find((m) => m.standard === "lot_area");
  const footprint = scene.measures.find((m) => m.standard === "lot_coverage");
  const lines = scene.measures.filter((m) => !m.polygon);
  const street = project([scene.W / 2, -13, 0], cam);
  const centre = project([scene.W / 2, scene.D / 2, scene.plan.h / 2], cam);

  return (
    <div className="space-y-2">
      <div className="relative overflow-hidden rounded-card border border-border bg-surface-2">
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="block h-auto w-full cursor-grab touch-none select-none active:cursor-grabbing"
          role="img"
          aria-label="Schematic model of the lot, the planned building and the zoning limits"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onLostPointerCapture={() => {
            drag.current = null;
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) onPin(null);
          }}
        >
          {/* The lot floor: the lot-area measure */}
          {floor && (
            <path
              d={path(floor.points, cam)}
              className={`${active === "lot_area" ? FILL[floor.status] : "fill-foreground/[0.05]"} stroke-foreground/30 transition-colors`}
              strokeWidth={1.5}
            />
          )}
          {/* Street label */}
          <text x={street[0]} y={street[1]} textAnchor="middle" className="fill-muted text-[11px] uppercase tracking-wide">
            street
          </text>
          {/* The building that stands today, when the plan moves a wall */}
          {scene.existing && (
            <path
              d={path([[scene.existing.x0, scene.existing.y0, 0], [scene.existing.x1, scene.existing.y0, 0], [scene.existing.x1, scene.existing.y1, 0], [scene.existing.x0, scene.existing.y1, 0]], cam)}
              className="fill-none stroke-muted"
              strokeWidth={1}
              strokeDasharray="2 3"
            />
          )}
          {/* The footprint: the coverage measure */}
          {footprint && (
            <path
              d={path(footprint.points, cam)}
              className={`${FILL[footprint.status]} ${STROKE[footprint.status]} cursor-pointer`}
              strokeWidth={active === "lot_coverage" ? 2.5 : 1}
              strokeDasharray={footprint.status === "unknown" ? "4 3" : undefined}
              onPointerEnter={() => onHover("lot_coverage")}
              onPointerLeave={() => onHover(null)}
              onClick={(e) => {
                e.stopPropagation();
                onPin(active === "lot_coverage" ? null : "lot_coverage");
              }}
            />
          )}
          {/* Boxes, far to near */}
          {faces.map((f, i) =>
            f.kind === "plan" ? (
              <path
                key={`p${i}`}
                d={path(f.points, cam)}
                className="fill-foreground/[0.07] stroke-foreground/60 dark:fill-foreground/10"
                strokeWidth={1.2}
                strokeLinejoin="round"
              />
            ) : (
              <path
                key={`a${i}`}
                d={path(f.points, cam)}
                className="fill-[#2563eb]/[0.07] stroke-[#2563eb]/60 dark:fill-[#60a5fa]/[0.09] dark:stroke-[#60a5fa]/70"
                strokeWidth={1}
                strokeDasharray="5 3"
                strokeLinejoin="round"
              />
            ),
          )}
          {/* Dimension lines */}
          {lines.map((m) => {
            const [a, b] = [project(m.points[0], cam), project(m.points[1], cam)];
            if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 8) return null;
            const on = active === m.standard;
            const at = labelBeside(a, b, centre);
            return (
              <g
                key={m.standard}
                className="cursor-pointer"
                onPointerEnter={() => onHover(m.standard)}
                onPointerLeave={() => onHover(null)}
                onClick={(e) => {
                  e.stopPropagation();
                  onPin(on ? null : m.standard);
                }}
              >
                <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className="stroke-transparent" strokeWidth={16} />
                <line
                  x1={a[0]}
                  y1={a[1]}
                  x2={b[0]}
                  y2={b[1]}
                  className={`${STROKE[m.status]} transition-[stroke-width]`}
                  strokeWidth={on ? 4 : 2.2}
                  strokeLinecap="round"
                  strokeDasharray={m.status === "unknown" ? "5 4" : undefined}
                />
                <Tick p={a} q={b} c={cam} status={m.status} />
                <Tick p={b} q={a} c={cam} status={m.status} />
                <text
                  x={at[0]}
                  y={at[1]}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className={`${TEXT[m.status]} text-[10.5px] font-medium tabular-nums ${on ? "" : "opacity-90"}`}
                  style={{ paintOrder: "stroke", stroke: "var(--background)", strokeWidth: 3.5, strokeLinejoin: "round" }}
                >
                  {m.label}
                </text>
              </g>
            );
          })}
        </svg>
        <div className="absolute right-2 top-2 inline-flex rounded-lg border border-border bg-surface/90 p-0.5 text-xs backdrop-blur">
          {VIEW_LABELS.map(([name, label]) => (
            <button
              key={name}
              type="button"
              onClick={() => goTo(name)}
              aria-pressed={preset === name}
              className={`rounded-md px-2 py-1 ${preset === name ? "bg-background font-medium shadow-sm" : "text-muted hover:text-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted">
        <ul className="flex flex-wrap gap-x-3 gap-y-1">
          <Swatch className="bg-success">Fits the by-law</Swatch>
          <Swatch className="bg-danger">Short</Swatch>
          <Swatch className="border border-dashed border-muted">Unknown</Swatch>
          <Swatch className="border border-dashed border-[#2563eb] bg-[#2563eb]/10 dark:border-[#60a5fa]">The most the by-law allows</Swatch>
          <Swatch className="bg-foreground/15 outline outline-1 outline-foreground/60">Your plan</Swatch>
        </ul>
        <p>Drag to turn it. Hover or tap a line for the meaning.</p>
      </div>
      {scene.badges.length > 0 && (
        <ul className="flex flex-wrap gap-2 text-xs">
          {scene.badges.map((b) => (
            <li key={b.standard}>
              <button
                type="button"
                onPointerEnter={() => onHover(b.standard)}
                onPointerLeave={() => onHover(null)}
                onClick={() => onPin(active === b.standard ? null : b.standard)}
                className={`rounded-full border px-2.5 py-1 tabular-nums ${badgeTone(b.status)} ${active === b.standard ? "ring-2 ring-foreground/20" : ""}`}
              >
                {b.label}
              </button>
            </li>
          ))}
          <li className="self-center text-muted">Not drawn: these have no place on the box.</li>
        </ul>
      )}
    </div>
  );
}

function badgeTone(status: Status): string {
  if (status === "complies") return "border-success/40 bg-success/10 text-success";
  if (status === "short") return "border-danger/50 bg-danger-soft text-danger";
  return "border-dashed border-muted text-muted";
}

/** The label point for a segment: its midpoint, pushed 13 px off the line on the side away from the scene centre. */
function labelBeside(a: [number, number, number], b: [number, number, number], centre: [number, number, number]): [number, number] {
  const mx = (a[0] + b[0]) / 2;
  const my = (a[1] + b[1]) / 2;
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  let nx = -dy / len;
  let ny = dx / len;
  if ((mx - centre[0]) * nx + (my - centre[1]) * ny < 0) {
    nx = -nx;
    ny = -ny;
  }
  return [mx + nx * 13, my + ny * 13];
}

/** A short end mark across a dimension line. */
function Tick({ p, q, status }: { p: [number, number, number]; q: [number, number, number]; c: Camera; status: Status }) {
  const dx = q[0] - p[0];
  const dy = q[1] - p[1];
  const len = Math.hypot(dx, dy) || 1;
  const nx = (-dy / len) * 4;
  const ny = (dx / len) * 4;
  return <line x1={p[0] + nx} y1={p[1] + ny} x2={p[0] - nx} y2={p[1] - ny} className={STROKE[status]} strokeWidth={1.5} />;
}

function Swatch({ className, children }: { className: string; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 rounded-sm ${className}`} aria-hidden />
      {children}
    </li>
  );
}

/** The card beside the model: the plain-words meaning of the active standard and its 3 numbers. */
export function TermCard({ gap, scene }: { gap: Gap | null; scene?: Scene }) {
  if (!gap) {
    return (
      <div className="rounded-card border border-border bg-surface p-4 text-sm text-muted shadow-card">
        <p className="font-medium text-foreground">What the lines mean</p>
        <p className="mt-1 leading-relaxed">
          Each line is 1 rule of the by-law, drawn where it is measured. Hover or tap a line, a badge or a row of the table to
          read what the rule is and how your plan compares.
        </p>
        {scene?.approximate && (
          <p className="mt-2 text-xs leading-relaxed">The lot is drawn as a rectangle. This lot is not one, so the picture is approximate.</p>
        )}
      </div>
    );
  }
  const term = GLOSSARY[gap.standard];
  const measure = scene?.measures.find((m) => m.standard === gap.standard);
  const verdict =
    gap.status === "complies"
      ? "Fits the by-law."
      : gap.status === "short" && gap.delta != null
        ? `Short by ${fmt(gap.delta, gap.unit)}. A route below addresses it.`
        : gap.status === "short"
          ? "Short of the by-law."
          : gap.required_status === "not_applicable"
            ? "The by-law sets no limit here."
            : gap.proposed == null
              ? "Not given. Add it to the details to have it checked."
              : "The by-law value for this lot is not known.";
  return (
    <div className="space-y-3 rounded-card border border-border bg-surface p-4 text-sm shadow-card">
      <div>
        <p className="font-medium">{term?.name ?? gap.label}</p>
        <p className="text-xs text-muted">{gap.label}</p>
      </div>
      {term && (
        <div className="space-y-1.5 leading-relaxed text-foreground/90">
          <p>{term.what}</p>
          <p className="text-muted">{term.why}</p>
          <p className="text-xs text-muted">{term.how}</p>
        </div>
      )}
      <dl className="grid grid-cols-3 gap-2 text-xs">
        <Num label="By-law" value={gap.required_status === "not_applicable" ? "No limit" : `${fmt(gap.required, gap.unit)}${gap.required != null ? ` ${gap.kind}` : ""}`} />
        <Num label="Your plan" value={fmt(gap.proposed, gap.unit)} hint={gap.proposed_source === "existing" ? "as today" : gap.proposed_source === "derived" ? "calculated" : undefined} />
        <Num label="Today" value={fmt(gap.existing, gap.unit)} hint={gap.existing_status === "short" ? "short today" : undefined} />
      </dl>
      <p className={gap.status === "short" ? "text-danger" : gap.status === "complies" ? "text-success" : "text-muted"}>{verdict}</p>
      {measure?.placeholder != null && (
        <p className="text-xs text-muted">Drawn at {fmt(measure.placeholder, gap.unit)} as a placeholder.</p>
      )}
      {gap.note && <p className="text-xs text-muted">{gap.note}</p>}
      {gap.clause_ids.length > 0 && (
        <p className="font-mono text-[11px] text-muted">
          {gap.source_url ? (
            <a href={gap.source_url} target="_blank" rel="noreferrer" className="hover:underline">
              By-law {gap.clause_ids.join(", ")}
            </a>
          ) : (
            `By-law ${gap.clause_ids.join(", ")}`
          )}
        </p>
      )}
    </div>
  );
}

function Num({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg bg-background p-2">
      <dt className="text-muted">{label}</dt>
      <dd className="tabular-nums">
        {value}
        {hint && <span className="block text-[10px] text-muted">{hint}</span>}
      </dd>
    </div>
  );
}
