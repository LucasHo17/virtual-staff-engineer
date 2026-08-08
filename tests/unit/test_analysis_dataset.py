import json
import tempfile
import unittest
from pathlib import Path

from virtual_staff_engineer.evaluation.analysis_dataset import (
    load_analysis_dataset,
    select_analysis_cases,
)
from virtual_staff_engineer.evaluation.dataset import DatasetValidationError


DATASET_PATH = Path("evaluation_data/analysis_workflow_cases.json")
HOLDOUT_PATH = Path("evaluation_data/analysis_holdout_v1.json")


class AnalysisDatasetTests(unittest.TestCase):
    def test_loads_twenty_balanced_frozen_cases(self):
        dataset = load_analysis_dataset(DATASET_PATH)

        distribution = {}
        for case in dataset.cases:
            distribution[case.case_type] = (
                distribution.get(case.case_type, 0) + 1
            )

        self.assertEqual(dataset.status, "frozen")
        self.assertEqual(len(dataset.cases), 20)
        self.assertEqual(
            distribution,
            {
                "violating": 5,
                "clean": 5,
                "ambiguous": 5,
                "irrelevant": 5,
            },
        )

    def test_draft_dataset_cannot_be_used_as_frozen_quality_data(self):
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        payload["status"] = "draft"
        with self.assertRaisesRegex(DatasetValidationError, "frozen"):
            self._load_payload(payload, require_frozen=True)

    def test_loads_balanced_independently_reviewed_frozen_holdout(self):
        dataset = load_analysis_dataset(HOLDOUT_PATH)
        distribution = {}
        for case in dataset.cases:
            distribution[case.case_type] = (
                distribution.get(case.case_type, 0) + 1
            )

        self.assertEqual(dataset.status, "frozen")
        self.assertEqual(dataset.review["reviewed_case_count"], 20)
        self.assertEqual(len(dataset.cases), 20)
        self.assertEqual(
            distribution,
            {
                "violating": 5,
                "clean": 5,
                "ambiguous": 5,
                "irrelevant": 5,
            },
        )

    def test_rejects_clean_case_with_expected_violation(self):
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        clean_case = next(
            case for case in payload["cases"] if case["case_type"] == "clean"
        )
        clean_case["expected_rule_keys"] = ["SEC-01"]

        with self.assertRaisesRegex(DatasetValidationError, "cannot expect"):
            self._load_payload(payload)

    def test_frozen_dataset_requires_every_case_to_be_reviewed(self):
        payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
        payload["review"]["reviewed_case_count"] = 19

        with self.assertRaisesRegex(DatasetValidationError, "review count"):
            self._load_payload(payload, require_frozen=True)

    def test_selects_explicit_balanced_smoke_case_ids(self):
        dataset = load_analysis_dataset(DATASET_PATH)
        selected = select_analysis_cases(
            dataset,
            case_ids=(
                "violating-001",
                "clean-001",
                "ambiguous-001",
                "irrelevant-001",
            ),
        )

        self.assertEqual(len(selected), 4)
        self.assertEqual(
            {case.case_type for case in selected},
            {"violating", "clean", "ambiguous", "irrelevant"},
        )

    @staticmethod
    def _load_payload(payload, require_frozen=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return load_analysis_dataset(path, require_frozen=require_frozen)


if __name__ == "__main__":
    unittest.main()
