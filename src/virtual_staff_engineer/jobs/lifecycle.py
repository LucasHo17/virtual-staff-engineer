from dataclasses import dataclass
from enum import Enum
from typing import Optional


class JobState(str, Enum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    GENERATING_PATCH = "generating_patch"
    VALIDATING_PATCH = "validating_patch"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    CREATING_PR = "creating_pr"
    RETRY_SCHEDULED = "retry_scheduled"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class JobCheckpoint(str, Enum):
    SUBMITTED = "submitted"
    ANALYSIS_COMPLETED = "analysis_completed"
    PATCH_GENERATED = "patch_generated"
    PATCH_VALIDATED = "patch_validated"
    APPROVAL_RECORDED = "approval_recorded"
    PR_CREATED = "pr_created"


class FailureDisposition(str, Enum):
    RETRYABLE = "retryable"
    PERMANENT = "permanent"


class FailureCode(str, Enum):
    PROVIDER_TIMEOUT = "provider_timeout"
    RATE_LIMITED = "rate_limited"
    NETWORK_ERROR = "network_error"
    DATABASE_UNAVAILABLE = "database_unavailable"
    GITHUB_UNAVAILABLE = "github_unavailable"
    LEASE_EXPIRED = "lease_expired"
    INVALID_INPUT = "invalid_input"
    MODEL_CONTRACT_INVALID = "model_contract_invalid"
    EVIDENCE_VALIDATION_FAILED = "evidence_validation_failed"
    PATCH_INVALID = "patch_invalid"
    STALE_SOURCE = "stale_source"
    UNSUPPORTED_REPOSITORY_STATE = "unsupported_repository_state"


FAILURE_DISPOSITIONS = {
    FailureCode.PROVIDER_TIMEOUT: FailureDisposition.RETRYABLE,
    FailureCode.RATE_LIMITED: FailureDisposition.RETRYABLE,
    FailureCode.NETWORK_ERROR: FailureDisposition.RETRYABLE,
    FailureCode.DATABASE_UNAVAILABLE: FailureDisposition.RETRYABLE,
    FailureCode.GITHUB_UNAVAILABLE: FailureDisposition.RETRYABLE,
    FailureCode.LEASE_EXPIRED: FailureDisposition.RETRYABLE,
    FailureCode.INVALID_INPUT: FailureDisposition.PERMANENT,
    FailureCode.MODEL_CONTRACT_INVALID: FailureDisposition.PERMANENT,
    FailureCode.EVIDENCE_VALIDATION_FAILED: FailureDisposition.PERMANENT,
    FailureCode.PATCH_INVALID: FailureDisposition.PERMANENT,
    FailureCode.STALE_SOURCE: FailureDisposition.PERMANENT,
    FailureCode.UNSUPPORTED_REPOSITORY_STATE: FailureDisposition.PERMANENT,
}


ALLOWED_JOB_TRANSITIONS = {
    JobState.QUEUED: frozenset(
        {
            JobState.ANALYZING,
            JobState.GENERATING_PATCH,
            JobState.VALIDATING_PATCH,
            JobState.CREATING_PR,
            JobState.CANCELLED,
        }
    ),
    JobState.ANALYZING: frozenset(
        {
            JobState.GENERATING_PATCH,
            JobState.COMPLETED,
            JobState.RETRY_SCHEDULED,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.GENERATING_PATCH: frozenset(
        {
            JobState.VALIDATING_PATCH,
            JobState.RETRY_SCHEDULED,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.VALIDATING_PATCH: frozenset(
        {
            JobState.AWAITING_APPROVAL,
            JobState.RETRY_SCHEDULED,
            JobState.FAILED,
            JobState.CANCELLED,
        }
    ),
    JobState.AWAITING_APPROVAL: frozenset(
        {JobState.APPROVED, JobState.REJECTED, JobState.CANCELLED}
    ),
    JobState.APPROVED: frozenset(
        {JobState.CREATING_PR, JobState.CANCELLED}
    ),
    JobState.CREATING_PR: frozenset(
        {
            JobState.COMPLETED,
            JobState.RETRY_SCHEDULED,
            JobState.FAILED,
        }
    ),
    JobState.RETRY_SCHEDULED: frozenset(
        {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED}
    ),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.REJECTED: frozenset(),
    JobState.CANCELLED: frozenset(),
}

ACTIVE_JOB_STATES = frozenset(
    {
        JobState.ANALYZING,
        JobState.GENERATING_PATCH,
        JobState.VALIDATING_PATCH,
        JobState.CREATING_PR,
    }
)

TERMINAL_JOB_STATES = frozenset(
    {
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.REJECTED,
        JobState.CANCELLED,
    }
)

_CHECKPOINT_ORDER = {
    checkpoint: position
    for position, checkpoint in enumerate(JobCheckpoint)
}


@dataclass(frozen=True)
class JobFailure:
    code: FailureCode
    message: str
    disposition: Optional[FailureDisposition] = None

    def __post_init__(self):
        try:
            code = FailureCode(self.code)
        except ValueError as exc:
            raise ValueError(f"Unknown failure code: {self.code!r}.") from exc
        expected = FAILURE_DISPOSITIONS[code]
        disposition = (
            expected
            if self.disposition is None
            else FailureDisposition(self.disposition)
        )
        if disposition is not expected:
            raise ValueError(
                f"{code.value} must be classified as {expected.value}."
            )
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("failure message must be a non-empty string.")
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "disposition", disposition)


@dataclass(frozen=True)
class JobTransition:
    from_state: JobState
    to_state: JobState
    failure: Optional[JobFailure] = None

    def __post_init__(self):
        current, target = validate_transition(
            self.from_state,
            self.to_state,
            failure=self.failure,
        )
        object.__setattr__(self, "from_state", current)
        object.__setattr__(self, "to_state", target)


def validate_transition(current_state, target_state, failure=None):
    """Return normalized states or reject an illegal lifecycle transition."""
    try:
        current = JobState(current_state)
        target = JobState(target_state)
    except ValueError as exc:
        raise ValueError("Unknown workflow job state.") from exc
    if target not in ALLOWED_JOB_TRANSITIONS[current]:
        raise ValueError(
            f"Illegal workflow job transition: {current.value} -> "
            f"{target.value}."
        )
    if target is JobState.RETRY_SCHEDULED:
        if (
            not isinstance(failure, JobFailure)
            or failure.disposition is not FailureDisposition.RETRYABLE
        ):
            raise ValueError(
                "retry_scheduled requires a retryable JobFailure."
            )
    elif target is JobState.FAILED:
        if not isinstance(failure, JobFailure):
            raise ValueError("failed requires a JobFailure.")
    elif failure is not None:
        raise ValueError(
            "Failure details are allowed only for retry_scheduled or failed."
        )
    return current, target


def validate_checkpoint_advance(current_checkpoint, target_checkpoint):
    """Allow idempotent checkpoint writes and forbid checkpoint regression."""
    current = (
        None
        if current_checkpoint is None
        else JobCheckpoint(current_checkpoint)
    )
    target = JobCheckpoint(target_checkpoint)
    if current is not None and _CHECKPOINT_ORDER[target] < _CHECKPOINT_ORDER[current]:
        raise ValueError(
            f"Checkpoint cannot regress from {current.value} to "
            f"{target.value}."
        )
    return target
