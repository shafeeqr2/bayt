import { getFloorPlan, type FloorPlan, type PlanLevel, type PlanRoom } from "@/lib/api";

const MAX_W = 300;
const MAX_H = 340;
const PAD = 10;
const STREET_SPACE = 22;
const NAME_FONT = 9;
const SIZE_FONT = 7.5;
const CHAR_W = 0.56; // average glyph width as a share of the font size
const TREAD_M = 0.28;
const SCALE_BAR_CHOICES_M = [1, 2, 5, 10];

/** "Possible layout": the listed rooms fitted into the city's building outline, one drawing per level. */
export async function FloorPlanSection({ id }: { id: string }) {
  const result = await getFloorPlan(id);
  if (!result) return null;
  const { plan, reason } = result;

  return (
    <section className="space-y-3">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Possible layout</h2>
        <p className="text-sm text-muted">
          {plan
            ? "The listed rooms fitted into the city's building outline. The listing has no floor plan, so room positions are a best guess and the real layout will differ."
            : reason}
        </p>
      </div>
      {plan && <Plan plan={plan} />}
    </section>
  );
}

function Plan({ plan }: { plan: FloorPlan }) {
  const scale = Math.min(MAX_W / plan.width_m, MAX_H / plan.depth_m);
  return (
    <div className="space-y-4">
      <Legend />
      <div className="grid gap-4 sm:grid-cols-2">
        {[...plan.levels].reverse().map((level) => (
          <LevelCard key={level.name} level={level} plan={plan} scale={scale} />
        ))}
      </div>
      {plan.notes.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-xs text-muted">
          {plan.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Legend() {
  const swatch = "inline-block h-3 w-4 rounded-sm border align-[-2px]";
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
      <span>
        <span className={`${swatch} border-foreground/50 bg-surface`} /> Listed room
      </span>
      <span>
        <span className={`${swatch} border-dashed border-muted bg-background`} /> Assumed: stairs, bathrooms, garage
      </span>
      <span>
        <span className={`${swatch} border-foreground/50 bg-border`} /> Halls, closets and walls
      </span>
    </div>
  );
}

function LevelCard({ level, plan, scale }: { level: PlanLevel; plan: FloorPlan; scale: number }) {
  const w = plan.width_m * scale + 2 * PAD;
  const h = plan.depth_m * scale + 2 * PAD + STREET_SPACE;
  // Plan metres to SVG units: x across, the front wall (y = 0) at the bottom next to the street.
  const sx = (x: number) => PAD + x * scale;
  const sy = (y: number) => PAD + (plan.depth_m - y) * scale;

  const rings = level.outline.type === "Polygon" ? level.outline.coordinates : level.outline.coordinates.flat();
  const outlinePath = rings
    .map((ring) => ring.map(([x, y], i) => `${i ? "L" : "M"}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join(" ") + " Z")
    .join(" ");

  const bar = [...SCALE_BAR_CHOICES_M].reverse().find((m) => m * scale <= w * 0.3) ?? 1;
  const streetY = PAD + plan.depth_m * scale + 8;

  return (
    <figure className="space-y-2 rounded-xl border border-border bg-surface p-4">
      <figcaption className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold">{level.name}</span>
        <span className="text-xs tabular-nums text-muted">
          Rooms {Math.round(level.listed_area_m2)} m² of {Math.round(level.floor_area_m2)} m²
        </span>
      </figcaption>
      {/* Never wider than its natural size, so text stays the same size on narrow and wide houses. */}
      <svg
        viewBox={`0 0 ${w.toFixed(1)} ${h.toFixed(1)}`}
        style={{ maxWidth: `${Math.ceil(w)}px` }}
        className="mx-auto block w-full"
        role="img" aria-label={`Possible layout of the ${level.name.toLowerCase()}`}>
        <path d={outlinePath} fillRule="evenodd" className="fill-border stroke-foreground/50" strokeWidth={1.2} strokeLinejoin="round" />
        {level.rooms.map((room, i) => (
          <Room key={`${room.name}-${i}`} room={room} x={sx(room.x)} y={sy(room.y + room.depth)} w={room.width * scale} h={room.depth * scale} scale={scale} />
        ))}
        {plan.street_side_known && (
          <g className="fill-muted stroke-muted">
            <line x1={PAD} x2={w - PAD} y1={streetY} y2={streetY} strokeWidth={0.8} strokeDasharray="4 3" />
            <text x={PAD} y={streetY + 11} fontSize={8} stroke="none">
              Street
            </text>
          </g>
        )}
        <g className="fill-muted stroke-muted">
          <line x1={w - PAD - bar * scale} x2={w - PAD} y1={streetY + 8} y2={streetY + 8} strokeWidth={1} />
          <line x1={w - PAD - bar * scale} x2={w - PAD - bar * scale} y1={streetY + 5} y2={streetY + 11} strokeWidth={1} />
          <line x1={w - PAD} x2={w - PAD} y1={streetY + 5} y2={streetY + 11} strokeWidth={1} />
          <text x={w - PAD - bar * scale - 4} y={streetY + 11} textAnchor="end" fontSize={7.5} stroke="none">
            {bar} m
          </text>
        </g>
      </svg>
      {level.not_placed.length > 0 && <p className="text-xs text-muted">Not drawn: {level.not_placed.join(", ")}.</p>}
    </figure>
  );
}

function Room({ room, x, y, w, h, scale }: { room: PlanRoom; x: number; y: number; w: number; h: number; scale: number }) {
  const assumed = room.assumed;
  const rect = assumed
    ? "fill-background stroke-muted"
    : "fill-surface stroke-foreground/60";
  const title = [
    room.name,
    room.size ? `${room.size} as listed` : null,
    room.scale ? `drawn ${Math.round((1 - room.scale) * 100)}% smaller to fit` : null,
    assumed ? "assumed, not in the listing" : "position is a guess",
  ]
    .filter(Boolean)
    .join(", ");

  const label = room.scale ? `${room.short}*` : room.short;
  const name = fit(label, w, NAME_FONT);
  // A narrow room such as a powder room gets its name turned on its side.
  const sideways = !name && w >= NAME_FONT + 2 ? fit(label, h, NAME_FONT) : null;
  const size = `${room.width.toFixed(1)}×${room.depth.toFixed(1)}`;
  const showSize = !!name && room.kind !== "stairs" && h >= 2 * NAME_FONT + 6 && size.length * SIZE_FONT * CHAR_W <= w - 4;

  return (
    <g>
      <title>{title}</title>
      <rect x={x} y={y} width={w} height={h} className={rect} strokeWidth={1} strokeDasharray={assumed ? "3 2" : undefined} />
      {room.kind === "stairs" && <Treads x={x} y={y} w={w} h={h} scale={scale} />}
      {name && room.kind !== "stairs" && (
        <text x={x + w / 2} y={y + h / 2 + (showSize ? -1 : 3)} textAnchor="middle" fontSize={NAME_FONT} className={assumed ? "fill-muted" : "fill-foreground"}>
          {name}
        </text>
      )}
      {sideways && room.kind !== "stairs" && (
        <text
          x={x + w / 2}
          y={y + h / 2}
          transform={`rotate(-90 ${x + w / 2} ${y + h / 2})`}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={NAME_FONT}
          className={assumed ? "fill-muted" : "fill-foreground"}
        >
          {sideways}
        </text>
      )}
      {showSize && (
        <text x={x + w / 2} y={y + h / 2 + SIZE_FONT + 1} textAnchor="middle" fontSize={SIZE_FONT} className="fill-muted tabular-nums">
          {size}
        </text>
      )}
    </g>
  );
}

/** Lines across the stair's long side, one per tread. */
function Treads({ x, y, w, h, scale }: { x: number; y: number; w: number; h: number; scale: number }) {
  const along = w >= h;
  const length = along ? w : h;
  const step = TREAD_M * scale;
  const lines = [];
  for (let t = step; t < length - 0.5; t += step) {
    lines.push(
      along ? <line key={t} x1={x + t} x2={x + t} y1={y} y2={y + h} /> : <line key={t} x1={x} x2={x + w} y1={y + t} y2={y + t} />,
    );
  }
  return (
    <g className="stroke-muted" strokeWidth={0.6}>
      {lines}
    </g>
  );
}

/** The label if it fits the room's width, else nothing (the tooltip still names the room). */
function fit(label: string, width: number, font: number): string | null {
  return label.length * font * CHAR_W <= width - 4 ? label : null;
}
