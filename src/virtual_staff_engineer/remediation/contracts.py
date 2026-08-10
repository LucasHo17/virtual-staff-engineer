import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple


def _require_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")


@dataclass(frozen=True)
class SourceSnapshot:
    """Immutable source content used as the patch-generation baseline."""

    source_path: str
    content: str
    revision: Optional[str] = None

    def __post_init__(self):
        _require_text(self.source_path, "source_path")
        if not isinstance(self.content, str):
            raise TypeError("content must be a string.")
        if self.revision is not None:
            _require_text(self.revision, "revision")

    @property
    def content_sha256(self):
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PatchRuleEvidence:
    playbook_chunk_id: str
    rule_key: str
    rule_snapshot: str

    def __post_init__(self):
        _require_text(self.playbook_chunk_id, "playbook_chunk_id")
        _require_text(self.rule_key, "rule_key")
        _require_text(self.rule_snapshot, "rule_snapshot")


@dataclass(frozen=True)
class PatchViolation:
    violation_id: str
    source_path: str
    start_line: int
    end_line: int
    input_excerpt: str
    explanation: str
    evidence: Tuple[PatchRuleEvidence, ...]

    def __post_init__(self):
        _require_text(self.violation_id, "violation_id")
        _require_text(self.source_path, "source_path")
        _require_text(self.input_excerpt, "input_excerpt")
        _require_text(self.explanation, "explanation")
        if (
            isinstance(self.start_line, bool)
            or not isinstance(self.start_line, int)
            or self.start_line < 1
        ):
            raise ValueError("start_line must be a positive integer.")
        if (
            isinstance(self.end_line, bool)
            or not isinstance(self.end_line, int)
            or self.end_line < self.start_line
        ):
            raise ValueError("end_line must be at least start_line.")
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise ValueError("evidence must contain at least one rule.")
        if not all(isinstance(item, PatchRuleEvidence) for item in self.evidence):
            raise TypeError("evidence must contain PatchRuleEvidence values.")
        chunk_ids = [item.playbook_chunk_id for item in self.evidence]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("evidence cannot contain duplicate chunks.")


@dataclass(frozen=True)
class PatchGenerationContext:
    source: SourceSnapshot
    violations: Tuple[PatchViolation, ...]

    def __post_init__(self):
        if not isinstance(self.source, SourceSnapshot):
            raise TypeError("source must be a SourceSnapshot.")
        if not isinstance(self.violations, tuple) or not self.violations:
            raise ValueError("violations must contain at least one violation.")
        if not all(isinstance(item, PatchViolation) for item in self.violations):
            raise TypeError("violations must contain PatchViolation values.")
        if any(
            item.source_path != self.source.source_path
            for item in self.violations
        ):
            raise ValueError(
                "All violations must target the source snapshot path."
            )


@dataclass(frozen=True)
class PatchGenerationSeed:
    """Persisted violation context before source content is loaded."""

    source_path: str
    source_revision: Optional[str]
    violations: Tuple[PatchViolation, ...]

    def __post_init__(self):
        _require_text(self.source_path, "source_path")
        if self.source_revision is not None:
            _require_text(self.source_revision, "source_revision")
        if not isinstance(self.violations, tuple) or not self.violations:
            raise ValueError("violations must contain at least one violation.")
        if not all(isinstance(item, PatchViolation) for item in self.violations):
            raise TypeError("violations must contain PatchViolation values.")
        if any(
            item.source_path != self.source_path for item in self.violations
        ):
            raise ValueError(
                "All violations must target the seed source_path."
            )


@dataclass(frozen=True)
class GeneratedPatch:
    unified_diff: str
    explanation: str
    addressed_violation_ids: Tuple[str, ...]
    addressed_rule_keys: Tuple[str, ...]

    def __post_init__(self):
        _require_text(self.unified_diff, "unified_diff")
        _require_text(self.explanation, "explanation")
        for field_name in (
            "addressed_violation_ids",
            "addressed_rule_keys",
        ):
            values = getattr(self, field_name)
            if (
                not isinstance(values, tuple)
                or not values
                or not all(
                    isinstance(value, str) and value.strip()
                    for value in values
                )
            ):
                raise ValueError(
                    f"{field_name} must contain non-empty strings."
                )
            if len(values) != len(set(values)):
                raise ValueError(f"{field_name} cannot contain duplicates.")


def validate_generated_patch(context, patch):
    """Reject a patch that does not exactly address its validated context."""
    if not isinstance(context, PatchGenerationContext):
        raise TypeError("context must be a PatchGenerationContext.")
    if not isinstance(patch, GeneratedPatch):
        raise TypeError("patch must be a GeneratedPatch.")
    expected_violations = {
        violation.violation_id for violation in context.violations
    }
    expected_rules = {
        evidence.rule_key
        for violation in context.violations
        for evidence in violation.evidence
    }
    if set(patch.addressed_violation_ids) != expected_violations:
        raise ValueError(
            "Generated patch must address every and only validated violation."
        )
    if set(patch.addressed_rule_keys) != expected_rules:
        raise ValueError(
            "Generated patch rule keys must match the cited evidence."
        )
    lines = patch.unified_diff.splitlines()
    expected_old = f"--- a/{context.source.source_path}"
    expected_new = f"+++ b/{context.source.source_path}"
    if len(lines) < 3 or lines[0] != expected_old or lines[1] != expected_new:
        raise ValueError(
            "Generated patch must be a unified diff for the exact source path."
        )
    if sum(line.startswith("--- ") for line in lines) != 1:
        raise ValueError("Generated patch may modify only one source file.")
    if sum(line.startswith("+++ ") for line in lines) != 1:
        raise ValueError("Generated patch may modify only one source file.")
    return patch
