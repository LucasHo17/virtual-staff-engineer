"""Durable Phase 3 workflow job contracts."""

from virtual_staff_engineer.jobs.lifecycle import (
    ACTIVE_JOB_STATES,
    ALLOWED_JOB_TRANSITIONS,
    TERMINAL_JOB_STATES,
    FailureCode,
    FailureDisposition,
    JobCheckpoint,
    JobFailure,
    JobState,
    JobTransition,
    validate_checkpoint_advance,
    validate_transition,
)
from virtual_staff_engineer.jobs.repository import (
    ApprovalConflictError,
    IdempotencyConflictError,
    LeaseLostError,
    SubmissionResult,
    WorkflowJobRecord,
    WorkflowJobRepository,
)
from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy
from virtual_staff_engineer.jobs.worker import (
    AnalysisWorker,
    PatchGenerationWorker,
    PatchValidationWorker,
    WorkerExecution,
    classify_failure,
    classify_patch_failure,
)

__all__ = [
    "ACTIVE_JOB_STATES",
    "ALLOWED_JOB_TRANSITIONS",
    "ApprovalConflictError",
    "TERMINAL_JOB_STATES",
    "FailureCode",
    "FailureDisposition",
    "JobCheckpoint",
    "JobFailure",
    "JobState",
    "JobTransition",
    "IdempotencyConflictError",
    "LeaseLostError",
    "SubmissionResult",
    "WorkflowJobRecord",
    "WorkflowJobRepository",
    "ExponentialBackoffPolicy",
    "AnalysisWorker",
    "PatchGenerationWorker",
    "PatchValidationWorker",
    "WorkerExecution",
    "classify_failure",
    "classify_patch_failure",
    "validate_checkpoint_advance",
    "validate_transition",
]
