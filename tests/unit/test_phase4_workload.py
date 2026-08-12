import json
import tempfile
import unittest
from pathlib import Path

from virtual_staff_engineer.evaluation.dataset import DatasetValidationError
from virtual_staff_engineer.evaluation.workload import (
    WorkloadCaseFailed,
    load_phase4_workload,
    run_phase4_workload,
    verify_workload_source,
)


class FakeClient:
    def __init__(self, statuses):
        self.statuses = {key: list(value) for key, value in statuses.items()}
        self.submitted = []
        self.decisions = []

    def submit(self, payload):
        self.submitted.append(payload)
        return {"workflow_job_id": payload["idempotency_key"].split(":")[-1]}

    def status(self, job_id):
        values = self.statuses[job_id]
        return values.pop(0) if len(values) > 1 else values[0]

    def review(self, job_id):
        return {"rules": [{"rule_key": "SEC-01"}]}

    def decide(self, job_id, payload):
        self.decisions.append((job_id, payload))
        return {"status": payload["decision"]}


class Phase4WorkloadTests(unittest.TestCase):
    def test_frozen_project_workload_is_valid_and_fixture_exists(self):
        workload = load_phase4_workload(
            "evaluation_data/phase4_workload_v1.json"
        )
        self.assertEqual(len(workload.cases), 3)
        root = verify_workload_source(
            workload, "tests/fixtures/demo-repository"
        )
        self.assertEqual(root.name, "demo-repository")

    def test_runner_rejects_validated_patch_and_records_safe_metrics(self):
        workload = load_phase4_workload(
            self._dataset(
                {
                    "id": "reject",
                    "scenario": "validated_violation_rejected",
                    "input_type": "code_diff",
                    "source_path": "app.py",
                    "content": "+logger.info(token)",
                    "expected_ready_status": "awaiting_approval",
                    "expected_failure_code": None,
                    "decision": "rejected",
                    "expected_final_status": "rejected",
                }
            )
        )
        client = FakeClient(
            {
                "reject": [
                    {"status": "queued", "failure_code": None},
                    {"status": "awaiting_approval", "failure_code": None},
                    {
                        "status": "rejected",
                        "failure_code": None,
                        "end_to_end_ms": 25,
                    },
                ]
            }
        )
        result = run_phase4_workload(
            workload,
            client,
            "run-1",
            poll_seconds=0.001,
            sleep=lambda _: None,
        )
        self.assertEqual(result["passed_count"], 1)
        self.assertEqual(result["cases"][0]["final_status"], "rejected")
        self.assertEqual(result["cases"][0]["review_rule_keys"], ["SEC-01"])
        self.assertEqual(client.decisions[0][1]["decision"], "rejected")

    def test_terminal_mismatch_fails_fast(self):
        workload = load_phase4_workload(
            self._dataset(
                {
                    "id": "clean",
                    "scenario": "clean_design",
                    "input_type": "design_document",
                    "source_path": "design.md",
                    "content": "A clean design.",
                    "expected_ready_status": "completed",
                    "expected_failure_code": None,
                    "decision": None,
                    "expected_final_status": "completed",
                }
            )
        )
        client = FakeClient(
            {"clean": [{"status": "failed", "failure_code": "network_error"}]}
        )
        with self.assertRaises(WorkloadCaseFailed):
            run_phase4_workload(workload, client, "run-1", sleep=lambda _: None)

    def test_rejects_duplicate_case_ids(self):
        case = {
            "id": "duplicate",
            "scenario": "clean_design",
            "input_type": "design_document",
            "source_path": "design.md",
            "content": "A clean design.",
            "expected_ready_status": "completed",
            "expected_failure_code": None,
            "decision": None,
            "expected_final_status": "completed",
        }
        with self.assertRaises(DatasetValidationError):
            load_phase4_workload(self._dataset(case, case))

    def _dataset(self, *cases):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "workload.json"
        path.write_text(
            json.dumps(
                {
                    "workload_id": "test-workload",
                    "status": "frozen",
                    "required_source_files": ["app.py"],
                    "cases": list(cases),
                    "deterministic_coverage": {"invalid_patch": ["test.py"]},
                }
            ),
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
