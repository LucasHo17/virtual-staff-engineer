from dataclasses import dataclass
from typing import Sequence, Tuple
from typing import Optional

from virtual_staff_engineer.analysis.contracts import (
    AnalysisInput,
    AnalysisProposal,
    EvaluationDecision,
    ProposedFinding,
    RuleEvidence,
    SearchQuery,
)
from virtual_staff_engineer.analysis.validation import (
    FindingRejection,
    validate_findings,
)


ANALYSIS_STATUSES = frozenset(
    {"completed_clean", "review_required", "inconclusive"}
)


def _require_bounded_integer(value, field_name, minimum, maximum):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(
            f"{field_name} must be an integer from {minimum} to {maximum}."
        )


@dataclass(frozen=True)
class WorkflowLimits:
    """Hard safety limits for one in-memory agent run."""

    max_iterations: int = 2
    max_initial_queries: int = 3
    max_additional_queries: int = 2
    max_total_queries: int = 5
    max_evidence_chunks: int = 20

    def __post_init__(self):
        _require_bounded_integer(
            self.max_iterations, "max_iterations", 1, 5
        )
        _require_bounded_integer(
            self.max_initial_queries, "max_initial_queries", 1, 5
        )
        _require_bounded_integer(
            self.max_additional_queries,
            "max_additional_queries",
            1,
            5,
        )
        _require_bounded_integer(
            self.max_total_queries, "max_total_queries", 1, 10
        )
        _require_bounded_integer(
            self.max_evidence_chunks, "max_evidence_chunks", 1, 100
        )
        if self.max_total_queries < self.max_initial_queries:
            raise ValueError(
                "max_total_queries must be at least max_initial_queries."
            )


@dataclass(frozen=True)
class AnalysisResult:
    """The explicit, non-persistent result of one bounded workflow run."""

    status: str
    findings: Tuple[ProposedFinding, ...]
    evaluated_findings: Tuple[ProposedFinding, ...]
    decisions: Tuple[EvaluationDecision, ...]
    rejected_findings: Tuple[FindingRejection, ...]
    evidence: Tuple[RuleEvidence, ...]
    queries: Tuple[SearchQuery, ...]
    iterations: int
    inconclusive_reason: Optional[str] = None

    def __post_init__(self):
        if self.status not in ANALYSIS_STATUSES:
            raise ValueError(f"Unknown analysis status: {self.status}.")
        if self.status == "inconclusive":
            if (
                not isinstance(self.inconclusive_reason, str)
                or not self.inconclusive_reason.strip()
            ):
                raise ValueError(
                    "inconclusive results require an inconclusive_reason."
                )
        elif self.inconclusive_reason is not None:
            raise ValueError(
                "inconclusive_reason is only valid for inconclusive results."
            )


class BoundedAnalysisOrchestrator:
    """Control reasoning and tools without allowing an unbounded agent loop."""

    def __init__(self, reasoner, retrieval_tool, limits=None):
        self.reasoner = reasoner
        self.retrieval_tool = retrieval_tool
        self.limits = limits or WorkflowLimits()

    def run(self, analysis_input):
        if not isinstance(analysis_input, AnalysisInput):
            raise TypeError("analysis_input must be an AnalysisInput.")

        initial_queries = self._bounded_unique_queries(
            self.reasoner.plan_queries(analysis_input),
            self.limits.max_initial_queries,
            existing_queries=(),
        )
        if not initial_queries:
            raise ValueError("The reasoner must plan at least one search query.")

        evidence, executed_queries = self._retrieve(initial_queries, ())
        all_queries = list(executed_queries)
        rejected_findings = []

        for iteration in range(1, self.limits.max_iterations + 1):
            proposal = self.reasoner.propose_findings(
                analysis_input, evidence
            )
            if not isinstance(proposal, AnalysisProposal):
                raise TypeError(
                    "Reasoners must return an AnalysisProposal."
                )
            if proposal.needs_more_input:
                return AnalysisResult(
                    status="inconclusive",
                    findings=(),
                    evaluated_findings=(),
                    decisions=(),
                    rejected_findings=tuple(rejected_findings),
                    evidence=evidence,
                    queries=tuple(all_queries),
                    iterations=iteration,
                    inconclusive_reason=proposal.context_reason,
                )
            proposed_findings = proposal.findings
            if not proposed_findings:
                return AnalysisResult(
                    status="completed_clean",
                    findings=(),
                    evaluated_findings=(),
                    decisions=(),
                    rejected_findings=tuple(rejected_findings),
                    evidence=evidence,
                    queries=tuple(all_queries),
                    iterations=iteration,
                )

            validation = validate_findings(
                analysis_input,
                proposed_findings,
                evidence,
            )
            rejected_findings.extend(validation.rejections)
            findings = validation.valid_findings
            if not findings:
                return AnalysisResult(
                    status="completed_clean",
                    findings=(),
                    evaluated_findings=(),
                    decisions=(),
                    rejected_findings=tuple(rejected_findings),
                    evidence=evidence,
                    queries=tuple(all_queries),
                    iterations=iteration,
                )

            evaluation = self.reasoner.evaluate_findings(
                analysis_input,
                findings,
                evidence,
            )
            self._validate_decision_indices(evaluation.decisions, findings)

            if not evaluation.needs_more_context:
                self._require_complete_decisions(evaluation.decisions, findings)
                supported = tuple(
                    findings[decision.finding_index]
                    for decision in evaluation.decisions
                    if decision.verdict == "supported"
                )
                status = (
                    "review_required" if supported else "completed_clean"
                )
                return AnalysisResult(
                    status=status,
                    findings=supported,
                    evaluated_findings=findings,
                    decisions=evaluation.decisions,
                    rejected_findings=tuple(rejected_findings),
                    evidence=evidence,
                    queries=tuple(all_queries),
                    iterations=iteration,
                )

            remaining_query_capacity = (
                self.limits.max_total_queries - len(all_queries)
            )
            if iteration == self.limits.max_iterations:
                break
            if remaining_query_capacity <= 0:
                break

            additional_limit = min(
                self.limits.max_additional_queries,
                remaining_query_capacity,
            )
            additional_queries = self._bounded_unique_queries(
                evaluation.additional_queries,
                additional_limit,
                existing_queries=all_queries,
            )
            if not additional_queries:
                break
            evidence, executed_queries = self._retrieve(
                additional_queries, evidence
            )
            all_queries.extend(executed_queries)

        return AnalysisResult(
            status="inconclusive",
            findings=(),
            evaluated_findings=findings,
            decisions=evaluation.decisions,
            rejected_findings=tuple(rejected_findings),
            evidence=evidence,
            queries=tuple(all_queries),
            iterations=min(iteration, self.limits.max_iterations),
            inconclusive_reason=evaluation.context_reason,
        )

    def _retrieve(self, queries, existing_evidence):
        evidence_by_chunk = {
            item.playbook_chunk_id: item for item in existing_evidence
        }
        executed_queries = []
        for query in queries:
            if len(evidence_by_chunk) >= self.limits.max_evidence_chunks:
                break
            executed_queries.append(query)
            for item in self.retrieval_tool.search(query):
                if not isinstance(item, RuleEvidence):
                    raise TypeError(
                        "Retrieval tools must return RuleEvidence values."
                    )
                evidence_by_chunk.setdefault(item.playbook_chunk_id, item)
                if (
                    len(evidence_by_chunk)
                    >= self.limits.max_evidence_chunks
                ):
                    break
        return tuple(evidence_by_chunk.values()), tuple(executed_queries)

    @staticmethod
    def _bounded_unique_queries(queries, limit, existing_queries):
        existing_text = {query.query.casefold() for query in existing_queries}
        bounded = []
        for query in queries:
            if not isinstance(query, SearchQuery):
                raise TypeError("Reasoners must return SearchQuery values.")
            normalized = query.query.casefold()
            if normalized in existing_text:
                continue
            existing_text.add(normalized)
            bounded.append(query)
            if len(bounded) == limit:
                break
        return tuple(bounded)

    @staticmethod
    def _validate_decision_indices(decisions, findings):
        for decision in decisions:
            if decision.finding_index >= len(findings):
                raise ValueError(
                    "Evaluator decision references an unknown finding index."
                )

    @staticmethod
    def _require_complete_decisions(decisions, findings):
        decided_indices = {decision.finding_index for decision in decisions}
        expected_indices = set(range(len(findings)))
        if decided_indices != expected_indices:
            raise ValueError(
                "Evaluator must decide every finding before completing a run."
            )
