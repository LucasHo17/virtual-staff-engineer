import unittest

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.analysis.service import AnalysisService


class FakeRepository:
    def __init__(self):
        self.created = []
        self.completed = []
        self.failed = []

    def create_run(self, analysis_input, **metadata):
        self.created.append((analysis_input, metadata))
        return "run-1"

    def complete_run(self, analysis_run_id, result):
        self.completed.append((analysis_run_id, result))

    def fail_run(self, analysis_run_id, error):
        self.failed.append((analysis_run_id, str(error)))


class FakeOrchestrator:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.reasoner = type("Reasoner", (), {"model": "test-model"})()

    def run(self, analysis_input):
        if self.error:
            raise self.error
        return self.result


class AnalysisServiceTests(unittest.TestCase):
    def setUp(self):
        self.analysis_input = AnalysisInput(
            "design_document",
            "Use a transaction for the write sequence.",
            "design.md",
        )

    def test_persists_successful_terminal_result(self):
        terminal_result = object()
        repository = FakeRepository()
        service = AnalysisService(
            FakeOrchestrator(result=terminal_result),
            repository,
        )

        persisted = service.analyze(self.analysis_input)

        self.assertEqual(persisted.analysis_run_id, "run-1")
        self.assertIs(persisted.result, terminal_result)
        self.assertEqual(repository.completed, [("run-1", terminal_result)])
        self.assertEqual(repository.failed, [])
        self.assertEqual(
            repository.created[0][1]["model_name"], "test-model"
        )

    def test_marks_run_failed_when_orchestration_raises(self):
        repository = FakeRepository()
        service = AnalysisService(
            FakeOrchestrator(error=RuntimeError("model unavailable")),
            repository,
        )

        with self.assertRaisesRegex(RuntimeError, "model unavailable"):
            service.analyze(self.analysis_input)

        self.assertEqual(repository.completed, [])
        self.assertEqual(repository.failed, [("run-1", "model unavailable")])


if __name__ == "__main__":
    unittest.main()
