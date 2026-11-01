"""The spend guards: the daily cap, the per-client hourly cap, and the client address."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import guard


class Clock:
    def __init__(self, t: float = 1_800_000_000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def test_daily_cap_stops_calls_and_resets_at_midnight_utc():
    clock = Clock()
    b = guard.Budget(daily_cap=2, ip_hourly_cap=-1, clock=clock)
    assert b.take("1.1.1.1") is None
    assert b.take("2.2.2.2") is None
    assert "daily model budget" in b.take("3.3.3.3")
    assert b.counts()["today"] == 2
    clock.t += 86_400
    assert b.take("3.3.3.3") is None


def test_hourly_cap_is_per_client_and_slides():
    clock = Clock()
    b = guard.Budget(daily_cap=-1, ip_hourly_cap=2, clock=clock)
    assert b.take("a") is None
    assert b.take("a") is None
    assert "too many model calls" in b.take("a")
    assert b.take("b") is None, "another client is not affected"
    clock.t += guard.IP_WINDOW_S + 1
    assert b.take("a") is None, "the window slid"


def test_no_client_address_still_counts_against_the_day():
    b = guard.Budget(daily_cap=1, ip_hourly_cap=1, clock=Clock())
    assert b.take(None) is None
    assert b.take(None) is not None


def test_client_ip_prefers_the_first_forwarded_hop():
    req = SimpleNamespace(headers={"x-forwarded-for": "216.73.217.58, 172.18.0.5"}, client=SimpleNamespace(host="172.18.0.5"))
    assert guard.client_ip(req) == "216.73.217.58"
    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="172.18.0.5"))
    assert guard.client_ip(req) == "172.18.0.5"


def test_charge_raises_429_when_denied(monkeypatch):
    monkeypatch.setattr(guard, "budget", guard.Budget(daily_cap=0, ip_hourly_cap=-1, clock=Clock()))
    req = SimpleNamespace(headers={}, client=SimpleNamespace(host="1.1.1.1"))
    with pytest.raises(HTTPException) as exc:
        guard.charge(req)
    assert exc.value.status_code == 429
