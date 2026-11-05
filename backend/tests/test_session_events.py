"""POST /api/session/{sid}/events: the taste summary is a model call and must pass the spend guard."""

from types import SimpleNamespace

from starlette.requests import Request

from app import guard, main
from app.taste import service as taste


class FakeSession:
    def get(self, model, key):
        return SimpleNamespace(id=key)  # every listing exists


def request_from(ip: str) -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [(b"x-forwarded-for", ip.encode())], "client": ("10.0.0.9", 1)})


def post(monkeypatch, actions: int, budget: guard.Budget, calls: list) -> None:
    monkeypatch.setattr(taste, "record", lambda *a, **k: actions)
    monkeypatch.setattr(taste, "summarize", lambda session, sid, n, client: calls.append(n) or SimpleNamespace(summary="s", persona=None, confidence=None, likes=[], actions=n))
    monkeypatch.setattr(taste, "taste_for", lambda session, sid: None)
    monkeypatch.setattr(taste, "make_client", lambda: object())
    monkeypatch.setattr(guard, "budget", budget)
    body = main.SessionEventIn(kind="open", listing_id="L1", via="direct")
    return main.post_session_event("a" * 16, body, FakeSession(), request_from("203.0.113.7"))


def test_due_summary_takes_one_budget_unit_keyed_by_the_visitor(monkeypatch):
    budget = guard.Budget(daily_cap=10, ip_hourly_cap=10)
    calls: list = []
    out = post(monkeypatch, 5, budget, calls)
    assert calls == [5] and out.taste is not None
    assert budget.counts() == {"today": 1, "clients": 1}


def test_no_summary_when_not_due(monkeypatch):
    budget = guard.Budget(daily_cap=10, ip_hourly_cap=10)
    calls: list = []
    out = post(monkeypatch, 4, budget, calls)
    assert calls == [] and out.taste is None and budget.counts()["today"] == 0


def test_daily_cap_blocks_the_summary_but_the_event_is_still_accepted(monkeypatch):
    budget = guard.Budget(daily_cap=0, ip_hourly_cap=-1)
    calls: list = []
    out = post(monkeypatch, 5, budget, calls)
    assert calls == [] and out.actions == 5 and out.taste is None


def test_past_max_events_no_summary_on_every_post(monkeypatch):
    budget = guard.Budget(daily_cap=10, ip_hourly_cap=-1)
    calls: list = []
    for _ in range(3):
        post(monkeypatch, taste.MAX_EVENTS, budget, calls)  # record() returns the saturated count, a multiple of EVERY
    assert calls == [] and budget.counts()["today"] == 0
