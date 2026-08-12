import unittest
from types import SimpleNamespace

from virtual_staff_engineer.jobs.runtime import WorkerRuntime


class FakeWorker:
    def __init__(self, claimed):
        self.claimed = claimed
        self.calls = 0

    def run_once(self):
        self.calls += 1
        return SimpleNamespace(claimed=self.claimed)


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


if __name__ == "__main__":
    unittest.main()
