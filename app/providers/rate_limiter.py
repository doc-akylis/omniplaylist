import asyncio
import time


class AsyncRateLimiter:
    """Asyncio-safe rate limiter enforcing a minimum interval between requests."""

    def __init__(self, min_interval_sec: float = 1.0):
        self.min_interval_sec = max(0.0, float(min_interval_sec))
        self._lock = asyncio.Lock()
        self._last_request_ts: float = 0.0

    async def acquire(self) -> None:
        """Wait until at least min_interval_sec has elapsed since the previous request."""
        if self.min_interval_sec <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_ts
            if self._last_request_ts > 0 and elapsed < self.min_interval_sec:
                await asyncio.sleep(self.min_interval_sec - elapsed)
            self._last_request_ts = time.monotonic()
