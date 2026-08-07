from dataclasses import dataclass
from typing import Sequence, Tuple

from virtual_staff_engineer.analysis.contracts import (
    AnalysisInput,
    ProposedFinding,
    RuleEvidence,
)


@dataclass(frozen=True)
class FindingRejection:
    """One analyst proposal rejected by deterministic validation."""

    finding_index: int
    finding: ProposedFinding
    code: str
    reason: str


@dataclass(frozen=True)
class FindingValidationResult:
    """Proposals separated into evaluator-safe and rejected collections."""

    valid_findings: Tuple[ProposedFinding, ...]
    rejections: Tuple[FindingRejection, ...]


def validate_findings(
    analysis_input: AnalysisInput,
    findings: Sequence[ProposedFinding],
    evidence: Sequence[RuleEvidence],
) -> FindingValidationResult:
    """Validate identity and input citations without model judgment."""
    if not isinstance(analysis_input, AnalysisInput):
        raise TypeError("analysis_input must be an AnalysisInput.")

    evidence_by_chunk = {
        item.playbook_chunk_id: item for item in evidence
    }
    valid_findings = []
    rejections = []
    accepted_identities = set()

    for finding_index, finding in enumerate(findings):
        if not isinstance(finding, ProposedFinding):
            raise TypeError("findings must contain ProposedFinding values.")

        rejection = _validate_one(
            analysis_input,
            finding,
            finding_index,
            evidence_by_chunk,
            accepted_identities,
        )
        if rejection is not None:
            rejections.append(rejection)
            continue

        accepted_identities.add(_finding_identity(finding))
        valid_findings.append(finding)

    return FindingValidationResult(
        valid_findings=tuple(valid_findings),
        rejections=tuple(rejections),
    )


def _validate_one(
    analysis_input,
    finding,
    finding_index,
    evidence_by_chunk,
    accepted_identities,
):
    cited_evidence = evidence_by_chunk.get(finding.playbook_chunk_id)
    if cited_evidence is None:
        return _reject(
            finding_index,
            finding,
            "unknown_playbook_chunk",
            "The cited playbook chunk was not returned by retrieval.",
        )

    if finding.rule_key != cited_evidence.rule_key:
        return _reject(
            finding_index,
            finding,
            "rule_key_mismatch",
            "The finding rule key does not match the cited playbook chunk.",
        )

    expected_path = analysis_input.source_path or "<input>"
    if finding.source_path != expected_path:
        return _reject(
            finding_index,
            finding,
            "source_path_mismatch",
            "The finding source path does not match the analyzed input.",
        )

    line_count = len(analysis_input.lines)
    if finding.start_line > line_count or finding.end_line > line_count:
        return _reject(
            finding_index,
            finding,
            "line_range_out_of_bounds",
            "The cited line range is outside the analyzed input.",
        )

    cited_text = "\n".join(
        analysis_input.lines[finding.start_line - 1 : finding.end_line]
    )
    if finding.input_excerpt != cited_text:
        return _reject(
            finding_index,
            finding,
            "input_excerpt_mismatch",
            "The input excerpt is not the verbatim text at the cited lines.",
        )

    identity = _finding_identity(finding)
    if identity in accepted_identities:
        return _reject(
            finding_index,
            finding,
            "duplicate_finding",
            "The same rule and input location were already proposed.",
        )

    return None


def _finding_identity(finding):
    return (
        finding.rule_key,
        finding.source_path,
        finding.start_line,
        finding.end_line,
    )


def _reject(finding_index, finding, code, reason):
    return FindingRejection(
        finding_index=finding_index,
        finding=finding,
        code=code,
        reason=reason,
    )
