import random
from dataclasses import dataclass


@dataclass(frozen=True)
class ExponentialBackoffPolicy:
    """Bounded exponential retry delay with symmetric jitter."""

    base_seconds: float = 5.0
    maximum_seconds: float = 300.0
    jitter_ratio: float = 0.20

    def __post_init__(self):
        if self.base_seconds <= 0:
            raise ValueError("base_seconds must be positive.")
        if self.maximum_seconds < self.base_seconds:
            raise ValueError(
                "maximum_seconds must be at least base_seconds."
            )
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1.")

    def delay_seconds(
        self, attempt_count, random_source=None, minimum_seconds=0
    ):
        if (
            isinstance(attempt_count, bool)
            or not isinstance(attempt_count, int)
            or attempt_count < 1
        ):
            raise ValueError("attempt_count must be a positive integer.")
        if (
            isinstance(minimum_seconds, bool)
            or not isinstance(minimum_seconds, (int, float))
            or minimum_seconds < 0
            or minimum_seconds > 86400
        ):
            raise ValueError("minimum_seconds must be from 0 to 86400.")
        capped = min(
            self.maximum_seconds,
            self.base_seconds * (2 ** (attempt_count - 1)),
        )
        source = random_source or random.SystemRandom()
        if minimum_seconds > 0:
            floor = max(capped, float(minimum_seconds))
            return source.uniform(floor, floor + floor * self.jitter_ratio)
        jitter = capped * self.jitter_ratio
        return max(0.0, source.uniform(capped - jitter, capped + jitter))
