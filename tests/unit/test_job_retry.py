import unittest

from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy


class FixedRandom:
    def __init__(self, fraction):
        self.fraction = fraction

    def uniform(self, low, high):
        return low + (high - low) * self.fraction


class ExponentialBackoffPolicyTests(unittest.TestCase):
    def test_doubles_delay_and_caps_before_jitter(self):
        policy = ExponentialBackoffPolicy(
            base_seconds=5,
            maximum_seconds=20,
            jitter_ratio=0,
        )

        self.assertEqual(
            [policy.delay_seconds(attempt) for attempt in range(1, 6)],
            [5, 10, 20, 20, 20],
        )

    def test_applies_bounded_symmetric_jitter(self):
        policy = ExponentialBackoffPolicy(
            base_seconds=10,
            maximum_seconds=100,
            jitter_ratio=0.2,
        )

        self.assertEqual(
            policy.delay_seconds(1, FixedRandom(0)),
            8,
        )
        self.assertEqual(
            policy.delay_seconds(1, FixedRandom(1)),
            12,
        )

    def test_rejects_invalid_configuration_and_attempts(self):
        with self.assertRaises(ValueError):
            ExponentialBackoffPolicy(base_seconds=0)
        with self.assertRaises(ValueError):
            ExponentialBackoffPolicy(base_seconds=10, maximum_seconds=5)
        with self.assertRaises(ValueError):
            ExponentialBackoffPolicy(jitter_ratio=1.1)
        with self.assertRaises(ValueError):
            ExponentialBackoffPolicy().delay_seconds(0)

    def test_provider_minimum_is_a_hard_floor_after_jitter(self):
        policy = ExponentialBackoffPolicy(
            base_seconds=5, maximum_seconds=60, jitter_ratio=0.2
        )

        self.assertEqual(
            policy.delay_seconds(
                1, random_source=FixedRandom(0), minimum_seconds=24.6
            ),
            24.6,
        )
        self.assertAlmostEqual(
            policy.delay_seconds(
                1, random_source=FixedRandom(1), minimum_seconds=24.6
            ),
            29.52,
        )

        for value in (-1, 86401, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    policy.delay_seconds(1, minimum_seconds=value)


if __name__ == "__main__":
    unittest.main()
