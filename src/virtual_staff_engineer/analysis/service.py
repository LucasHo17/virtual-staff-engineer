from dataclasses import dataclass

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.analysis.orchestrator import AnalysisResult


DEFAULT_WORKFLOW_VERSION = "phase2-v1"
DEFAULT_PROMPT_VERSION = "phase2-v1"


@dataclass(frozen=True)
class PersistedAnalysisResult:
    analysis_run_id: str
    result: AnalysisResult


class AnalysisService:
    """Run one analysis and persist its terminal state or failure."""

    def __init__(
        self,
        orchestrator,
        repository,
        model_name=None,
        workflow_version=DEFAULT_WORKFLOW_VERSION,
        prompt_version=DEFAULT_PROMPT_VERSION,
    ):
        self.orchestrator = orchestrator
        self.repository = repository
        self.model_name = model_name or getattr(
            orchestrator.reasoner,
            "model",
            orchestrator.reasoner.__class__.__name__,
        )
        self.workflow_version = workflow_version
        self.prompt_version = prompt_version

    def analyze(self, analysis_input):
        if not isinstance(analysis_input, AnalysisInput):
            raise TypeError("analysis_input must be an AnalysisInput.")
        analysis_run_id = self.repository.create_run(
            analysis_input,
            model_name=self.model_name,
            workflow_version=self.workflow_version,
            prompt_version=self.prompt_version,
        )
        try:
            result = self.orchestrator.run(analysis_input)
            self.repository.complete_run(analysis_run_id, result)
        except Exception as exc:
            self.repository.fail_run(analysis_run_id, exc)
            raise
        return PersistedAnalysisResult(analysis_run_id, result)
