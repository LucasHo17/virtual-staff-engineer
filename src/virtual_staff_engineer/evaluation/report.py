import json
from pathlib import Path


def report_paths(output_dir):
    """Return the two deterministic report paths for one benchmark run."""
    directory = Path(output_dir)
    return {
        "json": directory / "results.json",
        "markdown": directory / "report.md",
    }


def validate_report_destination(output_dir, overwrite=False):
    """Fail before expensive retrieval work if reports would be overwritten."""
    paths = report_paths(output_dir)
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing report files: "
            + ", ".join(str(path) for path in existing)
        )
    return paths


def write_reports(result, output_dir, overwrite=False):
    """Write machine-readable results and a concise human-readable report."""
    paths = validate_report_destination(output_dir, overwrite=overwrite)
    directory = Path(output_dir)
    markdown = _render_markdown(result)
    directory.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths["markdown"].write_text(markdown, encoding="utf-8")
    return {name: str(path) for name, path in paths.items()}


def _render_markdown(result):
    config = result["config"]
    cutoffs = config["cutoffs"]
    largest_cutoff = str(max(cutoffs))
    lines = [
        "# Phase 1 Retrieval Evaluation",
        "",
        f"- Run status: **{result['run_status']}**",
        f"- Generated: `{result['generated_at']}`",
        f"- Dataset: `{result['dataset']['dataset_id']}` "
        f"({result['dataset']['selected_case_count']}/"
        f"{result['dataset']['total_case_count']} cases)",
        f"- Corpus: `{result['corpus']['filename']}` version "
        f"{result['corpus']['version']} ({result['corpus']['chunk_count']} chunks)",
        f"- Embedding requests: {result['usage']['embedding_requests']}",
        f"- Candidate pool: {config['candidate_k']}",
        "",
        "## Overall results",
        "",
        _summary_table(result["summary"]["overall"], cutoffs),
        "",
        "Precision@K uses K as the denominator. Negative cases are reported "
        "separately through false-positive rate.",
        "",
        "## Results by query type",
        "",
    ]

    for method, query_types in result["summary"]["by_query_type"].items():
        lines.extend(
            [
                f"### {method.title()}",
                "",
                _query_type_table(query_types, cutoffs),
                "",
            ]
        )

    rank_one_misses = _rank_one_miss_rows(result["cases"])
    lines.extend(["## Rank-1 misses", ""])
    if rank_one_misses:
        lines.extend(
            [
                "| Case | Type | Method | Expected | Rank 1 | First expected rank |",
                "|---|---|---|---|---|---|",
                *rank_one_misses,
            ]
        )
    else:
        lines.append("Every positive case has an expected rule at rank 1.")
    lines.append("")

    failures = _failure_rows(result["cases"], largest_cutoff)
    lines.extend([f"## Cases failing at K={largest_cutoff}", ""])
    if failures:
        lines.extend(
            [
                "| Case | Type | Method | Expected | Retrieved | Issue |",
                "|---|---|---|---|---|---|",
                *failures,
            ]
        )
    else:
        lines.append(f"No failures at K={largest_cutoff}.")
    lines.append("")
    return "\n".join(lines)


def _rank_one_miss_rows(cases):
    rows = []
    for case in cases:
        expected_keys = case["expected_rule_keys"]
        if not expected_keys:
            continue
        expected = set(expected_keys)
        for method, method_result in case["methods"].items():
            ranked = method_result["ranked_rule_keys"]
            if ranked and ranked[0] in expected:
                continue
            first_expected_rank = next(
                (
                    rank
                    for rank, rule_key in enumerate(ranked, start=1)
                    if rule_key in expected
                ),
                None,
            )
            rows.append(
                f"| {case['case_id']} | {case['query_type']} | {method} | "
                f"{', '.join(expected_keys)} | "
                f"{ranked[0] if ranked else 'none'} | "
                f"{first_expected_rank if first_expected_rank else 'not retrieved'} |"
            )
    return rows


def _summary_table(method_summaries, cutoffs):
    metric_headers = []
    for cutoff in cutoffs:
        metric_headers.extend(
            [f"R@{cutoff}", f"P@{cutoff}", f"Hit@{cutoff}"]
        )
    headers = [
        "Method",
        *metric_headers,
        "MRR",
        f"Negative FP@{max(cutoffs)}",
        "p50 ms",
        "p95 ms",
    ]
    rows = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for method, summary in method_summaries.items():
        quality = summary["quality"]
        values = [method]
        for cutoff in cutoffs:
            key = str(cutoff)
            values.extend(
                [
                    _format(quality["recall_at_k"][key]),
                    _format(quality["precision_at_k"][key]),
                    _format(quality["hit_rate_at_k"][key]),
                ]
            )
        values.extend(
            [
                _format(quality["mrr"]),
                _format(
                    summary["negative_quality"]["false_positive_rate_at_k"][
                        str(max(cutoffs))
                    ]
                ),
                _format(summary["latency_ms"]["p50"], digits=2),
                _format(summary["latency_ms"]["p95"], digits=2),
            ]
        )
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def _query_type_table(query_types, cutoffs):
    largest = str(max(cutoffs))
    headers = ["Query type", "Cases", f"Recall@{largest}", "MRR", f"FP@{largest}", "p95 ms"]
    rows = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for query_type, summary in query_types.items():
        rows.append(
            "| "
            + " | ".join(
                [
                    query_type,
                    str(summary["case_count"]),
                    _format(summary["quality"]["recall_at_k"][largest]),
                    _format(summary["quality"]["mrr"]),
                    _format(
                        summary["negative_quality"]["false_positive_rate_at_k"][largest]
                    ),
                    _format(summary["latency_ms"]["p95"], digits=2),
                ]
            )
            + " |"
        )
    return "\n".join(rows)


def _failure_rows(cases, cutoff):
    rows = []
    for case in cases:
        expected = ", ".join(case["expected_rule_keys"]) or "none"
        for method, method_result in case["methods"].items():
            metrics = method_result["metrics"]
            if metrics["is_negative"]:
                failed = metrics["false_positive_at_k"][cutoff] == 1
                issue = "false positive"
            else:
                failed = metrics["recall_at_k"][cutoff] < 1
                issue = "missing expected rule"
            if not failed:
                continue
            retrieved = ", ".join(
                method_result["ranked_rule_keys"][: int(cutoff)]
            ) or "none"
            rows.append(
                f"| {case['case_id']} | {case['query_type']} | {method} | "
                f"{expected} | {retrieved} | {issue} |"
            )
    return rows


def _format(value, digits=3):
    if value is None:
        return "—"
    return f"{value:.{digits}f}"
