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
    "validate_checkpoint_advance",
    "validate_transition",
]
