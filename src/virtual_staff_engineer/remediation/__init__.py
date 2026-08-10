"""Structured, evidence-grounded remediation proposals."""

from virtual_staff_engineer.remediation.contracts import (
    GeneratedPatch,
    PatchGenerationContext,
    PatchGenerationSeed,
    PatchRuleEvidence,
    PatchViolation,
    SourceSnapshot,
    validate_generated_patch,
)
from virtual_staff_engineer.remediation.gemini import GeminiPatchGenerator
from virtual_staff_engineer.remediation.source import (
    FilesystemSourceProvider,
    GitSourceProvider,
)

__all__ = [
    "FilesystemSourceProvider",
    "GeneratedPatch",
    "GitSourceProvider",
    "GeminiPatchGenerator",
    "PatchGenerationContext",
    "PatchGenerationSeed",
    "PatchRuleEvidence",
    "PatchViolation",
    "SourceSnapshot",
    "validate_generated_patch",
]
