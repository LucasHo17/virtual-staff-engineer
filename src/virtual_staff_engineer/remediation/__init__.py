"""Structured, evidence-grounded remediation proposals."""

from virtual_staff_engineer.remediation.contracts import (
    GeneratedPatch,
    PatchGenerationContext,
    PatchGenerationSeed,
    PatchValidationCheck,
    PatchValidationResult,
    PatchRuleEvidence,
    PatchViolation,
    SourceSnapshot,
    PersistedPatchProposal,
    validate_generated_patch,
)
from virtual_staff_engineer.remediation.gemini import GeminiPatchGenerator
from virtual_staff_engineer.remediation.source import (
    FilesystemSourceProvider,
    GitSourceProvider,
)
from virtual_staff_engineer.remediation.validation import (
    DeterministicPatchValidator,
    PatchApplyError,
    apply_unified_diff,
)

__all__ = [
    "FilesystemSourceProvider",
    "GeneratedPatch",
    "GitSourceProvider",
    "GeminiPatchGenerator",
    "PatchGenerationContext",
    "PatchGenerationSeed",
    "PatchValidationCheck",
    "PatchValidationResult",
    "PatchRuleEvidence",
    "PatchViolation",
    "SourceSnapshot",
    "PersistedPatchProposal",
    "DeterministicPatchValidator",
    "PatchApplyError",
    "apply_unified_diff",
    "validate_generated_patch",
]
