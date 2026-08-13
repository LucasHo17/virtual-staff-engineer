import unittest

from virtual_staff_engineer.providers import ModelRequestRateLimiter


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class ModelRequestRateLimiterTests(unittest.TestCase):
    def test_evenly_spaces_reserved_request_slots(self):
        clock = FakeClock()
        limiter = ModelRequestRateLimiter(
            15,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        delays = tuple(limiter.acquire() for _ in range(3))

        self.assertEqual(delays, (0.0, 4.0, 4.0))
        self.assertEqual(clock.sleeps, [4.0, 4.0])

    def test_rejects_invalid_request_rate(self):
        for value in (0, -1, True, float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ModelRequestRateLimiter(value)


if __name__ == "__main__":
    unittest.main()
