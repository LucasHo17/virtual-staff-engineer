from typing import Protocol, Sequence, Tuple

from virtual_staff_engineer.analysis.contracts import (
    AnalysisInput,
    AnalysisProposal,
    EvaluationResult,
    ProposedFinding,
    RuleEvidence,
    SearchQuery,
)


class AnalysisReasoner(Protocol):
    """Reasoning boundary implemented by a model adapter or a test fake."""

    def plan_queries(
        self,
        analysis_input: AnalysisInput,
    ) -> Tuple[SearchQuery, ...]:
        """Select playbook searches that may apply to the input."""

    def propose_findings(
        self,
        analysis_input: AnalysisInput,
        evidence: Sequence[RuleEvidence],
    ) -> AnalysisProposal:
        """Propose findings or identify missing submitted-input context."""

    def evaluate_findings(
        self,
        analysis_input: AnalysisInput,
        findings: Sequence[ProposedFinding],
        evidence: Sequence[RuleEvidence],
    ) -> EvaluationResult:
        """Independently judge proposals or request additional context."""
