"""A small predicate engine for playbook card triggers.

A trigger is a tree of conditions written in YAML:

    trigger:
      all:
        - gap.side_setback.status == "short"
        - building.exists == true
        - any:
            - intent.keep_existing_walls == true
            - parcel.frontage_m < 9.0
        - not: zoning.has_site_exception == true

Leaves are strings of the form ``<path> <op> <literal>``. ``path`` is a dotted
key into the fact bundle (a flat dict). ``op`` is one of ``== != < <= > >= in``,
or the unary forms ``<path> is null`` / ``<path> is not null``. Literals are
numbers, ``true``/``false``/``null``, double-quoted strings, or a ``[a, b]`` list
for ``in``.

Evaluation is three-valued. A comparison against a missing or None fact is
UNKNOWN, and the engine reports which paths were missing, so the answer can say
"needs the proposed height" instead of guessing. ``all`` is FALSE if any child is
FALSE, else UNKNOWN if any child is UNKNOWN, else TRUE. ``any`` is TRUE if any
child is TRUE, else UNKNOWN if any is UNKNOWN, else FALSE. ``not`` flips TRUE and
FALSE and leaves UNKNOWN alone.

There are no loops, no function calls and no free code. A card author can only
write comparisons and logic, so a person can read a trigger and know why a card
matched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Truth(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class PredicateError(ValueError):
    """The trigger is malformed. Raised at card load time, never at query time."""


@dataclass
class Evaluation:
    result: Truth
    missing: list[str] = field(default_factory=list)  # fact paths that were None when a leaf needed them
    passed: list[str] = field(default_factory=list)  # leaves that evaluated TRUE
    failed: list[str] = field(default_factory=list)  # leaves that evaluated FALSE


# -- parsing -------------------------------------------------------------------

_PATH = r"[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*"
_LEAF = re.compile(
    rf"^\s*(?P<path>{_PATH})\s*(?:(?P<op>==|!=|<=|>=|<|>|in)\s*(?P<lit>.+?)|(?P<isnull>is\s+(?:not\s+)?null))\s*$",
    re.I,
)
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_STRING = re.compile(r'^"([^"]*)"$|^\'([^\']*)\'$')


@dataclass(frozen=True)
class Leaf:
    path: str
    op: str  # "==", "!=", "<", "<=", ">", ">=", "in", "is_null", "is_not_null"
    literal: Any = None
    source: str = ""

    def __str__(self) -> str:
        return self.source


@dataclass(frozen=True)
class Node:
    kind: str  # "all" | "any" | "not"
    children: tuple["Leaf | Node", ...]


Predicate = Leaf | Node


def parse_literal(text: str) -> Any:
    text = text.strip()
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    if _NUMBER.match(text):
        return float(text) if "." in text else int(text)
    if m := _STRING.match(text):
        return m.group(1) if m.group(1) is not None else m.group(2)
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [parse_literal(p) for p in _split_list(inner)] if inner else []
    # A bare word is a string; this keeps YAML short (status == short).
    if re.match(r"^[A-Za-z_][A-Za-z0-9_\-]*$", text):
        return text
    raise PredicateError(f"cannot read literal {text!r}")


def _split_list(inner: str) -> list[str]:
    parts, buf, quote = [], "", None
    for ch in inner:
        if quote:
            buf += ch
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf += ch
        elif ch == ",":
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    return parts


def parse_leaf(text: str) -> Leaf:
    m = _LEAF.match(text)
    if not m:
        raise PredicateError(f"cannot read condition {text!r}")
    path = m.group("path").lower()
    if m.group("isnull"):
        op = "is_not_null" if "not" in m.group("isnull").lower() else "is_null"
        return Leaf(path, op, None, text.strip())
    op = m.group("op").lower()
    literal = parse_literal(m.group("lit"))
    if op == "in" and not isinstance(literal, list):
        raise PredicateError(f"'in' needs a list on the right: {text!r}")
    if op in ("<", "<=", ">", ">=") and not isinstance(literal, (int, float)):
        raise PredicateError(f"{op} needs a number on the right: {text!r}")
    return Leaf(path, op, literal, text.strip())


def parse(spec: Any) -> Predicate:
    """Build a predicate from the YAML value under ``trigger``."""
    if isinstance(spec, str):
        return parse_leaf(spec)
    if isinstance(spec, dict):
        if len(spec) != 1:
            raise PredicateError(f"a logic node needs exactly 1 key (all/any/not), got {sorted(spec)}")
        (kind, value), = spec.items()
        kind = str(kind).lower()
        if kind in ("all", "any"):
            if not isinstance(value, list) or not value:
                raise PredicateError(f"'{kind}' needs a non-empty list")
            return Node(kind, tuple(parse(v) for v in value))
        if kind == "not":
            return Node("not", (parse(value),))
        raise PredicateError(f"unknown logic key {kind!r}; use all, any or not")
    if isinstance(spec, list):
        # A bare list means "all".
        if not spec:
            raise PredicateError("an empty list is not a condition")
        return Node("all", tuple(parse(v) for v in spec))
    raise PredicateError(f"cannot read trigger {spec!r}")


def paths(pred: Predicate) -> set[str]:
    """Every fact path a predicate reads. Used to validate cards against the fact schema."""
    if isinstance(pred, Leaf):
        return {pred.path}
    out: set[str] = set()
    for c in pred.children:
        out |= paths(c)
    return out


# -- evaluation ----------------------------------------------------------------


def _compare(leaf: Leaf, value: Any) -> Truth:
    if leaf.op == "is_null":
        return Truth.TRUE if value is None else Truth.FALSE
    if leaf.op == "is_not_null":
        return Truth.FALSE if value is None else Truth.TRUE
    if value is None:
        return Truth.UNKNOWN
    lit = leaf.literal
    if leaf.op == "in":
        return Truth.TRUE if value in lit else Truth.FALSE
    if leaf.op == "==":
        return Truth.TRUE if _eq(value, lit) else Truth.FALSE
    if leaf.op == "!=":
        return Truth.FALSE if _eq(value, lit) else Truth.TRUE
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return Truth.UNKNOWN  # ordering a non-number is a card bug; treat as unknown rather than crash
    return Truth.TRUE if {"<": value < lit, "<=": value <= lit, ">": value > lit, ">=": value >= lit}[leaf.op] else Truth.FALSE


def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) < 1e-9
    return a == b


def evaluate(pred: Predicate, facts: dict[str, Any]) -> Evaluation:
    ev = Evaluation(Truth.UNKNOWN)
    ev.result = _eval(pred, facts, ev)
    return ev


def _eval(pred: Predicate, facts: dict[str, Any], ev: Evaluation) -> Truth:
    if isinstance(pred, Leaf):
        value = facts.get(pred.path)
        t = _compare(pred, value)
        if t is Truth.UNKNOWN and value is None:
            ev.missing.append(pred.path)
        elif t is Truth.TRUE:
            ev.passed.append(str(pred))
        elif t is Truth.FALSE:
            ev.failed.append(str(pred))
        return t
    results = [_eval(c, facts, ev) for c in pred.children]
    if pred.kind == "not":
        (r,) = results
        return {Truth.TRUE: Truth.FALSE, Truth.FALSE: Truth.TRUE, Truth.UNKNOWN: Truth.UNKNOWN}[r]
    if pred.kind == "all":
        if Truth.FALSE in results:
            return Truth.FALSE
        return Truth.UNKNOWN if Truth.UNKNOWN in results else Truth.TRUE
    if Truth.TRUE in results:
        return Truth.TRUE
    return Truth.UNKNOWN if Truth.UNKNOWN in results else Truth.FALSE
