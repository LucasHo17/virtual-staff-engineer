import json
from pathlib import Path

from virtual_staff_engineer.evaluation.report import (
    report_paths,
    validate_report_destination,
)


def write_analysis_reports(result, output_dir, overwrite=False):
    """Write Phase 2 machine-readable and review-friendly reports."""
    paths = validate_report_destination(output_dir, overwrite=overwrite)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["markdown"].write_text(
        render_analysis_markdown(result),
        encoding="utf-8",
    )
    return {name: str(path) for name, path in paths.items()}


def render_analysis_markdown(result):
    summary = result["summary"]
    quality = summary["quality"]
    safety = summary["safety"]
    workflow = summary["workflow"]
    usage = summary["usage"]
    latency = summary["latency_ms"]
    thinking_budget = result["config"]["thinking_budget"]
    thinking_description = (
        "model default"
        if thinking_budget is None
        else f"{thinking_budget} tokens/call"
    )
    lines = [
        "# Phase 2 Agent Evaluation",
        "",
        f"- Run status: **{result['run_status']}**",
        f"- Generated: `{result['generated_at']}`",
        f"- Dataset: `{result['dataset']['dataset_id']}` "
        f"({result['dataset']['selected_case_count']}/"
        f"{result['dataset']['total_case_count']} cases)",
        f"- Model: `{result['config']['model']}`",
        f"- Thinking budget: {thinking_description}",
        f"- Delay between cases: "
        f"{result['config']['case_delay_seconds']:.1f} seconds",
        f"- Corpus: `{result['corpus']['filename']}` version "
        f"{result['corpus']['version']}",
        "",
        "## Quality",
        "",
        "| Precision | Recall | F1 | Exact rules | Status accuracy |",
        "|---|---|---|---|---|",
        f"| {_fmt(quality['precision'])} | {_fmt(quality['recall'])} | "
        f"{_fmt(quality['f1'])} | {_fmt(quality['exact_rule_accuracy'])} | "
        f"{_fmt(quality['status_accuracy'])} |",
        "",
        "| Violating detection | Clean FP | Irrelevant FP | "
        "Ambiguous inconclusive |",
        "|---|---|---|---|",
        f"| {_fmt(quality['violating_detection_rate'])} | "
        f"{_fmt(quality['clean_false_positive_rate'])} | "
        f"{_fmt(quality['irrelevant_false_positive_rate'])} | "
        f"{_fmt(quality['ambiguous_inconclusive_rate'])} |",
        "",
        "## Safety and workflow",
        "",
        f"- Deterministic rejection rate: "
        f"{_fmt(safety['deterministic_rejection_rate'])} "
        f"({safety['deterministic_rejection_count']} proposals)",
        f"- Evaluator unsupported rate: "
        f"{_fmt(safety['unsupported_decision_rate'])} "
        f"({safety['unsupported_decision_count']} decisions)",
        f"- Average queries: {workflow['average_queries']:.2f}",
        f"- Average iterations: {workflow['average_iterations']:.2f}",
        f"- Latency p50/p95: {latency['p50']:.2f} / "
        f"{latency['p95']:.2f} ms",
        f"- Model calls: {usage['model_calls']}",
        f"- Input/output/thinking tokens: {usage['input_tokens']} / "
        f"{usage['output_tokens']} / {usage['thinking_tokens']}",
        f"- Embedding requests: {usage['embedding_requests']}",
        f"- Estimated reasoning cost: "
        f"${usage['estimated_reasoning_cost_usd']:.6f}",
        "",
        "The cost estimate uses the explicit per-million-token rates recorded "
        "in the report configuration. Embedding cost is not included.",
        "",
        "## Results by case type",
        "",
        "| Type | Cases | Status accuracy | Exact rules | FP rate | "
        "Inconclusive rate |",
        "|---|---|---|---|---|---|",
    ]
    for case_type, values in summary["by_case_type"].items():
        lines.append(
            f"| {case_type} | {values['case_count']} | "
            f"{_fmt(values['status_accuracy'])} | "
            f"{_fmt(values['exact_rule_accuracy'])} | "
            f"{_fmt(values['false_positive_rate'])} | "
            f"{_fmt(values['inconclusive_rate'])} |"
        )

    lines.extend(["", "## Case results", ""])
    failures = 0
    for case in result["cases"]:
        passed = (
            case["metrics"]["exact_rule_match"]
            and case["metrics"]["status_match"]
        )
        if not passed:
            failures += 1
        lines.extend(
            [
                f"### {case['case_id']} — "
                f"{'PASS' if passed else 'FAIL'}",
                "",
                f"- Type: `{case['case_type']}`",
                f"- Expected status/rules: `{case['expected_status']}` / "
                f"`{', '.join(case['expected_rule_keys']) or 'none'}`",
                f"- Actual status/rules: `{case['actual_status']}` / "
                f"`{', '.join(case['actual_rule_keys']) or 'none'}`",
                f"- Queries/iterations: {case['query_count']} / "
                f"{case['iterations']}",
                f"- Latency: {case['latency_ms']:.2f} ms",
            ]
        )
        if case["inconclusive_reason"]:
            lines.append(
                f"- Inconclusive reason: {case['inconclusive_reason']}"
            )
        lines.append("")

    lines.insert(
        lines.index("## Case results") - 1,
        f"Overall case failures: **{failures}**",
    )
    return "\n".join(lines)


def _fmt(value):
    return f"{value:.3f}"
