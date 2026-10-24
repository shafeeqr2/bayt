"""The predicate engine: parsing, three-valued evaluation, and the paths it reads."""

import pytest

from app.zoning.predicate import PredicateError, Truth, evaluate, parse, paths


def ev(spec, facts):
    return evaluate(parse(spec), facts)


def test_leaf_comparisons():
    f = {"a": 1.2, "s": "short", "b": True, "n": None}
    assert ev("a < 2", f).result is Truth.TRUE
    assert ev("a >= 1.2", f).result is Truth.TRUE
    assert ev("a > 2", f).result is Truth.FALSE
    assert ev('s == "short"', f).result is Truth.TRUE
    assert ev("s == short", f).result is Truth.TRUE  # bare word is a string
    assert ev("s != short", f).result is Truth.FALSE
    assert ev("b == true", f).result is Truth.TRUE
    assert ev("s in [short, unknown]", f).result is Truth.TRUE
    assert ev("s in [complies]", f).result is Truth.FALSE


def test_missing_fact_is_unknown_and_named():
    r = ev("gap.height.status == short", {"other": 1})
    assert r.result is Truth.UNKNOWN
    assert r.missing == ["gap.height.status"]
    r = ev("x < 3", {"x": None})
    assert r.result is Truth.UNKNOWN and r.missing == ["x"]


def test_is_null():
    assert ev("x is null", {"x": None}).result is Truth.TRUE
    assert ev("x is null", {}).result is Truth.TRUE
    assert ev("x is not null", {"x": 0}).result is Truth.TRUE
    assert ev("x is null", {"x": 0}).result is Truth.FALSE


def test_all_any_not_three_valued():
    f = {"t": 1, "f": 0}
    # all: FALSE beats UNKNOWN beats TRUE
    assert ev({"all": ["t == 1", "f == 0"]}, f).result is Truth.TRUE
    assert ev({"all": ["t == 1", "m == 0"]}, f).result is Truth.UNKNOWN
    assert ev({"all": ["t == 0", "m == 0"]}, f).result is Truth.FALSE
    # any: TRUE beats UNKNOWN beats FALSE
    assert ev({"any": ["t == 0", "m == 0"]}, f).result is Truth.UNKNOWN
    assert ev({"any": ["t == 1", "m == 0"]}, f).result is Truth.TRUE
    assert ev({"any": ["t == 0", "f == 1"]}, f).result is Truth.FALSE
    # not
    assert ev({"not": "t == 1"}, f).result is Truth.FALSE
    assert ev({"not": "m == 1"}, f).result is Truth.UNKNOWN
    # bare list = all
    assert ev(["t == 1", "f == 0"], f).result is Truth.TRUE


def test_nested_and_passed_failed_record():
    spec = {"all": ["a == 1", {"any": ["b == 2", "c == 3"]}]}
    r = ev(spec, {"a": 1, "b": 5, "c": 3})
    assert r.result is Truth.TRUE
    assert "a == 1" in r.passed and "c == 3" in r.passed
    assert "b == 2" in r.failed


def test_paths_collects_every_leaf():
    spec = {"all": ["gap.x.status == short", {"any": ["parcel.frontage_m < 9", {"not": "zoning.zone == RD"}]}]}
    assert paths(parse(spec)) == {"gap.x.status", "parcel.frontage_m", "zoning.zone"}


@pytest.mark.parametrize(
    "bad",
    [
        "a === 1",
        "a < short",  # ordering needs a number
        "a in short",  # in needs a list
        {"all": []},
        {"all": ["a == 1"], "any": ["b == 1"]},
        {"xor": ["a == 1"]},
        42,
    ],
)
def test_malformed_triggers_fail_at_parse(bad):
    with pytest.raises(PredicateError):
        parse(bad)


def test_bool_does_not_equal_number():
    assert ev("b == 1", {"b": True}).result is Truth.FALSE
    assert ev("b == true", {"b": 1}).result is Truth.FALSE
