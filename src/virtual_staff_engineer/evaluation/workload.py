import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from virtual_staff_engineer.evaluation.dataset import DatasetValidationError


INPUT_TYPES = frozenset({"code_diff", "design_document"})
EXPECTED_STATUSES = frozenset(
    {"completed", "failed", "awaiting_approval", "rejected"}
)
TERMINAL_STATUSES = frozenset({"completed", "failed", "rejected", "cancelled"})


@dataclass(frozen=True)
class Phase4WorkloadCase:
    case_id: str
    scenario: str
    input_type: str
    source_path: str
    content: str
    expected_ready_status: str
    expected_failure_code: Optional[str]
    decision: Optional[str]
    expected_final_status: str


@dataclass(frozen=True)
class Phase4Workload:
    workload_id: str
    status: str
    required_source_files: tuple
    cases: tuple
    deterministic_coverage: dict
    source_path: str


class WorkloadCaseFailed(RuntimeError):
    """A live workload case did not reach its labeled outcome."""


def load_phase4_workload(file_path, require_frozen=True):
    path = Path(file_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(
            f"Could not load Phase 4 workload {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise DatasetValidationError("Workload root must be a JSON object.")

    workload_id = _text(payload, "workload_id", "workload")
    status = _text(payload, "status", "workload")
    if status not in {"draft", "frozen"}:
        raise DatasetValidationError(
            "workload.status must be either 'draft' or 'frozen'."
        )
    if require_frozen and status != "frozen":
        raise DatasetValidationError(
            f"Workload status must be 'frozen', received {status!r}."
        )

    required_source_files = _string_list(
        payload, "required_source_files", "workload"
    )
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise DatasetValidationError("Workload cases must be a non-empty array.")
    cases = []
    seen_ids = set()
    for index, item in enumerate(raw_cases):
        location = f"cases[{index}]"
        if not isinstance(item, dict):
            raise DatasetValidationError(f"{location} must be an object.")
        case = _load_case(item, location)
        if case.case_id in seen_ids:
            raise DatasetValidationError(f"Duplicate case id: {case.case_id}.")
        seen_ids.add(case.case_id)
        cases.append(case)

    coverage = payload.get("deterministic_coverage")
    if not isinstance(coverage, dict) or not coverage:
        raise DatasetValidationError(
            "deterministic_coverage must be a non-empty object."
        )
    for scenario, paths in coverage.items():
        if not isinstance(scenario, str) or not scenario.strip():
            raise DatasetValidationError(
                "deterministic_coverage keys must be non-empty strings."
            )
        if not isinstance(paths, list) or not paths or not all(
            isinstance(value, str) and value.strip() for value in paths
        ):
            raise DatasetValidationError(
                f"deterministic_coverage.{scenario} must list test paths."
            )

    return Phase4Workload(
        workload_id=workload_id,
        status=status,
        required_source_files=required_source_files,
        cases=tuple(cases),
        deterministic_coverage=coverage,
        source_path=str(path),
    )


def verify_workload_source(workload, repository_root):
    root = Path(repository_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Repository root does not exist: {root}")
    missing = [
        value
        for value in workload.required_source_files
        if not (root / value).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Required workload source files are missing: " + ", ".join(missing)
        )
    return root


def run_phase4_workload(
    workload,
    client,
    run_id,
    timeout_seconds=300,
    poll_seconds=1,
    progress_callback=None,
    status_callback=None,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string.")
    if timeout_seconds <= 0 or poll_seconds <= 0:
        raise ValueError("timeout_seconds and poll_seconds must be positive.")
    started_at = datetime.now(timezone.utc)
    started_clock = monotonic()
    results = []
    for case in workload.cases:
        submitted = client.submit(
            {
                "input_type": case.input_type,
                "source_path": case.source_path,
                "content": case.content,
                "idempotency_key": (
                    f"phase4-workload:{workload.workload_id}:"
                    f"{run_id.strip()}:{case.case_id}"
                ),
            }
        )
        job_id = submitted["workflow_job_id"]
        if status_callback:
            status_callback(case.case_id, job_id, "submitted")
        ready = _wait_for_status(
            client,
            job_id,
            case.expected_ready_status,
            timeout_seconds,
            poll_seconds,
            monotonic,
            sleep,
            alternate_status=(
                case.expected_final_status if case.decision else None
            ),
            status_callback=(
                (lambda value, case_id=case.case_id: status_callback(
                    case_id, job_id, value
                ))
                if status_callback
                else None
            ),
        )
        if ready.get("failure_code") != case.expected_failure_code:
            raise WorkloadCaseFailed(
                f"{case.case_id} expected failure_code "
                f"{case.expected_failure_code!r}, received "
                f"{ready.get('failure_code')!r}."
            )

        review = None
        final = ready
        if case.decision and ready["status"] != case.expected_final_status:
            review = client.review(job_id)
            client.decide(
                job_id,
                {"decision": case.decision, "comment": "Phase 4 workload."},
            )
            final = _wait_for_status(
                client,
                job_id,
                case.expected_final_status,
                timeout_seconds,
                poll_seconds,
                monotonic,
                sleep,
                status_callback=(
                    (lambda value, case_id=case.case_id: status_callback(
                        case_id, job_id, value
                    ))
                    if status_callback
                    else None
                ),
            )
        elif ready["status"] != case.expected_final_status:
            raise WorkloadCaseFailed(
                f"{case.case_id} expected final status "
                f"{case.expected_final_status!r}, received {ready['status']!r}."
            )

        result = {
            "case_id": case.case_id,
            "scenario": case.scenario,
            "workflow_job_id": job_id,
            "passed": True,
            "ready_status": ready["status"],
            "final_status": final["status"],
            "failure_code": final.get("failure_code"),
            "attempt_count": final.get("attempt_count"),
            "retry_count": final.get("retry_count"),
            "queue_wait_ms": final.get("queue_wait_ms"),
            "automated_processing_ms": final.get("automated_processing_ms"),
            "human_wait_ms": final.get("human_wait_ms"),
            "end_to_end_ms": final.get("end_to_end_ms"),
            "input_tokens": final.get("input_tokens"),
            "output_tokens": final.get("output_tokens"),
            "tool_call_count": final.get("tool_call_count"),
            "estimated_analysis_cost_usd": final.get(
                "estimated_analysis_cost_usd"
            ),
            "stage_timings": final.get("stage_timings", []),
            "review_rule_keys": (
                [item["rule_key"] for item in review.get("rules", [])]
                if review
                else []
            ),
        }
        results.append(result)
        if progress_callback:
            progress_callback(result, len(results), len(workload.cases))
    completed_at = datetime.now(timezone.utc)
    duration_ms = round(max(0.0, monotonic() - started_clock) * 1000, 3)
    return {
        "workload_id": workload.workload_id,
        "run_id": run_id.strip(),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_ms": duration_ms,
        "case_count": len(results),
        "passed_count": len(results),
        "cases": results,
    }


def _wait_for_status(
    client,
    job_id,
    expected,
    timeout_seconds,
    poll_seconds,
    monotonic,
    sleep,
    alternate_status=None,
    status_callback=None,
):
    deadline = monotonic() + timeout_seconds
    previous = None
    while True:
        status = client.status(job_id)
        current = status["status"]
        if current != previous and status_callback:
            status_callback(current)
        previous = current
        if current == expected:
            return status
        if alternate_status is not None and current == alternate_status:
            return status
        if current in TERMINAL_STATUSES:
            raise WorkloadCaseFailed(
                f"Job {job_id} reached {current!r}; expected {expected!r}."
            )
        if monotonic() >= deadline:
            raise WorkloadCaseFailed(
                f"Job {job_id} timed out in {current!r}; expected {expected!r}."
            )
        sleep(poll_seconds)


def _load_case(payload, location):
    input_type = _text(payload, "input_type", location)
    if input_type not in INPUT_TYPES:
        raise DatasetValidationError(
            f"{location}.input_type must be one of {sorted(INPUT_TYPES)}."
        )
    ready = _text(payload, "expected_ready_status", location)
    final = _text(payload, "expected_final_status", location)
    if ready not in EXPECTED_STATUSES or final not in EXPECTED_STATUSES:
        raise DatasetValidationError(
            f"{location} contains an unsupported expected status."
        )
    decision = payload.get("decision")
    if decision is not None and decision != "rejected":
        raise DatasetValidationError(
            f"{location}.decision must be null or 'rejected'."
        )
    if decision and (ready != "awaiting_approval" or final != decision):
        raise DatasetValidationError(
            f"{location} decision cases must await approval then match decision."
        )
    failure = payload.get("expected_failure_code")
    if failure is not None and (
        not isinstance(failure, str) or not failure.strip()
    ):
        raise DatasetValidationError(
            f"{location}.expected_failure_code must be null or text."
        )
    return Phase4WorkloadCase(
        case_id=_text(payload, "id", location),
        scenario=_text(payload, "scenario", location),
        input_type=input_type,
        source_path=_text(payload, "source_path", location),
        content=_text(payload, "content", location, strip=False),
        expected_ready_status=ready,
        expected_failure_code=failure,
        decision=decision,
        expected_final_status=final,
    )


def _text(payload, key, location, strip=True):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(
            f"{location}.{key} must be a non-empty string."
        )
    return value.strip() if strip else value


def _string_list(payload, key, location):
    values = payload.get(key)
    if not isinstance(values, list) or not values or not all(
        isinstance(value, str) and value.strip() for value in values
    ):
        raise DatasetValidationError(
            f"{location}.{key} must be a non-empty string array."
        )
    return tuple(value.strip() for value in values)
