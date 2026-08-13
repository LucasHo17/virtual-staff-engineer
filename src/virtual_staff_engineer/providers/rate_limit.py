import math
import threading
import time


class ModelRequestRateLimiter:
    """Reserve evenly spaced request slots across threads in one process."""

    def __init__(
        self,
        requests_per_minute,
        monotonic=None,
        sleep=None,
    ):
        if (
            isinstance(requests_per_minute, bool)
            or not isinstance(requests_per_minute, (int, float))
            or not math.isfinite(requests_per_minute)
            or requests_per_minute <= 0
        ):
            raise ValueError("requests_per_minute must be a positive number.")
        self.requests_per_minute = float(requests_per_minute)
        self.interval_seconds = 60.0 / self.requests_per_minute
        self._monotonic = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self):
        """Wait for and return the delay of the caller's reserved slot."""
        with self._lock:
            now = self._monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self.interval_seconds
        delay = max(0.0, slot - now)
        if delay:
            self._sleep(delay)
        return delay
