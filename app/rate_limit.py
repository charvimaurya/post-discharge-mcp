"""
In-memory sliding-window rate limits for the demo bridge.

Each key (a session ID or a visitor IP address) may make `limit` requests in
any `window_seconds`. Counts live in this process only, so a restart clears
them: this is a demo guard, not a security control.
"""

import threading
import time
from collections import deque
from typing import Callable


class RateLimiter:
    """Allow at most `limit` hits per key in any rolling window."""

    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if not hits:
            # Drop empty keys so memory does not grow with old sessions.
            del self._hits[key]
        return hits

    def allowed(self, key: str) -> bool:
        """True when one more hit would still be within the limit. Records nothing."""
        with self._lock:
            return len(self._recent(key, self.clock())) < self.limit

    def record(self, key: str) -> None:
        """Count one hit for this key now."""
        with self._lock:
            now = self.clock()
            self._recent(key, now)
            self._hits.setdefault(key, deque()).append(now)

    def clear(self) -> None:
        """Forget every count (used by tests)."""
        with self._lock:
            self._hits.clear()
