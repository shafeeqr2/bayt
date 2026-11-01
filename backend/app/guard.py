"""Spend guards for the routes that call a paid model.

Why this exists. On 2026-10-30 the site went public with no robots.txt, no rate limit
and no cap. Every `/listings/{id}/similar` page render made 1 rerank call, and the
cache key (persona + facets + candidate set) made every URL variant a new paid call.
Anthropic's ClaudeBot crawled 2,261 listings x 4 personas x facet subsets and made
233,001 model calls in 43 hours, which drained the Token Factory balance. The frontend
now asks for a rerank only when the visitor has a session cookie (a crawler never
gets one), and this module bounds the worst case from the backend side:

- a daily cap on model calls across the whole service (`MODEL_DAILY_CAP`), and
- a per-client cap per hour (`MODEL_IP_HOURLY_CAP`), keyed by the first address in
  `X-Forwarded-For` (Caddy sets it; the Next.js server forwards it).

Both counters live in memory. The API runs as 1 uvicorn worker, and a restart
resetting the day's count is acceptable: the cap is a fuse, not an accountant.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from app.config import settings

log = logging.getLogger(__name__)

IP_WINDOW_S = 3600


class Budget:
    def __init__(self, daily_cap: int, ip_hourly_cap: int, clock=time.time) -> None:
        self.daily_cap = daily_cap
        self.ip_hourly_cap = ip_hourly_cap
        self._clock = clock
        self._lock = threading.Lock()
        self._day: str | None = None
        self._day_count = 0
        self._by_ip: dict[str, deque[float]] = {}

    def _today(self) -> str:
        return datetime.fromtimestamp(self._clock(), tz=timezone.utc).strftime("%Y-%m-%d")

    def take(self, ip: str | None) -> str | None:
        """Reserve 1 model call. Returns None when allowed, or the reason when denied."""
        now = self._clock()
        with self._lock:
            today = self._today()
            if today != self._day:
                self._day, self._day_count = today, 0
                self._by_ip.clear()
            if self.daily_cap >= 0 and self._day_count >= self.daily_cap:
                log.warning("model budget: daily cap of %d reached", self.daily_cap)
                return f"the daily model budget ({self.daily_cap} calls) is used up; try again tomorrow"
            if ip and self.ip_hourly_cap >= 0:
                window = self._by_ip.setdefault(ip, deque())
                while window and window[0] <= now - IP_WINDOW_S:
                    window.popleft()
                if len(window) >= self.ip_hourly_cap:
                    log.warning("model budget: hourly cap of %d reached for %s", self.ip_hourly_cap, ip)
                    return f"too many model calls from this client ({self.ip_hourly_cap} per hour); try again later"
                window.append(now)
            self._day_count += 1
            return None

    def counts(self) -> dict[str, int]:
        with self._lock:
            return {"today": self._day_count if self._day == self._today() else 0, "clients": len(self._by_ip)}


budget = Budget(settings.model_daily_cap, settings.model_ip_hourly_cap)


def client_ip(request: Request) -> str | None:
    """The visitor's address: the first hop in X-Forwarded-For, else the peer. Only Caddy and the frontend reach this API."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else None


def charge(request: Request) -> None:
    """For the POST routes that always may call the model: 429 when a cap is hit."""
    denied = budget.take(client_ip(request))
    if denied:
        raise HTTPException(status_code=429, detail=denied)
