import unittest
import threading
from types import SimpleNamespace

from virtual_staff_engineer.jobs.runtime import WorkerRuntime


class FakeWorker:
    def __init__(self, claimed):
        self.claimed = claimed
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return SimpleNamespace(claimed=self.claimed)


class BarrierWorker:
    def __init__(self, barrier):
        self.barrier = barrier

    def run_once(self):
        self.barrier.wait(timeout=1)
        return SimpleNamespace(claimed=True)


class WorkerRuntimeTests(unittest.TestCase):
    def test_polls_every_stage_and_returns_only_claimed_work(self):
        empty = FakeWorker(False)
        claimed = FakeWorker(True)
        results = WorkerRuntime(
            (("analysis", empty), ("validation", claimed))
        ).run_cycle()
        self.assertEqual(empty.calls, 1)
        self.assertEqual(claimed.calls, 1)
        self.assertEqual(tuple(item.stage for item in results), ("validation",))

    def test_requires_named_workers(self):
        with self.assertRaises(ValueError):
            WorkerRuntime(())
        with self.assertRaises(ValueError):
            WorkerRuntime((("", FakeWorker(False)),))

    def test_can_poll_independent_workers_concurrently(self):
        barrier = threading.Barrier(2)
        results = WorkerRuntime(
            (
                ("analysis-1", BarrierWorker(barrier)),
                ("analysis-2", BarrierWorker(barrier)),
            ),
            max_parallelism=2,
        ).run_cycle()

        self.assertEqual(
            tuple(item.stage for item in results),
            ("analysis-1", "analysis-2"),
        )

    def test_requires_positive_parallelism(self):
        with self.assertRaises(ValueError):
            WorkerRuntime((("analysis", FakeWorker(False)),), 0)


if __name__ == "__main__":
    unittest.main()
