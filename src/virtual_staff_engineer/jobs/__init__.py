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
from virtual_staff_engineer.jobs.observability import (
    StageTiming,
    WorkflowEvent,
    WorkflowObservation,
    build_observation,
)
from virtual_staff_engineer.jobs.runtime import RuntimeExecution, WorkerRuntime
from virtual_staff_engineer.jobs.worker import (
    AnalysisWorker,
    PatchGenerationWorker,
    PatchValidationWorker,
    GitHubPullRequestWorker,
    WorkerExecution,
    classify_failure,
    classify_patch_failure,
    classify_github_failure,
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
    "StageTiming",
    "WorkflowEvent",
    "WorkflowObservation",
    "build_observation",
    "RuntimeExecution",
    "WorkerRuntime",
    "AnalysisWorker",
    "PatchGenerationWorker",
    "PatchValidationWorker",
    "GitHubPullRequestWorker",
    "WorkerExecution",
    "classify_failure",
    "classify_patch_failure",
    "classify_github_failure",
    "validate_checkpoint_advance",
    "validate_transition",
]
