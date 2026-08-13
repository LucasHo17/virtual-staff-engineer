import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from virtual_staff_engineer.evaluation.metrics import percentile


def load_workload_runs(paths):
    runs = []
    for value in paths:
        path = Path(value)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not load workload result {path}: {exc}") from exc
        _validate_run(payload, path)
        payload["source_path"] = str(path)
        runs.append(payload)
    workload_ids = {run["workload_id"] for run in runs}
    if len(workload_ids) != 1:
        raise ValueError("All baseline runs must use the same workload_id.")
    return tuple(runs)


def aggregate_phase4_baseline(runs):
    if not runs:
        raise ValueError("At least one workload run is required.")
    cases = [case for run in runs for case in run["cases"]]
    passed = sum(case["passed"] is True for case in cases)
    expected_blocks = sum(
        case.get("failure_code") is not None and case["passed"] is True
        for case in cases
    )
    unexpected_failures = sum(case["passed"] is not True for case in cases)
    run_durations = [
        run.get("duration_ms")
        for run in runs
        if _number_or_none(run.get("duration_ms")) is not None
    ]
    total_duration_ms = sum(run_durations) if run_durations else None
    throughput = (
        round(len(cases) / (total_duration_ms / 60000), 3)
        if total_duration_ms and total_duration_ms > 0
        else None
    )
    retry_values = [
        case.get("retry_count")
        for case in cases
        if isinstance(case.get("retry_count"), int)
    ]
    retry_case_count = sum(value > 0 for value in retry_values)
    retry_recovered_count = sum(
        isinstance(case.get("retry_count"), int)
        and case["retry_count"] > 0
        and case["passed"] is True
        for case in cases
    )
    costs = [
        case.get("estimated_analysis_cost_usd")
        for case in cases
        if _number_or_none(case.get("estimated_analysis_cost_usd")) is not None
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workload_id": runs[0]["workload_id"],
        "source_runs": [run["source_path"] for run in runs],
        "sample": {
            "run_count": len(runs),
            "job_count": len(cases),
            "small_sample_warning": len(cases) < 20,
        },
        "outcomes": {
            "workload_acceptance_rate": _ratio(passed, len(cases)),
            "passed_count": passed,
            "expected_safety_block_count": expected_blocks,
            "unexpected_failure_count": unexpected_failures,
            "terminal_status_counts": dict(
                sorted(Counter(case["final_status"] for case in cases).items())
            ),
        },
        "latency_ms": {
            "queue_wait": _distribution(cases, "queue_wait_ms"),
            "automated_processing": _distribution(
                cases, "automated_processing_ms"
            ),
            "human_wait": _distribution(cases, "human_wait_ms"),
            "end_to_end": _distribution(cases, "end_to_end_ms"),
        },
        "throughput": {
            "measured_run_count": len(run_durations),
            "jobs_per_minute": throughput,
        },
        "retries": {
            "measured_job_count": len(retry_values),
            "jobs_with_retry": retry_case_count if retry_values else None,
            "retry_recovery_rate": (
                _ratio(retry_recovered_count, retry_case_count)
                if retry_case_count
                else None
            ),
        },
        "usage": {
            "input_tokens": sum(case.get("input_tokens") or 0 for case in cases),
            "output_tokens": sum(
                case.get("output_tokens") or 0 for case in cases
            ),
            "tool_calls": sum(
                case.get("tool_call_count") or 0 for case in cases
            ),
            "estimated_analysis_cost_usd": (
                round(sum(costs), 8) if len(costs) == len(cases) else None
            ),
            "costed_job_count": len(costs),
        },
    }


def write_phase4_baseline(result, output_dir, overwrite=False):
    directory = Path(output_dir)
    json_path = directory / "results.json"
    markdown_path = directory / "report.md"
    existing = [path for path in (json_path, markdown_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing baseline files: "
            + ", ".join(str(path) for path in existing)
        )
    directory.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    markdown_path.write_text(_render_markdown(result), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _validate_run(payload, path):
    if not isinstance(payload, dict):
        raise ValueError(f"Workload result root must be an object: {path}")
    for field in ("workload_id", "run_id", "case_count", "passed_count", "cases"):
        if field not in payload:
            raise ValueError(f"Workload result is missing {field}: {path}")
    if not isinstance(payload["cases"], list) or not payload["cases"]:
        raise ValueError(f"Workload result cases must be non-empty: {path}")
    if payload["case_count"] != len(payload["cases"]):
        raise ValueError(f"Workload result case_count is inconsistent: {path}")
    required_case_fields = {
        "case_id", "scenario", "passed", "final_status", "workflow_job_id"
    }
    for case in payload["cases"]:
        if not isinstance(case, dict) or not required_case_fields.issubset(case):
            raise ValueError(f"Workload result contains an invalid case: {path}")


def _distribution(cases, field):
    values = [
        case.get(field)
        for case in cases
        if _number_or_none(case.get(field)) is not None
    ]
    if not values:
        return {"sample_count": 0, "mean": None, "p50": None, "p95": None}
    return {
        "sample_count": len(values),
        "mean": round(sum(values) / len(values), 3),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
    }


def _number_or_none(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def _render_markdown(result):
    sample = result["sample"]
    outcomes = result["outcomes"]
    latency = result["latency_ms"]
    retries = result["retries"]
    usage = result["usage"]
    lines = [
        "# Phase 4 Baseline",
        "",
        f"- Workload: `{result['workload_id']}`",
        f"- Runs: {sample['run_count']}",
        f"- Jobs: {sample['job_count']}",
        f"- Workload acceptance: {_percent(outcomes['workload_acceptance_rate'])}",
        f"- Unexpected failures: {outcomes['unexpected_failure_count']}",
        f"- Expected safety blocks: {outcomes['expected_safety_block_count']}",
        "",
    ]
    if sample["small_sample_warning"]:
        lines.extend(
            [
                "> This is an exploratory smoke baseline with fewer than 20 jobs. "
                "Its p95 values are directional, not statistically stable.",
                "",
            ]
        )
    lines.extend(
        [
            "## Latency",
            "",
            "| Metric | Samples | Mean ms | p50 ms | p95 ms |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for label, key in (
        ("Queue wait", "queue_wait"),
        ("Automated processing", "automated_processing"),
        ("Human wait", "human_wait"),
        ("End to end", "end_to_end"),
    ):
        item = latency[key]
        lines.append(
            f"| {label} | {item['sample_count']} | {_value(item['mean'])} | "
            f"{_value(item['p50'])} | {_value(item['p95'])} |"
        )
    lines.extend(
        [
            "",
            "## Throughput, retries, and usage",
            "",
            f"- Jobs/minute: {_value(result['throughput']['jobs_per_minute'])}",
            f"- Jobs with retry: {_value(retries['jobs_with_retry'])}",
            f"- Retry recovery rate: {_percent(retries['retry_recovery_rate'])}",
            f"- Input tokens: {usage['input_tokens']}",
            f"- Output tokens: {usage['output_tokens']}",
            f"- Retrieval tool calls: {usage['tool_calls']}",
            f"- Estimated analysis cost: {_cost(usage['estimated_analysis_cost_usd'])}",
            "",
            "`attempt_count` is not reported as retries because it counts worker "
            "stage claims. Retry metrics use explicit `retry_scheduled` transitions.",
            "",
        ]
    )
    return "\n".join(lines)


def _value(value):
    return "N/A" if value is None else str(value)


def _percent(value):
    return "N/A" if value is None else f"{value * 100:.2f}%"


def _cost(value):
    return "N/A" if value is None else f"${value:.8f}"
