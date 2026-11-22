"""Sliding-window rate limit for the paid live-model modes (cost and denial-of-service protection)."""
from collections import defaultdict, deque
import threading
import time


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit, self.window = limit, window_seconds
        self.events = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """(allowed, seconds until the next slot frees up). An allowed call is counted."""
        now = time.monotonic() if now is None else now
        with self.lock:
            q = self.events[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, round(self.window - (now - q[0]), 1)
            q.append(now)
            return True, 0.0
