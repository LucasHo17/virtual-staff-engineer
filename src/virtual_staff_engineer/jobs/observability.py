from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple


@dataclass(frozen=True)
class WorkflowEvent:
    sequence: int
    from_status: Optional[str]
    to_status: str
    attempt_count: int
    checkpoint: str
    failure_code: Optional[str]
    error_message: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class StageTiming:
    stage: str
    duration_ms: float


@dataclass(frozen=True)
class WorkflowObservation:
    job: object
    events: Tuple[WorkflowEvent, ...]
    stage_timings: Tuple[StageTiming, ...]
    queue_wait_ms: Optional[float]
    human_wait_ms: Optional[float]
    automated_processing_ms: Optional[float]
    end_to_end_ms: Optional[float]
    input_tokens: int = 0
    output_tokens: int = 0
    tool_call_count: int = 0
    retry_count: int = 0


def build_observation(
    job,
    events,
    observed_at=None,
    input_tokens=0,
    output_tokens=0,
    tool_call_count=0,
):
    """Derive timing metrics from the immutable transition history."""
    events = tuple(events)
    now = observed_at or datetime.now(job.created_at.tzinfo)
    event_by_target = {}
    for event in events:
        event_by_target.setdefault(event.to_status, event)

    first_active = next(
        (
            event
            for event in events
            if event.to_status
            in {"analyzing", "generating_patch", "validating_patch", "creating_pr"}
        ),
        None,
    )
    queue_wait = (
        _milliseconds(first_active.created_at - job.created_at)
        if first_active else None
    )

    approval_started = event_by_target.get("awaiting_approval")
    approval_ended = event_by_target.get("approved") or event_by_target.get(
        "rejected"
    )
    human_wait = (
        _milliseconds(approval_ended.created_at - approval_started.created_at)
        if approval_started and approval_ended else None
    )

    terminal_at = job.completed_at
    elapsed_end = terminal_at or now
    end_to_end = _milliseconds(elapsed_end - job.created_at)
    automated = end_to_end
    if human_wait is not None:
        automated = max(0.0, end_to_end - human_wait)

    timings = []
    for index, event in enumerate(events):
        if event.to_status not in {
            "analyzing", "generating_patch", "validating_patch", "creating_pr"
        }:
            continue
        end = (
            events[index + 1].created_at
            if index + 1 < len(events)
            else elapsed_end
        )
        timings.append(
            StageTiming(event.to_status, _milliseconds(end - event.created_at))
        )
    retry_count = sum(
        event.to_status == "retry_scheduled" for event in events
    )
    return WorkflowObservation(
        job=job,
        events=events,
        stage_timings=tuple(timings),
        queue_wait_ms=queue_wait,
        human_wait_ms=human_wait,
        automated_processing_ms=automated,
        end_to_end_ms=end_to_end,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_call_count=tool_call_count,
        retry_count=retry_count,
    )


def _milliseconds(delta):
    return round(max(0.0, delta.total_seconds() * 1000), 3)
