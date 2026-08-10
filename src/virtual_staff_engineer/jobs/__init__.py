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
    IdempotencyConflictError,
    LeaseLostError,
    SubmissionResult,
    WorkflowJobRecord,
    WorkflowJobRepository,
)
from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy
from virtual_staff_engineer.jobs.worker import (
    AnalysisWorker,
    WorkerExecution,
    classify_failure,
)

__all__ = [
    "ACTIVE_JOB_STATES",
    "ALLOWED_JOB_TRANSITIONS",
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
    "WorkerExecution",
    "classify_failure",
    "validate_checkpoint_advance",
    "validate_transition",
]
