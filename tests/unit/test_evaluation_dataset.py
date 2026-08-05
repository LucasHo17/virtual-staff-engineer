import json
import tempfile
import unittest
from pathlib import Path

from virtual_staff_engineer.evaluation.dataset import (
    DatasetValidationError,
    load_dataset,
    select_cases,
)


def valid_payload():
    return {
        "dataset_id": "test-retrieval-v1",
        "status": "frozen",
        "review": {"reviewed_case_count": 2},
        "playbook": {
            "filename": "evaluation.md",
            "category": "evaluation",
            "version": 1,
            "rule_count": 2,
        },
        "cases": [
            {
                "id": "exact-001",
                "query_type": "exact",
                "query": "SEC-01",
                "expected_rule_keys": ["SEC-01"],
                "notes": "Exact lookup.",
            },
            {
                "id": "negative-001",
                "query_type": "negative",
                "query": "Office lunch menu",
                "expected_rule_keys": [],
                "notes": "No applicable rule.",
            },
        ],
    }


class EvaluationDatasetTests(unittest.TestCase):
    def write_payload(self, payload):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "cases.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_frozen_dataset_and_selects_cases(self):
        dataset = load_dataset(self.write_payload(valid_payload()))

        selected = select_cases(dataset, query_types=["negative"])

        self.assertEqual(dataset.dataset_id, "test-retrieval-v1")
        self.assertEqual(len(dataset.cases), 2)
        self.assertEqual([case.case_id for case in selected], ["negative-001"])

    def test_rejects_draft_dataset_by_default(self):
        payload = valid_payload()
        payload["status"] = "draft"

        with self.assertRaisesRegex(DatasetValidationError, "frozen"):
            load_dataset(self.write_payload(payload))

    def test_rejects_duplicate_case_ids(self):
        payload = valid_payload()
        payload["cases"][1]["id"] = "exact-001"

        with self.assertRaisesRegex(DatasetValidationError, "Duplicate"):
            load_dataset(self.write_payload(payload))

    def test_rejects_incomplete_frozen_review(self):
        payload = valid_payload()
        payload["review"]["reviewed_case_count"] = 1

        with self.assertRaisesRegex(DatasetValidationError, "review count"):
            load_dataset(self.write_payload(payload))

    def test_rejects_negative_case_with_expected_rule(self):
        payload = valid_payload()
        payload["cases"][1]["expected_rule_keys"] = ["SEC-01"]

        with self.assertRaisesRegex(DatasetValidationError, "negative"):
            load_dataset(self.write_payload(payload))


if __name__ == "__main__":
    unittest.main()
