import json
import tempfile
import unittest
from pathlib import Path

from virtual_staff_engineer.evaluation.phase4_baseline import (
    aggregate_phase4_baseline,
    load_workload_runs,
    write_phase4_baseline,
)


class Phase4BaselineTests(unittest.TestCase):
    def test_aggregates_outcomes_latency_retries_usage_and_throughput(self):
        runs = load_workload_runs((self._run_file(),))
        result = aggregate_phase4_baseline(runs)

        self.assertEqual(result["outcomes"]["workload_acceptance_rate"], 1.0)
        self.assertEqual(result["outcomes"]["expected_safety_block_count"], 1)
        self.assertEqual(result["latency_ms"]["queue_wait"]["p50"], 20)
        self.assertEqual(result["latency_ms"]["queue_wait"]["p95"], 30)
        self.assertEqual(result["throughput"]["jobs_per_minute"], 30.0)
        self.assertEqual(result["retries"]["retry_recovery_rate"], 1.0)
        self.assertEqual(result["usage"]["input_tokens"], 600)

    def test_old_run_reports_missing_new_metrics_without_inventing_values(self):
        path = self._run_file(include_new_metrics=False)
        result = aggregate_phase4_baseline(load_workload_runs((path,)))

        self.assertIsNone(result["throughput"]["jobs_per_minute"])
        self.assertEqual(result["retries"]["measured_job_count"], 0)
        self.assertIsNone(result["retries"]["retry_recovery_rate"])

    def test_report_refuses_accidental_overwrite(self):
        result = aggregate_phase4_baseline(
            load_workload_runs((self._run_file(),))
        )
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        write_phase4_baseline(result, directory.name)
        with self.assertRaises(FileExistsError):
            write_phase4_baseline(result, directory.name)

    def _run_file(self, include_new_metrics=True):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        cases = []
        for index, status in enumerate(("completed", "rejected", "failed"), 1):
            cases.append(
                {
                    "case_id": f"case-{index}",
                    "scenario": "test",
                    "workflow_job_id": f"job-{index}",
                    "passed": True,
                    "final_status": status,
                    "failure_code": "stale_source" if status == "failed" else None,
                    "queue_wait_ms": index * 10,
                    "automated_processing_ms": index * 100,
                    "human_wait_ms": 50 if status == "rejected" else None,
                    "end_to_end_ms": index * 100,
                    "input_tokens": index * 100,
                    "output_tokens": index * 10,
                    "tool_call_count": 1,
                    "estimated_analysis_cost_usd": 0.01,
                    **({"retry_count": 1 if index == 2 else 0} if include_new_metrics else {}),
                }
            )
        payload = {
            "workload_id": "phase4-workload-v1",
            "run_id": "test-run",
            "case_count": 3,
            "passed_count": 3,
            "cases": cases,
        }
        if include_new_metrics:
            payload["duration_ms"] = 6000
        path = Path(directory.name) / "run.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
