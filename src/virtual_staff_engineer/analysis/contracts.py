import math
from dataclasses import dataclass
from typing import Optional, Tuple


INPUT_TYPES = frozenset({"code_diff", "design_document"})
SEVERITIES = frozenset({"low", "medium", "high", "critical"})
EVALUATION_VERDICTS = frozenset({"supported", "unsupported"})


def _require_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


def _require_optional_text(value, field_name):
    if value is not None:
        _require_text(value, field_name)


def _require_positive_integer(value, field_name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} must be a positive integer.")


@dataclass(frozen=True)
class AnalysisInput:
    """The immutable code diff or design document being analyzed."""

    input_type: str
    content: str
    source_path: Optional[str] = None
    commit_id: Optional[str] = None

    def __post_init__(self):
        if self.input_type not in INPUT_TYPES:
            allowed = ", ".join(sorted(INPUT_TYPES))
            raise ValueError(f"input_type must be one of: {allowed}.")
        _require_text(self.content, "content")
        _require_optional_text(self.source_path, "source_path")
        _require_optional_text(self.commit_id, "commit_id")

    @property
    def lines(self):
        return tuple(self.content.splitlines())

    @property
    def numbered_content(self):
        return "\n".join(
            f"{line_number}: {line}"
            for line_number, line in enumerate(self.lines, start=1)
        )


@dataclass(frozen=True)
class SearchQuery:
    """One bounded retrieval request selected by the reasoning agent."""

    query: str
    purpose: str

    def __post_init__(self):
        _require_text(self.query, "query")
        _require_text(self.purpose, "purpose")


@dataclass(frozen=True)
class RuleEvidence:
    """A retrieved, versioned playbook chunk available as evidence."""

    playbook_chunk_id: str
    playbook_version_id: str
    rule_key: str
    filename: str
    section: str
    content: str
    retrieval_query: str
    rank_position: int
    retrieval_score: float
    semantic_rank: Optional[int] = None
    lexical_rank: Optional[int] = None

    def __post_init__(self):
        for field_name in (
            "playbook_chunk_id",
            "playbook_version_id",
            "rule_key",
            "filename",
            "section",
            "content",
            "retrieval_query",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_positive_integer(self.rank_position, "rank_position")
        if (
            isinstance(self.retrieval_score, bool)
            or not isinstance(self.retrieval_score, (int, float))
            or not math.isfinite(self.retrieval_score)
            or self.retrieval_score < 0
        ):
            raise ValueError(
                "retrieval_score must be a finite non-negative number."
            )
        for field_name in ("semantic_rank", "lexical_rank"):
            value = getattr(self, field_name)
            if value is not None:
                _require_positive_integer(value, field_name)


@dataclass(frozen=True)
class ProposedFinding:
    """An analyst proposal that is not valid until independently evaluated."""

    rule_key: str
    playbook_chunk_id: str
    source_path: str
    start_line: int
    end_line: int
    input_excerpt: str
    explanation: str
    severity: str
    confidence: float

    def __post_init__(self):
        for field_name in (
            "rule_key",
            "playbook_chunk_id",
            "source_path",
            "input_excerpt",
            "explanation",
        ):
            _require_text(getattr(self, field_name), field_name)
        _require_positive_integer(self.start_line, "start_line")
        _require_positive_integer(self.end_line, "end_line")
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line.")
        if self.severity not in SEVERITIES:
            allowed = ", ".join(sorted(SEVERITIES))
            raise ValueError(f"severity must be one of: {allowed}.")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be a finite number from 0 to 1.")


@dataclass(frozen=True)
class AnalysisProposal:
    """Analyst findings or an explicit declaration of missing input context."""

    findings: Tuple[ProposedFinding, ...]
    needs_more_input: bool = False
    context_reason: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, ProposedFinding) for finding in self.findings
        ):
            raise ValueError(
                "findings must be a tuple of ProposedFinding values."
            )
        if not isinstance(self.needs_more_input, bool):
            raise ValueError("needs_more_input must be a boolean.")
        if self.needs_more_input:
            _require_optional_text(self.context_reason, "context_reason")
            if self.context_reason is None:
                raise ValueError(
                    "context_reason is required when input context is missing."
                )
            if self.findings:
                raise ValueError(
                    "Missing-input proposals cannot also contain findings."
                )
        elif self.context_reason is not None:
            raise ValueError(
                "context_reason requires needs_more_input to be true."
            )


@dataclass(frozen=True)
class EvaluationDecision:
    """The evaluator's independent verdict for one proposed finding."""

    finding_index: int
    verdict: str
    reason: str

    def __post_init__(self):
        if (
            isinstance(self.finding_index, bool)
            or not isinstance(self.finding_index, int)
            or self.finding_index < 0
        ):
            raise ValueError("finding_index must be a non-negative integer.")
        if self.verdict not in EVALUATION_VERDICTS:
            allowed = ", ".join(sorted(EVALUATION_VERDICTS))
            raise ValueError(f"verdict must be one of: {allowed}.")
        _require_text(self.reason, "reason")


@dataclass(frozen=True)
class EvaluationResult:
    """Batch verdicts plus an explicit, bounded request for more context."""

    decisions: Tuple[EvaluationDecision, ...]
    needs_more_context: bool = False
    additional_queries: Tuple[SearchQuery, ...] = ()
    context_reason: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.decisions, tuple) or not all(
            isinstance(decision, EvaluationDecision)
            for decision in self.decisions
        ):
            raise ValueError(
                "decisions must be a tuple of EvaluationDecision values."
            )
        if not isinstance(self.needs_more_context, bool):
            raise ValueError("needs_more_context must be a boolean.")
        if not isinstance(self.additional_queries, tuple) or not all(
            isinstance(query, SearchQuery) for query in self.additional_queries
        ):
            raise ValueError(
                "additional_queries must be a tuple of SearchQuery values."
            )
        decision_indices = [
            decision.finding_index for decision in self.decisions
        ]
        if len(decision_indices) != len(set(decision_indices)):
            raise ValueError("Each finding may have only one evaluation decision.")
        if self.needs_more_context:
            if not self.additional_queries:
                raise ValueError(
                    "additional_queries are required when playbook context "
                    "is needed."
                )
            _require_optional_text(self.context_reason, "context_reason")
            if self.context_reason is None:
                raise ValueError(
                    "context_reason is required when more context is needed."
                )
        else:
            if self.additional_queries:
                raise ValueError(
                    "additional_queries require needs_more_context to be true."
                )
            if self.context_reason is not None:
                raise ValueError(
                    "context_reason requires needs_more_context to be true."
                )
