import tempfile
import threading
import unittest
from pathlib import Path

from virtual_staff_engineer.evaluation.load_test import (
    run_phase4_load_test,
    validate_concurrency_levels,
    write_load_test_report,
)


class FakeLoadClient:
    def __init__(self, fail_level=None):
        self.fail_level = fail_level
        self.lock = threading.Lock()
        self.status_calls = {}

    def submit(self, payload):
        job_id = payload["idempotency_key"]
        with self.lock:
            self.status_calls[job_id] = 0
        return {"workflow_job_id": job_id}

    def status(self, job_id):
        with self.lock:
            self.status_calls[job_id] += 1
            calls = self.status_calls[job_id]
        level = int(job_id.split(":wave-")[1].split(":")[0])
        if calls == 1:
            return {"status": "queued"}
        failed = level == self.fail_level
        return {
            "status": "failed" if failed else "completed",
            "failure_code": "rate_limited" if failed else None,
            "queue_wait_ms": float(level),
            "automated_processing_ms": 10.0,
            "end_to_end_ms": 10.0,
            "retry_count": 1 if failed else 0,
            "input_tokens": 100,
            "output_tokens": 10,
            "tool_call_count": 1,
            "stage_timings": [],
        }

    def health(self):
        return {"status": "ok"}


class Phase4LoadTestTests(unittest.TestCase):
    def test_runs_increasing_concurrent_waves_and_aggregates_metrics(self):
        result = run_phase4_load_test(
            FakeLoadClient(),
            "test-run",
            concurrency_levels=(1, 2),
            poll_seconds=0.001,
            sleep=lambda _: None,
        )

        self.assertFalse(result["aborted"])
        self.assertEqual(result["completed_levels"], [1, 2])
        self.assertEqual(result["waves"][1]["submitted_count"], 2)
        self.assertEqual(result["waves"][1]["completed_clean_count"], 2)
        self.assertEqual(result["waves"][1]["input_tokens"], 200)

    def test_aborts_higher_waves_after_failure_threshold(self):
        result = run_phase4_load_test(
            FakeLoadClient(fail_level=2),
            "test-run",
            concurrency_levels=(1, 2, 3),
            max_failure_rate=0.2,
            poll_seconds=0.001,
            sleep=lambda _: None,
        )

        self.assertTrue(result["aborted"])
        self.assertEqual(result["completed_levels"], [1, 2])
        self.assertEqual(result["waves"][1]["unexpected_failure_rate"], 1.0)

    def test_report_refuses_accidental_overwrite(self):
        result = run_phase4_load_test(
            FakeLoadClient(),
            "test-run",
            concurrency_levels=(1,),
            poll_seconds=0.001,
            sleep=lambda _: None,
        )
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        write_load_test_report(result, directory.name)
        report = Path(directory.name, "report.md").read_text(encoding="utf-8")
        self.assertIn("configured worker concurrency", report)
        self.assertNotIn("single-worker path", report)
        with self.assertRaises(FileExistsError):
            write_load_test_report(result, directory.name)

    def test_requires_unique_increasing_positive_levels(self):
        for levels in ((), (0,), (2, 1), (1, 1)):
            with self.subTest(levels=levels):
                with self.assertRaises(ValueError):
                    validate_concurrency_levels(levels)


if __name__ == "__main__":
    unittest.main()
