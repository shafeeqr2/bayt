"""A possible floor plan from the city's building outline and the listed room sizes.

Listings rarely include a floor plan, but they do list each room with its level
and size, and the City of Toronto building outline gives the footprint. This
module fits the listed rooms into that footprint, level by level, so a buyer can
see how the space might be arranged.

It is a plausible arrangement, never the real one. Positions follow common
layouts: the living room at the front, the kitchen and family room at the back,
the kitchen next to the dining room, bedrooms on an exterior wall for a window.
Parts that listings leave out are added and marked as assumed: one stair in the
same place on every level, bathrooms from the bathroom count, and an attached
garage when the parking type says there is one.

Method: the footprint is laid on a 10 cm grid in street-aligned coordinates, x
along the street and y from the front wall back. Rooms are placed one at a time
at the best-scoring free position, scored for every position at once with
summed-area tables. Several room orders are tried per level and the best layout
is kept, so the result is deterministic.
"""

from __future__ import annotations

import math
import random
import re
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import numpy as np
import shapely
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from app.lot.analysis import to_m
from app.lot.schemas import LotAnalysis

GRID_M = 0.1
ATTEMPTS = 16  # room orders tried with the usual front-to-back arrangement
PACKING_ATTEMPTS = 8  # and with it relaxed, used only when they fit more of the listed rooms
RELAXED_DEPTH_SHARE = (0.3, 0.0)  # how much of the front-to-back pull the packing attempts keep, tried in order
CONTACT_WEIGHT = 1.0  # rooms that hug walls and each other leave usable space behind
PAIR_WEIGHT = 3.0  # kitchen beside dining and the like, worth moving a room off its usual spot
OVERFULL_SHARE = 0.85
SHRINK_STEPS = (0.95, 0.9, 0.85)  # a listed room that will not fit may be drawn this much smaller
STAIR_TRIAL_ATTEMPTS = (3, 2)  # zoned and packing attempts when comparing stair positions

STAIR_W, STAIR_D = 1.0, 3.6  # a straight run for a 2.7 m storey, with landings
FULL_BATH = (2.4, 1.5)
HALF_BATH = (1.5, 1.2)
SINGLE_GARAGE = (3.3, 6.0)
DOUBLE_GARAGE = (6.0, 6.0)
DOUBLE_GARAGE_MIN_WIDTH_M = 12.0
NARROW_HOUSE_M = 7.0  # below this the stair runs along a side wall

CONDO_OWNERSHIP = {"Condominium/Strata", "Condominium", "Leasehold Condo/Strata", "Shares in Co-operative"}

# Listing level names, mapped to the level we draw and its order from the bottom.
LEVELS: dict[str, tuple[str, int]] = {
    "Sub-basement": ("Basement", 0),
    "Basement": ("Basement", 0),
    "Lower level": ("Basement", 0),
    "Main level": ("Main level", 1),
    "Ground level": ("Main level", 1),
    "Second level": ("Second level", 2),
    "Upper Level": ("Second level", 2),
    "Third level": ("Third level", 3),
}
BASEMENT, MAIN = 0, 1


@dataclass(frozen=True)
class Role:
    """Where a kind of room tends to sit. depth: 0 front wall to 1 back wall; None means anywhere."""

    depth: float | None
    window: float  # how much the room wants an exterior wall
    short: str | None = None


ROLES: dict[str, Role] = {
    "living room": Role(0.15, 1.0, "Living"),
    "foyer": Role(0.0, 0.3, "Foyer"),
    "office": Role(0.2, 1.0, "Office"),
    "den": Role(0.2, 1.0, "Den"),
    "study": Role(0.2, 1.0, "Study"),
    "library": Role(0.2, 1.0, "Library"),
    "sitting room": Role(0.2, 1.0, "Sitting"),
    "great room": Role(0.6, 1.0, "Great room"),
    "dining room": Role(0.5, 0.8, "Dining"),
    "kitchen": Role(0.85, 0.8, "Kitchen"),
    "kitchen/dining room": Role(0.8, 0.8, "Kitchen"),
    "eating area": Role(0.9, 0.8, "Eating"),
    "family room": Role(0.85, 1.0, "Family"),
    "mud room": Role(0.9, 0.3, "Mud room"),
    "sunroom": Role(1.0, 1.0, "Sunroom"),
    "solarium": Role(1.0, 1.0, "Solarium"),
    "pantry": Role(0.8, 0.0, "Pantry"),
    "laundry room": Role(None, 0.0, "Laundry"),
    "bathroom": Role(None, 0.1, "Bath"),
    "utility room": Role(None, 0.0, "Utility"),
    "furnace": Role(None, 0.0, "Furnace"),
    "cold room": Role(0.0, 0.0, "Cold room"),
    "storage": Role(None, 0.0, "Storage"),
    "primary bedroom": Role(None, 1.5, "Primary"),
    "bedroom": Role(None, 1.5, "Bed"),
    "recreational, games room": Role(None, 0.5, "Rec room"),
    "games room": Role(None, 0.5, "Games"),
    "media": Role(None, 0.3, "Media"),
    "exercise room": Role(None, 0.5, "Gym"),
    "playroom": Role(None, 0.8, "Play"),
    "workshop": Role(None, 0.3, "Workshop"),
    "loft": Role(None, 0.8, "Loft"),
}
DEFAULT_ROLE = Role(None, 0.3)
# Rooms that work best side by side.
PAIRS = {
    frozenset({"kitchen", "dining room"}),
    frozenset({"kitchen", "eating area"}),
    frozenset({"kitchen", "family room"}),
    frozenset({"living room", "dining room"}),
}

_METRIC = re.compile(r"^\s*([\d.]+)\s*m\s*x\s*([\d.]+)\s*m\s*$", re.I)
_IMPERIAL = re.compile(r"^\s*(\d+)'\s*(\d+)?(?:''|\")?\s*x\s*(\d+)'\s*(\d+)?(?:''|\")?\s*$")
_BATHROOM = re.compile(r"bath|ensuite|powder|washroom|\dpc\b", re.I)


# --- Response shapes --------------------------------------------------------------------------


class PlanRoom(BaseModel):
    name: str
    short: str
    kind: Literal["room", "bathroom", "stairs", "garage"]
    assumed: bool = Field(description="True when the listing does not mention it and we added it")
    x: float = Field(description="Metres along the street from the left of the drawing")
    y: float = Field(description="Metres back from the front wall")
    width: float
    depth: float
    size: str | None = Field(None, description="The size as listed")
    scale: float | None = Field(None, description="Drawn at this share of the listed size so it fits; None when full size")


class PlanLevel(BaseModel):
    name: str
    outline: dict[str, Any] = Field(description="GeoJSON polygon of the level in local metres")
    rooms: list[PlanRoom]
    not_placed: list[str] = Field(description="Listed rooms that did not fit, or have no size")
    listed_area_m2: float
    floor_area_m2: float


class FloorPlan(BaseModel):
    width_m: float
    depth_m: float
    street_side_known: bool
    levels: list[PlanLevel]
    notes: list[str]


class FloorPlanResult(BaseModel):
    plan: FloorPlan | None
    reason: str | None = Field(None, description="Why there is no plan, when plan is null")


class NoPlan(Exception):
    """Why no plan can be drawn for a listing, in words for the buyer."""


# --- Inputs -----------------------------------------------------------------------------------


def parse_dimension(text: str | None) -> tuple[float, float] | None:
    """Metres from '3.38 m x 3.96 m' or "16'8'' x 13'10''"; None when the size is missing."""
    if not text:
        return None
    if m := _METRIC.match(text):
        a, b = float(m.group(1)), float(m.group(2))
    elif m := _IMPERIAL.match(text):
        a = (int(m.group(1)) * 12 + int(m.group(2) or 0)) * 0.0254
        b = (int(m.group(3)) * 12 + int(m.group(4) or 0)) * 0.0254
    else:
        return None
    if a < 0.5 or b < 0.5:
        return None
    return a, b


def role_key(name: str) -> str:
    key = name.strip().lower()
    if _BATHROOM.search(key):
        return "bathroom"
    if key.startswith("bedroom"):
        return "bedroom"
    return key


def short_label(name: str) -> str:
    if "powder" in name.lower():
        return "WC"
    key = role_key(name)
    if key == "bedroom":
        number = re.search(r"\d+", name)
        return f"Bed {number.group(0)}" if number else "Bed"
    role = ROLES.get(key)
    if role and role.short:
        return role.short
    return name.split(",")[0][:12]


@dataclass
class RoomSpec:
    name: str
    a: float
    b: float
    kind: Literal["room", "bathroom", "stairs", "garage"] = "room"
    assumed: bool = False
    size: str | None = None
    scale: float = 1.0

    @property
    def key(self) -> str:
        return role_key(self.name)

    @property
    def role(self) -> Role:
        return ROLES.get(self.key, DEFAULT_ROLE)

    @property
    def area(self) -> float:
        return self.a * self.b


# --- Street-aligned footprint ------------------------------------------------------------------


def wall_angle(outline: Polygon) -> float:
    """The house's main wall direction in radians, modulo 90 degrees (length-weighted)."""
    sx = sy = 0.0
    coords = list(outline.exterior.coords)
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        length = math.hypot(x1 - x0, y1 - y0)
        theta = math.atan2(y1 - y0, x1 - x0)
        sx += length * math.cos(4 * theta)
        sy += length * math.sin(4 * theta)
    return math.atan2(sy, sx) / 4


def street_aligned(footprint_m: Polygon, frontage_m: LineString | None) -> tuple[Polygon, bool]:
    """The footprint turned so its walls run along the grid, with the street side at y = 0.

    The grid follows the house's own walls, not the lot line, because on curved
    streets houses often sit at an angle to the front lot line. Of the two wall
    directions, the one closer to the street becomes x.
    """
    if frontage_m is not None and frontage_m.length > 0.5:
        (x0, y0), (x1, y1) = frontage_m.coords[0], frontage_m.coords[-1]
        known = True
    else:
        corners = list(footprint_m.minimum_rotated_rectangle.exterior.coords)
        (x0, y0), (x1, y1) = max(zip(corners, corners[1:]), key=lambda e: math.dist(*e))
        known = False
    street = math.atan2(y1 - y0, x1 - x0)
    base = wall_angle(footprint_m)

    def off_street(angle: float) -> float:
        d = (angle - street) % math.pi
        return min(d, math.pi - d)

    axis = min((base, base + math.pi / 2), key=off_street)
    ux, uy = math.cos(axis), math.sin(axis)
    nx, ny = -uy, ux
    c = footprint_m.centroid
    if (c.x - x0) * nx + (c.y - y0) * ny < 0:
        nx, ny = -nx, -ny
        ux, uy = -ux, -uy  # keep a right-handed frame so the plan is not mirrored
    local = shapely.transform(footprint_m, lambda p: np.column_stack(
        ((p[:, 0] - x0) * ux + (p[:, 1] - y0) * uy, (p[:, 0] - x0) * nx + (p[:, 1] - y0) * ny)
    ))
    minx, miny, _, _ = local.bounds
    return shapely.affinity.translate(local, -minx, -miny), known


# --- Grid placement -----------------------------------------------------------------------------


def _sat(mask: np.ndarray) -> np.ndarray:
    """Summed-area table with a zero first row and column."""
    return np.pad(mask.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))


def _window(sat: np.ndarray, h: int, w: int) -> np.ndarray:
    """Sum of every h x w window, indexed by its top-left cell."""
    return sat[h:, w:] - sat[:-h, w:] - sat[h:, :-w] + sat[:-h, :-w]


@dataclass
class Placed:
    spec: RoomSpec
    i: int
    j: int
    h: int
    w: int
    score: float


@dataclass
class Grid:
    inside: np.ndarray  # cell centre inside this level's outline
    rows: int
    cols: int
    occupied: np.ndarray = field(init=False)
    placed: list[Placed] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.occupied = np.zeros_like(self.inside)
        # Outside cells, padded by one so walls at the edge of the grid count as exterior.
        self._outside_sat = _sat(np.pad(~self.inside, 1, constant_values=True))

    def copy(self) -> Grid:
        g = Grid(self.inside, self.rows, self.cols)
        g.occupied = self.occupied.copy()
        g.placed = list(self.placed)
        return g

    def mark(self, p: Placed) -> None:
        self.occupied[p.i : p.i + p.h, p.j : p.j + p.w] = True
        self.placed.append(p)

    def best(
        self, spec: RoomSpec, *, depth_weight: float, x_target: float | None = None, role: Role | None = None
    ) -> Placed | None:
        free_sat = _sat(self.inside & ~self.occupied)
        occupied_sat = _sat(np.pad(self.occupied, 1))
        partners = [p for p in self.placed if frozenset({spec.key, p.spec.key}) in PAIRS]
        partner_sat = None
        if partners:
            mask = np.zeros_like(self.occupied)
            for p in partners:
                mask[p.i : p.i + p.h, p.j : p.j + p.w] = True
            partner_sat = _sat(np.pad(mask, 1))

        role = role or spec.role
        best: Placed | None = None
        sizes = {(_cells(spec.b), _cells(spec.a)), (_cells(spec.a), _cells(spec.b))}
        for h, w in sorted(sizes):
            if h > self.rows or w > self.cols:
                continue
            free = _window(free_sat, h, w) == h * w
            if not free.any():
                continue
            perimeter = 2.0 * (h + w)
            exterior = _window(self._outside_sat, h + 2, w + 2) / perimeter
            touching = _window(occupied_sat, h + 2, w + 2) / perimeter
            score = role.window * exterior + 0.8 * touching + CONTACT_WEIGHT * (exterior + touching)
            if partner_sat is not None:
                score = score + PAIR_WEIGHT * _window(partner_sat, h + 2, w + 2) / perimeter
            if role.depth is not None and depth_weight:
                centre_y = (np.arange(free.shape[0])[:, None] + h / 2) / self.rows
                score = score - depth_weight * np.abs(centre_y - role.depth)
            if x_target is not None:
                centre_x = (np.arange(free.shape[1])[None, :] + w / 2) / self.cols
                score = score - np.abs(centre_x - x_target)
            score = np.where(free, score, -np.inf)
            i, j = np.unravel_index(int(np.argmax(score)), score.shape)
            if best is None or score[i, j] > best.score:
                best = Placed(spec, int(i), int(j), h, w, float(score[i, j]))
        return best


def _cells(metres: float) -> int:
    return max(1, round(metres / GRID_M))


def _rasterize(outline: BaseGeometry, rows: int, cols: int) -> np.ndarray:
    ys = (np.arange(rows) + 0.5) * GRID_M
    xs = (np.arange(cols) + 0.5) * GRID_M
    xx, yy = np.meshgrid(xs, ys)
    return shapely.contains_xy(outline, xx, yy)


LayoutKey = tuple[int, int, int, int, float]


def _layout_level(
    grid: Grid, rooms: list[RoomSpec], *, depth_weight: float, attempts: tuple[int, int] = (ATTEMPTS, PACKING_ATTEMPTS)
) -> tuple[Grid, list[RoomSpec], LayoutKey]:
    """Try several room orders and keep the best layout.

    Fitting every listed room comes first. Among layouts that fit the same
    number, one with the usual front-to-back arrangement beats a pure packing,
    and then the higher total score wins.
    """
    listed = sorted((r for r in rooms if not r.assumed), key=lambda r: -r.area)
    extras = sorted((r for r in rooms if r.assumed), key=lambda r: -r.area)
    zoned, packing = attempts
    runs = [(depth_weight, 0, n) for n in range(zoned)]
    for rank, share in enumerate(RELAXED_DEPTH_SHARE, start=1):
        runs += [(depth_weight * share, rank, n) for n in range(packing // len(RELAXED_DEPTH_SHARE) or 1)]
    best: tuple[LayoutKey, Grid, list[RoomSpec]] | None = None
    for weight, rank, attempt in runs:
        order = list(listed)
        if attempt:
            random.Random(attempt).shuffle(order)
        g = grid.copy()
        missing: list[RoomSpec] = []
        total = 0.0
        shrunk = 0
        for spec in order + extras:
            spot = g.best(spec, depth_weight=weight)
            if spot is None and not spec.assumed:
                for factor in SHRINK_STEPS:
                    spot = g.best(replace(spec, a=spec.a * factor, b=spec.b * factor, scale=factor), depth_weight=weight)
                    if spot is not None:
                        shrunk += 1
                        break
            if spot is None:
                missing.append(spec)
                continue
            g.mark(spot)
            total += spot.score
        unplaced = sum(1 for r in missing if not r.assumed)
        key = (unplaced, shrunk, rank if depth_weight > 0 else 0, len(missing) - unplaced, -total)
        if best is None or key < best[0]:
            best = (key, g, missing)
        if unplaced == 0 and shrunk == 0 and rank == 0 and attempt >= zoned // 2:
            break  # a full fit in the usual arrangement after a fair search; packing runs cannot beat it
    assert best is not None
    return best[1], best[2], best[0]


# --- Assumed rooms -----------------------------------------------------------------------------


def assumed_bathrooms(
    full: int, half: int, levels: dict[int, list[RoomSpec]], listed_by_level: dict[int, int]
) -> dict[int, list[RoomSpec]]:
    """Bathrooms the listing counts but does not list as rooms, spread over the levels in the usual way."""
    present = sorted(levels)
    if not present:
        return {}
    bedroom_levels = [lvl for lvl in present if lvl >= MAIN and any(r.key in ("bedroom", "primary bedroom") for r in levels[lvl])]
    top = max(bedroom_levels) if bedroom_levels else max(present)
    has_primary = any(r.key == "primary bedroom" for r in levels.get(top, []))
    basement_lived_in = BASEMENT in levels and any(r.key not in ("utility room", "furnace", "cold room", "storage", "laundry room") for r in levels[BASEMENT])

    full_order = [top] + ([top] if has_primary else []) + ([BASEMENT] if basement_lived_in else [])
    full_order += [lvl for lvl in present if lvl >= MAIN and lvl != top] + [top] * 4
    half_order = [MAIN, BASEMENT] + [top] * 4

    out: dict[int, list[RoomSpec]] = {}
    already = dict(listed_by_level)
    total_listed = sum(already.values())
    need_full = max(0, full - total_listed)
    need_half = max(0, half - max(0, total_listed - full))

    def add(order: list[int], count: int, size: tuple[float, float], name: str) -> None:
        for lvl in order:
            if count <= 0:
                return
            if lvl not in levels:
                continue
            if already.get(lvl, 0) > 0:
                already[lvl] -= 1  # a listed bathroom already covers this slot
                continue
            out.setdefault(lvl, []).append(RoomSpec(name, *size, kind="bathroom", assumed=True))
            count -= 1

    add(full_order, need_full, FULL_BATH, "Bathroom")
    add(half_order, need_half, HALF_BATH, "Powder room")
    return out


def _attached_garage(parking_type: str | None, building_type: str | None, lot: LotAnalysis | None) -> bool:
    tokens = {t.strip() for t in (parking_type or "").split(",")}
    if "Attached Garage" not in tokens and not ("Garage" in tokens and not tokens & {"Detached Garage", "Underground", "Carport"}):
        return False
    # A garage the city outlines separately is already outside the house footprint.
    if lot and any("garage" in b.kind.lower() for b in lot.buildings if not b.is_main):
        return False
    return building_type != "Apartment"


# --- The plan ---------------------------------------------------------------------------------


def plan(
    outline: Polygon,
    rooms: list[dict[str, Any]],
    *,
    full_baths: int = 0,
    half_baths: int = 0,
    attached_garage: bool = False,
    street_side_known: bool = True,
) -> FloorPlan:
    """Fit the listed rooms into a street-aligned outline (front wall at y = 0)."""
    minx, miny, maxx, maxy = outline.bounds
    width, depth = maxx - minx, maxy - miny
    rows, cols = math.ceil(depth / GRID_M), math.ceil(width / GRID_M)
    notes: list[str] = []

    by_level: dict[int, list[RoomSpec]] = {}
    unsized: dict[int, list[str]] = {}
    unlevelled: list[str] = []
    listed_baths: dict[int, int] = {}
    for room in rooms:
        name = (room.get("type") or "Room").strip()
        level = LEVELS.get((room.get("level") or "").strip())
        if level is None:
            unlevelled.append(name)
            continue
        idx = level[1]
        dims = parse_dimension(room.get("dimension"))
        if role_key(name) == "bathroom":
            listed_baths[idx] = listed_baths.get(idx, 0) + 1
        if dims is None:
            unsized.setdefault(idx, []).append(name)
            if role_key(name) != "bathroom":
                by_level.setdefault(idx, [])
            continue
        kind = "bathroom" if role_key(name) == "bathroom" else "room"
        by_level.setdefault(idx, []).append(RoomSpec(name, dims[0], dims[1], kind=kind, size=room.get("dimension")))
    if not by_level:
        raise NoPlan("The listing gives no rooms with a level, so there is nothing to place.")

    for idx, extra in assumed_bathrooms(full_baths, half_baths, by_level, listed_baths).items():
        by_level[idx].extend(extra)
    if any(r.assumed for rs in by_level.values() for r in rs):
        notes.append("Bathrooms marked as assumed come from the listing's bathroom count; their places and sizes are a guess.")

    level_outline = {idx: outline for idx in by_level}
    garage_box: Polygon | None = None
    if attached_garage and MAIN in by_level:
        garage_box = _place_garage(outline, rows, cols, width)
        if garage_box is not None:
            for idx in (BASEMENT, MAIN):
                if idx in level_outline:
                    level_outline[idx] = _largest(outline.difference(garage_box))
            notes.append("The attached garage is assumed at the front of the house; the basement is drawn without it.")
        else:
            notes.append("The listing has an attached garage, but no place for it fit the outline.")

    grids = {idx: Grid(_rasterize(level_outline[idx], rows, cols), rows, cols) for idx in by_level}

    if len(grids) > 1:
        stair = _choose_stairs(grids, by_level, rows, cols, narrow=width < NARROW_HOUSE_M)
        if stair is not None:
            for g in grids.values():
                g.mark(stair)
            notes.append("The stairs are assumed: one straight run in the same place on every level.")

    levels: list[PlanLevel] = []
    for idx in sorted(by_level):
        grid, missing, _ = _layout_level(grids[idx], by_level[idx], depth_weight=_depth_weight(idx))
        placed_rooms = [_to_room(p) for p in grid.placed]
        if idx == MAIN and garage_box is not None:
            gx0, gy0, gx1, gy1 = garage_box.bounds
            placed_rooms.insert(0, PlanRoom(name="Garage", short="Garage", kind="garage", assumed=True,
                                            x=round(gx0, 2), y=round(gy0, 2), width=round(gx1 - gx0, 2), depth=round(gy1 - gy0, 2)))
        name = next(n for n, i in LEVELS.values() if i == idx)
        listed = [r for r in by_level[idx] if not r.assumed]
        levels.append(
            PlanLevel(
                name=name,
                outline=mapping(level_outline[idx]),
                rooms=placed_rooms,
                not_placed=[f"{r.name} (did not fit)" for r in missing if not r.assumed]
                + [f"{n} (no size given)" for n in unsized.get(idx, [])],
                listed_area_m2=round(sum(r.area for r in listed), 1),
                floor_area_m2=round(level_outline[idx].area, 1),
            )
        )

    if any(r.scale for lvl in levels for r in lvl.rooms):
        notes.append(
            "Rooms marked as smaller are drawn up to 15% under their listed size so they fit the outline. "
            "Listed sizes are usually the longest measurements and can include closets or bay windows."
        )
    overfull = [lvl.name for lvl in levels if lvl.listed_area_m2 > OVERFULL_SHARE * lvl.floor_area_m2]
    if overfull:
        notes.append(
            f"The listed rooms on the {_join(overfull)} add up to nearly all of the outline or more. Listings often give "
            "open-plan spaces twice or round sizes up, so some rooms could not be placed."
        )
    if any(i >= 2 for i in by_level):
        notes.append("Upper floors use the ground-floor outline; the real upper floor may be smaller.")
    if unlevelled:
        notes.append(f"Not drawn because the listing gives no level: {', '.join(unlevelled)}.")
    if not street_side_known:
        notes.append("The street side of the lot is unknown, so the front of the house is a guess.")
    return FloorPlan(width_m=round(width, 2), depth_m=round(depth, 2), street_side_known=street_side_known, levels=levels, notes=notes)


def _choose_stairs(
    grids: dict[int, Grid], by_level: dict[int, list[RoomSpec]], rows: int, cols: int, *, narrow: bool
) -> Placed | None:
    """The stair position, the same on every level, that lets the most listed rooms fit."""
    shared = Grid(np.logical_and.reduce([g.inside for g in grids.values()]), rows, cols)
    spec = RoomSpec("Stairs", STAIR_W, STAIR_D, kind="stairs", assumed=True)
    # Along a side wall at the middle, front and back, and in the centre; the usual choice for the house width first.
    wall = [(Role(d, 0.6), None) for d in (0.45, 0.25, 0.65, 0.85)]
    centre = [(Role(d, 0.0), 0.5) for d in (0.45, 0.25, 0.65)]
    candidates: list[Placed] = []
    for role, x_target in wall + centre if narrow else centre + wall:
        spot = shared.best(spec, depth_weight=2.0, x_target=x_target, role=role)
        if spot and all((spot.i, spot.j, spot.h, spot.w) != (c.i, c.j, c.h, c.w) for c in candidates):
            candidates.append(spot)
    if len(candidates) <= 1:
        return candidates[0] if candidates else None

    def cost(stair: Placed) -> tuple[float, ...]:
        # Fitting rooms first, then full size, then the usual front-to-back order, then the overall score.
        total = [0.0, 0.0, 0.0, 0.0, 0.0]
        for idx, grid in grids.items():
            g = grid.copy()
            g.mark(stair)
            _, _, key = _layout_level(g, by_level[idx], depth_weight=_depth_weight(idx), attempts=STAIR_TRIAL_ATTEMPTS)
            total = [a + b for a, b in zip(total, key)]
        return tuple(total)

    return min(candidates, key=cost)  # ties keep the usual choice, which comes first


def _depth_weight(level: int) -> float:
    """The front-to-back pull: strong on the main floor, where the order of rooms is most predictable."""
    return 3.0 if level == MAIN else 1.0


def _join(names: list[str]) -> str:
    names = [n.lower() for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _largest(geom: BaseGeometry) -> Polygon:
    if geom.geom_type == "MultiPolygon":
        return max(geom.geoms, key=lambda g: g.area)
    return geom  # type: ignore[return-value]


def _place_garage(outline: Polygon, rows: int, cols: int, width: float) -> Polygon | None:
    sizes = [DOUBLE_GARAGE, SINGLE_GARAGE] if width >= DOUBLE_GARAGE_MIN_WIDTH_M else [SINGLE_GARAGE]
    grid = Grid(_rasterize(outline, rows, cols), rows, cols)
    for gw, gd in sizes:
        # Keep the garage wide side to the street: only try one orientation.
        h, w = _cells(gd), _cells(gw)
        if h > rows or w > cols:
            continue
        free = _window(_sat(grid.inside), h, w) == h * w
        if not free.any():
            continue
        exterior = _window(grid._outside_sat, h + 2, w + 2) / (2.0 * (h + w))
        centre_y = (np.arange(free.shape[0])[:, None] + h / 2) / rows
        score = np.where(free, exterior - 5.0 * centre_y, -np.inf)
        i, j = np.unravel_index(int(np.argmax(score)), score.shape)
        return box(j * GRID_M, i * GRID_M, j * GRID_M + gw, i * GRID_M + gd)
    return None


def _to_room(p: Placed) -> PlanRoom:
    # Draw the listed size exactly; the grid only decides the position.
    rotated = p.w == _cells(p.spec.b) and p.h == _cells(p.spec.a) and p.spec.a != p.spec.b
    width, depth = (p.spec.b, p.spec.a) if rotated else (p.spec.a, p.spec.b)
    return PlanRoom(
        name=p.spec.name,
        short=short_label(p.spec.name) if p.spec.kind != "stairs" else "Stairs",
        kind=p.spec.kind,
        assumed=p.spec.assumed,
        x=round(p.j * GRID_M, 2),
        y=round(p.i * GRID_M, 2),
        width=round(width, 2),
        depth=round(depth, 2),
        size=p.spec.size,
        scale=p.spec.scale if p.spec.scale < 1 else None,
    )


# --- From a listing ---------------------------------------------------------------------------


CACHE_SIZE = 512
_cache: OrderedDict[tuple[str, str, str], FloorPlan] = OrderedDict()


def floor_plan_for(listing: Any, lot: LotAnalysis) -> FloorPlan:
    """A possible plan for a listing, or NoPlan with the reason.

    Plans take up to a few seconds for large houses, so the latest few hundred
    are kept in memory, keyed by the listing and when its data last changed.
    """
    if listing.building_type == "Apartment" or listing.ownership_type in CONDO_OWNERSHIP:
        raise NoPlan("Condo units are not drawn: the city outline covers the whole building.")
    key = (str(listing.id), str(getattr(listing, "source_updated_at", "")), lot.computed_at.isoformat())
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    result = _floor_plan_for(listing, lot)
    _cache[key] = result
    if len(_cache) > CACHE_SIZE:
        _cache.popitem(last=False)
    return result


def _floor_plan_for(listing: Any, lot: LotAnalysis) -> FloorPlan:
    mains = [shape(f.geometry) for f in lot.geometry.buildings if f.properties.is_main and f.properties.on_lot]
    if not mains:
        raise NoPlan("The city has no building outline on this lot.")
    footprint = _largest(to_m(unary_union(mains)).buffer(0))
    frontage = to_m(shape(lot.geometry.frontage)) if lot.geometry.frontage else None
    outline, known = street_aligned(footprint, frontage)  # type: ignore[arg-type]
    outline = outline.simplify(0.05)

    building = ((listing.raw or {}).get("_details") or {}).get("Building") or {}
    half = _int(building.get("HalfBathTotal"))
    return plan(
        outline,
        listing.rooms or [],
        full_baths=listing.bathrooms or 0,
        half_baths=half,
        attached_garage=_attached_garage(listing.parking_type, listing.building_type, lot),
        street_side_known=known,
    )


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
