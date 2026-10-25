"""Deterministic reading of the common phrases in a building plan.

A backstop under the model parse, and the only reader when no model key is set.
Pattern matching in the style of `app.strategy.parse`: instant, testable, and
it never guesses. A field the rules cannot read stays None, so the model (or the
form) decides. The model's reading wins when both have a value.

Units: metres and square metres. Feet and square feet are converted.
"""

from __future__ import annotations

import re
from typing import Any

FT = 0.3048
SQFT = 0.09290304

_NUM = r"(\d[\d,]*(?:\.\d+)?)"  # 6.5, 2,500 (thousands comma), 10
_M = r"\s*(?:m\b|metres?\b|meters?\b)"
_FT = r"\s*(?:ft\b|feet\b|foot\b|')"
_M2 = r"\s*(?:m2\b|m²|sq\.?\s*m\b|square met(?:re|er)s?\b)"
_SQFT = r"\s*(?:sq\.?\s*ft\b|sqft\b|square feet\b|ft2\b|ft²)"

ORDINALS = {"second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
PLEXES = {"duplex": 2, "triplex": 3, "fourplex": 4, "quadplex": 4, "sixplex": 6}


def _num(raw: str) -> float:
    return float(raw.replace(",", ""))


Span = tuple[int, int]
Hit = tuple[float, Span]


def _length(text: str, before: tuple[str, ...] = (), after: tuple[str, ...] = ()) -> Hit | None:
    """`<before label> ... 6.5 m` or `6.5 m <after label>`; feet are converted. The first match wins.

    A label like "high" only goes after the number: "10.5 m high and a rear yard of 6.5 m"
    must not read 6.5 as the height.
    """
    for label in before:
        for pattern, scale in ((rf"{label}[^.\d]{{0,40}}?{_NUM}{_M}", 1.0), (rf"{label}[^.\d]{{0,40}}?{_NUM}{_FT}", FT)):
            m = re.search(pattern, text, re.I)
            if m:
                return round(_num(m.group(1)) * scale, 2), m.span()
    for label in after:
        for pattern, scale in ((rf"{_NUM}{_M}\s+{label}", 1.0), (rf"{_NUM}{_FT}\s+{label}", FT)):
            m = re.search(pattern, text, re.I)
            if m:
                return round(_num(m.group(1)) * scale, 2), m.span()
    return None


def _area(text: str, *labels: str) -> Hit | None:
    for label in labels:
        for pattern, scale in (
            (rf"{label}[^.\d]{{0,40}}?{_NUM}{_M2}", 1.0),
            (rf"{label}[^.\d]{{0,40}}?{_NUM}{_SQFT}", SQFT),
            (rf"{_NUM}{_M2}\s+(?:of\s+)?{label}", 1.0),
            (rf"{_NUM}{_SQFT}\s+(?:of\s+)?{label}", SQFT),
        ):
            m = re.search(pattern, text, re.I)
            if m:
                return round(_num(m.group(1)) * scale, 1), m.span()
    return None


def _count(raw: str) -> int | None:
    raw = raw.lower()
    if raw.isdigit():
        return int(raw)
    return ORDINALS.get(raw) or WORDS.get(raw)


def extract(text: str) -> dict[str, Any]:
    """Fields of `Intent` the text states. Missing keys mean "not said"."""
    return _extract(text)[0]


def reads_all(text: str) -> bool:
    """True when the rules alone are enough and the model parse can be skipped.

    The rules must have read the project, and every digit in the text must sit inside a phrase
    the rules matched. A number the rules did not place ("the lot is 7.6 m wide", "built in 1952")
    means the model should read the text, since it may be a field the rules do not know.
    """
    fields, spans = _extract(text)
    if "project" not in fields:
        return False
    t = " ".join(text.split())
    return all(any(a <= m.start() < b for a, b in spans) for m in re.finditer(r"\d", t))


def _extract(text: str) -> tuple[dict[str, Any], list[Span]]:
    t = " ".join(text.split())
    out: dict[str, Any] = {}
    spans: list[Span] = []

    # Project and walls. Suites and severance first: "build a new garden suite" is not a tear-down.
    if re.search(r"\blaneway\s+(?:suite|house)\b", t, re.I):
        out["project"] = "laneway_suite"
    elif re.search(r"\bgarden\s+suite\b", t, re.I):
        out["project"] = "garden_suite"
    elif re.search(r"\b(sever|split\s+the\s+lot|two\s+lots|2\s+lots|subdivide|divide\s+the\s+lot)\b", t, re.I):
        out["project"], out["sever_lot"] = "sever", True
    elif re.search(r"\b(tear\s+(?:it\s+|the\s+\w+\s+)?down|demolish|knock\s+(?:it\s+)?down|rebuild|new\s*build|build\s+(?:a\s+|the\s+)?new\b)", t, re.I):
        out["project"], out["keep_existing_walls"] = "new_build", False
    elif re.search(r"\b(addition|add\s+(?:a|an|on)\b|extend|extension|renovat|keep\s+the\s+(?:house|walls)|second\s+storey\s+on|third\s+storey|storey\s+on\s+top)", t, re.I):
        out["project"], out["keep_existing_walls"] = "addition", True
    elif re.search(r"\b(convert|more\s+units|into\s+(?:a\s+)?(?:duplex|triplex|fourplex|multiplex)|basement\s+(?:suite|apartment))\b", t, re.I):
        out["project"] = "convert"
    if re.search(r"\bkeep(?:ing)?\s+(?:the\s+)?(?:existing\s+)?(?:main\s+)?walls?\b", t, re.I):
        out["keep_existing_walls"] = True

    # Storeys: "third storey", "3 storeys", "three-storey".
    m = re.search(r"\b(second|third|fourth|2nd|3rd|4th)[\s-]+(?:storey|story|floor|level)\b", t, re.I)
    if m:
        out["proposed_storeys"] = _count(m.group(1))
        spans.append(m.span())
    else:
        m = re.search(r"\b(\d|one|two|three|four|five|six)[\s-]+(?:storeys?|stories|story|floors?)\b", t, re.I)
        if m:
            out["proposed_storeys"] = _count(m.group(1))
            spans.append(m.span())

    # Units: "4 units", "fourplex", "triplex".
    m = re.search(r"\b(\d|one|two|three|four|five|six)\s+(?:dwelling\s+|residential\s+)?units?\b", t, re.I)
    if m:
        out["proposed_units"] = _count(m.group(1))
        spans.append(m.span())
    else:
        m = re.search(r"\b(duplex|triplex|fourplex|quadplex|sixplex)\b", t, re.I)
        if m:
            out["proposed_units"] = PLEXES[m.group(1).lower()]

    height = _length(t, before=(r"(?:building\s+)?height(?:\s+of)?",), after=(r"(?:high|tall)\b",))
    if height is not None:
        out["proposed_height_m"], span = height
        spans.append(span)

    for field, label in (
        ("proposed_rear_setback_m", r"(?:rear|back)\s+(?:yard|setback)"),
        ("proposed_front_setback_m", r"front\s+(?:yard|setback)"),
        ("proposed_side_setback_m", r"side\s+(?:yard|setback)s?"),
        ("proposed_building_depth_m", r"(?:building\s+)?depth"),
        ("proposed_building_length_m", r"building\s+length"),
    ):
        # "rear yard of 6.5 m" and "a 6.5 m rear yard" both count.
        value = _length(t, before=(label + r"(?:\s+(?:is|of|to|at))?",), after=(label,))
        if value is not None:
            out[field], span = value
            spans.append(span)

    gfa = _area(t, r"(?:gross\s+)?floor\s+(?:area|space)(?:\s+of)?", r"\bgfa\b")
    if gfa is not None:
        out["proposed_gfa_m2"], span = gfa
        spans.append(span)
    footprint = _area(t, r"footprint(?:\s+of)?", r"ground\s+(?:floor\s+)?area(?:\s+of)?")
    if footprint is not None:
        out["proposed_footprint_m2"], span = footprint
        spans.append(span)
    return out, spans


LABELS = {
    "proposed_units": ("Units", ""),
    "proposed_storeys": ("Storeys", ""),
    "proposed_height_m": ("Height", " m"),
    "proposed_gfa_m2": ("Floor area", " m²"),
    "proposed_footprint_m2": ("Footprint", " m²"),
    "proposed_building_depth_m": ("Building depth", " m"),
    "proposed_building_length_m": ("Building length", " m"),
    "proposed_front_setback_m": ("Front yard", " m"),
    "proposed_side_setback_m": ("Side yard", " m"),
    "proposed_rear_setback_m": ("Rear yard", " m"),
}
PROJECT_LABELS = {
    "addition": "Addition",
    "new_build": "New building",
    "convert": "More units inside the house",
    "garden_suite": "Garden suite",
    "laneway_suite": "Laneway suite",
    "sever": "Split the lot",
}


def describe(fields: dict[str, Any]) -> list[str]:
    """Short lines a person can check: 'Addition, main walls kept', 'Height 10.5 m'."""
    lines: list[str] = []
    project = fields.get("project")
    if project in PROJECT_LABELS:
        walls = fields.get("keep_existing_walls")
        suffix = ", main walls kept" if walls is True else ", main walls removed" if walls is False else ""
        lines.append(PROJECT_LABELS[project] + suffix)
    elif fields.get("keep_existing_walls") is True:
        lines.append("Main walls kept")
    elif fields.get("keep_existing_walls") is False:
        lines.append("Main walls removed")
    for name, (label, unit) in LABELS.items():
        value = fields.get(name)
        if value is None:
            continue
        number = f"{value:g}" if isinstance(value, float) else str(value)
        lines.append(f"{label} {number}{unit}")
    return lines
