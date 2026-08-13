import time
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from virtual_staff_engineer.evaluation.metrics import percentile


SETTLED_STATUSES = frozenset(
    {"completed", "failed", "rejected", "cancelled", "awaiting_approval"}
)


def validate_concurrency_levels(levels):
    normalized = tuple(levels)
    if not normalized:
        raise ValueError("At least one concurrency level is required.")
    if any(
        isinstance(level, bool) or not isinstance(level, int) or level < 1
        for level in normalized
    ):
        raise ValueError("Concurrency levels must be positive integers.")
    if tuple(sorted(set(normalized))) != normalized:
        raise ValueError("Concurrency levels must be unique and increasing.")
    return normalized


def run_phase4_load_test(
    client,
    run_id,
    concurrency_levels=(1, 5, 10, 25),
    timeout_seconds=600,
    poll_seconds=1,
    max_failure_rate=0.2,
    max_attempts=5,
    progress_callback=None,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    levels = validate_concurrency_levels(concurrency_levels)
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string.")
    if timeout_seconds <= 0 or poll_seconds <= 0:
        raise ValueError("timeout_seconds and poll_seconds must be positive.")
    if not 0 <= max_failure_rate <= 1:
        raise ValueError("max_failure_rate must be between 0 and 1.")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        raise ValueError("max_attempts must be an integer.")
    if max_attempts < 1 or max_attempts > 100:
        raise ValueError("max_attempts must be between 1 and 100.")

    started_at = datetime.now(timezone.utc)
    waves = []
    aborted = False
    for level in levels:
        wave = _run_wave(
            client,
            run_id.strip(),
            level,
            timeout_seconds,
            poll_seconds,
            max_attempts,
            progress_callback,
            monotonic,
            sleep,
        )
        waves.append(wave)
        if wave["unexpected_failure_rate"] > max_failure_rate:
            aborted = True
            break
    completed_at = datetime.now(timezone.utc)
    return {
        "test_id": "phase4-load-v1",
        "run_id": run_id.strip(),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "configured_levels": list(levels),
        "completed_levels": [wave["concurrency"] for wave in waves],
        "max_failure_rate": max_failure_rate,
        "aborted": aborted,
        "waves": waves,
    }


def _run_wave(
    client,
    run_id,
    concurrency,
    timeout_seconds,
    poll_seconds,
    max_attempts,
    progress_callback,
    monotonic,
    sleep,
):
    started_clock = monotonic()
    health_latencies = []
    submission_results = []
    api_errors = []

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(
                _timed_submit,
                client,
                _payload(run_id, concurrency, index, max_attempts),
                monotonic,
            ): index
            for index in range(concurrency)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                submission_results.append(future.result())
            except Exception as exc:
                api_errors.append(
                    {"job_index": index, "operation": "submit", "error": str(exc)}
                )

    jobs = {
        result["workflow_job_id"]: {
            "job_index": result["job_index"],
            "workflow_job_id": result["workflow_job_id"],
            "submission_latency_ms": result["submission_latency_ms"],
        }
        for result in submission_results
    }
    pending = set(jobs)
    deadline = monotonic() + timeout_seconds
    while pending and monotonic() < deadline:
        health_latency = _timed_health(client, monotonic, api_errors)
        if health_latency is not None:
            health_latencies.append(health_latency)
        for job_id in tuple(pending):
            try:
                status = client.status(job_id)
            except Exception as exc:
                api_errors.append(
                    {
                        "job_index": jobs[job_id]["job_index"],
                        "operation": "status",
                        "error": str(exc),
                    }
                )
                continue
            if status["status"] in SETTLED_STATUSES:
                jobs[job_id].update(_job_metrics(status))
                pending.remove(job_id)
                if progress_callback:
                    progress_callback(
                        concurrency,
                        len(jobs) - len(pending),
                        len(jobs),
                        status["status"],
                    )
        if pending:
            sleep(poll_seconds)

    for job_id in pending:
        jobs[job_id].update(
            {"final_status": "timed_out", "unexpected_failure": True}
        )

    job_results = sorted(jobs.values(), key=lambda item: item["job_index"])
    successful = sum(
        item.get("final_status") == "completed" for item in job_results
    )
    unexpected = concurrency - successful
    denominator = concurrency
    duration_ms = round(max(0.0, monotonic() - started_clock) * 1000, 3)
    status_counts = Counter(
        item.get("final_status", "submission_failed") for item in job_results
    )
    submission_failures = concurrency - len(job_results)
    if submission_failures:
        status_counts["submission_failed"] += submission_failures
    return {
        "concurrency": concurrency,
        "submitted_count": len(submission_results),
        "completed_clean_count": successful,
        "api_error_count": len(api_errors),
        "unexpected_failure_count": unexpected,
        "unexpected_failure_rate": round(unexpected / denominator, 4),
        "duration_ms": duration_ms,
        "throughput_jobs_per_minute": (
            round(successful / (duration_ms / 60000), 3)
            if duration_ms > 0
            else None
        ),
        "terminal_status_counts": dict(sorted(status_counts.items())),
        "submission_latency_ms": _distribution(
            job_results, "submission_latency_ms"
        ),
        "health_latency_ms": _values_distribution(health_latencies),
        "queue_wait_ms": _distribution(job_results, "queue_wait_ms"),
        "automated_processing_ms": _distribution(
            job_results, "automated_processing_ms"
        ),
        "end_to_end_ms": _distribution(job_results, "end_to_end_ms"),
        "retry_count": sum(item.get("retry_count") or 0 for item in job_results),
        "input_tokens": sum(item.get("input_tokens") or 0 for item in job_results),
        "output_tokens": sum(
            item.get("output_tokens") or 0 for item in job_results
        ),
        "tool_call_count": sum(
            item.get("tool_call_count") or 0 for item in job_results
        ),
        "api_errors": api_errors,
        "jobs": job_results,
    }


def write_load_test_report(result, output_dir, overwrite=False):
    directory = Path(output_dir)
    json_path = directory / "results.json"
    markdown_path = directory / "report.md"
    existing = [path for path in (json_path, markdown_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing load-test files: "
            + ", ".join(str(path) for path in existing)
        )
    directory.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_render_markdown(result), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _render_markdown(result):
    lines = [
        "# Phase 4 Concurrent Load Test",
        "",
        f"- Run ID: `{result['run_id']}`",
        f"- Configured levels: {', '.join(map(str, result['configured_levels']))}",
        f"- Completed levels: {', '.join(map(str, result['completed_levels']))}",
        f"- Safety abort triggered: {'yes' if result['aborted'] else 'no'}",
        "",
        "## Wave comparison",
        "",
        "| Concurrent jobs | Clean | Unexpected | Submit p95 ms | Health p95 ms | Queue p95 ms | Processing p95 ms | Throughput jobs/min | Retries |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for wave in result["waves"]:
        lines.append(
            f"| {wave['concurrency']} | {wave['completed_clean_count']} | "
            f"{wave['unexpected_failure_count']} | "
            f"{_value(wave['submission_latency_ms']['p95'])} | "
            f"{_value(wave['health_latency_ms']['p95'])} | "
            f"{_value(wave['queue_wait_ms']['p95'])} | "
            f"{_value(wave['automated_processing_ms']['p95'])} | "
            f"{_value(wave['throughput_jobs_per_minute'])} | "
            f"{wave['retry_count']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "The test uses clean design inputs and never approves patches or calls "
            "GitHub. It measures the API/PostgreSQL queue/single-worker path. "
            "Provider quotas can become the measured bottleneck and must be reported "
            "separately from application defects.",
            "",
        ]
    )
    return "\n".join(lines)


def _value(value):
    return "N/A" if value is None else str(value)


def _payload(run_id, concurrency, index, max_attempts):
    return {
        "input_type": "design_document",
        "source_path": f"load/wave-{concurrency}/design-{index}.md",
        "content": (
            "The API validates authentication tokens and verifies resource "
            "ownership before returning customer invoices."
        ),
        "idempotency_key": (
            f"phase4-load:{run_id}:wave-{concurrency}:job-{index}"
        ),
        "max_attempts": max_attempts,
    }


def _timed_submit(client, payload, monotonic):
    started = monotonic()
    response = client.submit(payload)
    return {
        "job_index": int(payload["source_path"].rsplit("-", 1)[1].split(".")[0]),
        "workflow_job_id": response["workflow_job_id"],
        "submission_latency_ms": round((monotonic() - started) * 1000, 3),
    }


def _timed_health(client, monotonic, errors):
    started = monotonic()
    try:
        response = client.health()
        if response.get("status") != "ok":
            raise RuntimeError("health response was not status=ok")
        return round((monotonic() - started) * 1000, 3)
    except Exception as exc:
        errors.append({"job_index": None, "operation": "health", "error": str(exc)})
        return None


def _job_metrics(status):
    final_status = status["status"]
    return {
        "final_status": final_status,
        "failure_code": status.get("failure_code"),
        "unexpected_failure": final_status != "completed",
        "queue_wait_ms": status.get("queue_wait_ms"),
        "automated_processing_ms": status.get("automated_processing_ms"),
        "end_to_end_ms": status.get("end_to_end_ms"),
        "retry_count": status.get("retry_count"),
        "input_tokens": status.get("input_tokens"),
        "output_tokens": status.get("output_tokens"),
        "tool_call_count": status.get("tool_call_count"),
        "stage_timings": status.get("stage_timings", []),
    }


def _distribution(items, field):
    return _values_distribution(
        [item.get(field) for item in items if _is_number(item.get(field))]
    )


def _values_distribution(values):
    if not values:
        return {"sample_count": 0, "mean": None, "p50": None, "p95": None}
    return {
        "sample_count": len(values),
        "mean": round(sum(values) / len(values), 3),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
    }


def _is_number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float))
