import json
import re
from pathlib import Path

from virtual_staff_engineer.evaluation.metrics import (
    aggregate_metrics,
    evaluate_ranking,
)


DEFAULT_THRESHOLDS = tuple(round(value / 100, 2) for value in range(50, 76))
DEFAULT_LEXICAL_WEIGHTS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
LEXICAL_POLICIES = ("all", "confident", "explicit_only")


def load_benchmark_results(file_path):
    path = Path(file_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not load benchmark results {path}: {error}") from error
    _validate_results(payload)
    return payload


def analyze_optimization(
    results,
    thresholds=DEFAULT_THRESHOLDS,
    lexical_weights=DEFAULT_LEXICAL_WEIGHTS,
    strong_trigram_threshold=0.3,
    locked_policy=None,
):
    """Replay saved rankings without database or embedding API calls."""
    _validate_results(results)
    cutoffs = tuple(results["config"]["cutoffs"])
    rrf_k = results["config"]["rrf_k"]
    threshold_rows = [
        _evaluate_policy(
            results["cases"],
            cutoffs,
            semantic_threshold=threshold,
            lexical_weight=0,
            rrf_k=rrf_k,
            lexical_policy="all",
            strong_trigram_threshold=strong_trigram_threshold,
        )
        for threshold in thresholds
    ]
    fusion_rows = []
    for policy in LEXICAL_POLICIES:
        for lexical_weight in lexical_weights:
            row = _evaluate_policy(
                results["cases"],
                cutoffs,
                semantic_threshold=None,
                lexical_weight=lexical_weight,
                rrf_k=rrf_k,
                lexical_policy=policy,
                strong_trigram_threshold=strong_trigram_threshold,
            )
            fusion_rows.append(row)

    baseline = _baseline_summary(results)
    threshold_recommendation = None
    fusion_recommendation = None
    combined_recommendation = None
    locked_result = None
    if locked_policy is not None:
        locked_result = _evaluate_policy(
            results["cases"],
            cutoffs,
            semantic_threshold=locked_policy["semantic_threshold"],
            lexical_weight=locked_policy["lexical_weight"],
            rrf_k=rrf_k,
            lexical_policy=locked_policy["lexical_policy"],
            strong_trigram_threshold=strong_trigram_threshold,
        )
    else:
        threshold_recommendation = _recommend_threshold(
            threshold_rows,
            baseline,
            cutoffs,
        )
        fusion_recommendation = _recommend_fusion(
            fusion_rows,
            baseline,
            cutoffs,
        )
    if threshold_recommendation and fusion_recommendation:
        combined_recommendation = _evaluate_policy(
            results["cases"],
            cutoffs,
            semantic_threshold=threshold_recommendation["semantic_threshold"],
            lexical_weight=fusion_recommendation["lexical_weight"],
            rrf_k=rrf_k,
            lexical_policy=fusion_recommendation["lexical_policy"],
            strong_trigram_threshold=strong_trigram_threshold,
        )
    return {
        "source": {
            "generated_at": results["generated_at"],
            "dataset_id": results["dataset"]["dataset_id"],
            "case_count": len(results["cases"]),
            "results_path": results["dataset"].get("source_path"),
        },
        "analysis_mode": "holdout" if locked_policy else "development",
        "config": {
            "cutoffs": list(cutoffs),
            "thresholds": list(thresholds),
            "lexical_weights": list(lexical_weights),
            "strong_trigram_threshold": strong_trigram_threshold,
            "rrf_k": rrf_k,
        },
        "baseline": baseline,
        "threshold_sweep": threshold_rows,
        "fusion_sweep": fusion_rows,
        "recommendations": {
            "threshold": threshold_recommendation,
            "fusion": fusion_recommendation,
            "combined": combined_recommendation,
            "locked": locked_result,
        },
    }


def write_optimization_reports(analysis, output_dir, overwrite=False):
    directory = Path(output_dir)
    json_path = directory / "optimization.json"
    markdown_path = directory / "optimization.md"
    existing = [path for path in (json_path, markdown_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing optimization reports: "
            + ", ".join(str(path) for path in existing)
        )
    markdown = _render_optimization_markdown(analysis)
    directory.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(markdown, encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def _evaluate_policy(
    cases,
    cutoffs,
    semantic_threshold,
    lexical_weight,
    rrf_k,
    lexical_policy,
    strong_trigram_threshold,
):
    evaluated = []
    changed_cases = []
    for case in cases:
        semantic_candidates = [
            candidate
            for candidate in case["methods"]["semantic"]["candidates"]
            if semantic_threshold is None
            or candidate["similarity_score"] >= semantic_threshold
        ]
        lexical_candidates = _filter_lexical_candidates(
            case["query"],
            case["methods"]["lexical"]["candidates"],
            lexical_policy,
            strong_trigram_threshold,
        )
        ranked = _offline_rrf(
            semantic_candidates,
            lexical_candidates,
            rrf_k=rrf_k,
            semantic_weight=1.0,
            lexical_weight=lexical_weight,
        )
        baseline_ranked = case["methods"]["semantic"]["ranked_rule_keys"]
        if ranked[: max(cutoffs)] != baseline_ranked[: max(cutoffs)]:
            changed_cases.append(case["case_id"])
        evaluated.append(
            {
                "latency_ms": 0,
                "metrics": evaluate_ranking(
                    case["expected_rule_keys"],
                    ranked,
                    cutoffs,
                ),
            }
        )

    summary = aggregate_metrics(evaluated, cutoffs)
    summary.pop("latency_ms")
    return {
        "semantic_threshold": semantic_threshold,
        "lexical_weight": lexical_weight,
        "lexical_policy": lexical_policy,
        "changed_case_count": len(changed_cases),
        "changed_case_ids": changed_cases,
        "summary": summary,
    }


def _filter_lexical_candidates(query, candidates, policy, strong_threshold):
    if policy not in LEXICAL_POLICIES:
        raise ValueError(f"Unknown lexical policy: {policy}.")
    if policy == "all":
        return list(candidates)

    filtered = []
    for candidate in candidates:
        explicit = _query_contains_rule_key(query, candidate["rule_key"])
        if policy == "explicit_only" and explicit:
            filtered.append(candidate)
        elif policy == "confident" and (
            explicit
            or candidate.get("full_text_rank", 0) > 0
            or candidate.get("trigram_score", 0) >= strong_threshold
        ):
            filtered.append(candidate)
    return filtered


def _offline_rrf(
    semantic_candidates,
    lexical_candidates,
    rrf_k,
    semantic_weight,
    lexical_weight,
):
    indexed = {}
    for channel, candidates, weight in (
        ("semantic", semantic_candidates, semantic_weight),
        ("lexical", lexical_candidates, lexical_weight),
    ):
        if weight == 0:
            continue
        for rank, candidate in enumerate(candidates, start=1):
            chunk_id = candidate["playbook_chunk_id"]
            entry = indexed.setdefault(
                chunk_id,
                {
                    "chunk_id": chunk_id,
                    "rule_key": candidate["rule_key"],
                    "score": 0.0,
                    "semantic_rank": None,
                    "lexical_rank": None,
                },
            )
            entry[f"{channel}_rank"] = rank
            entry["score"] += weight / (rrf_k + rank)

    def sort_key(item):
        ranks = [
            rank
            for rank in (item["semantic_rank"], item["lexical_rank"])
            if rank is not None
        ]
        appears_in_both = len(ranks) == 2
        return (
            -item["score"],
            -int(appears_in_both),
            min(ranks),
            item["chunk_id"],
        )

    return [item["rule_key"] for item in sorted(indexed.values(), key=sort_key)]


def _query_contains_rule_key(query, rule_key):
    pattern = rf"(?<![A-Za-z0-9]){re.escape(rule_key)}(?![A-Za-z0-9])"
    return re.search(pattern, query, flags=re.IGNORECASE) is not None


def _baseline_summary(results):
    baseline = results["summary"]["overall"]
    return {
        method: {
            "quality": values["quality"],
            "negative_quality": values["negative_quality"],
        }
        for method, values in baseline.items()
    }


def _recommend_threshold(rows, baseline, cutoffs):
    largest = str(max(cutoffs))
    baseline_recall = baseline["semantic"]["quality"]["recall_at_k"][largest]
    eligible = [
        row
        for row in rows
        if row["summary"]["quality"]["recall_at_k"][largest]
        >= baseline_recall
    ]
    if not eligible:
        return None
    return min(
        eligible,
        key=lambda row: (
            row["summary"]["negative_quality"]["false_positive_rate_at_k"][
                largest
            ],
            -row["semantic_threshold"],
        ),
    )


def _recommend_fusion(rows, baseline, cutoffs):
    largest = str(max(cutoffs))
    semantic = baseline["semantic"]
    eligible = [
        row
        for row in rows
        if row["summary"]["quality"]["recall_at_k"][largest]
        >= semantic["quality"]["recall_at_k"][largest]
        and row["summary"]["quality"]["hit_rate_at_k"]["1"]
        >= semantic["quality"]["hit_rate_at_k"]["1"]
    ]
    if not eligible:
        return None
    guarded = [
        row
        for row in eligible
        if row["lexical_policy"] in {"confident", "explicit_only"}
        and row["lexical_weight"] > 0
    ]
    if guarded:
        eligible = guarded
    return max(
        eligible,
        key=lambda row: (
            row["summary"]["quality"]["mrr"],
            -row["changed_case_count"],
            int(row["lexical_policy"] == "confident"),
            row["lexical_weight"],
        ),
    )


def _render_optimization_markdown(analysis):
    cutoffs = analysis["config"]["cutoffs"]
    largest = str(max(cutoffs))
    lines = [
        "# Offline Retrieval Optimization",
        "",
        f"Source dataset: `{analysis['source']['dataset_id']}` "
        f"({analysis['source']['case_count']} cases)",
        "",
        "This replay uses saved candidate rankings. It makes no database or "
        "embedding API calls.",
        "",
        "## Semantic threshold sweep",
        "",
        f"| Threshold | Recall@{largest} | Hit@1 | Negative FP@{largest} | Changed cases |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in analysis["threshold_sweep"]:
        summary = row["summary"]
        lines.append(
            f"| {row['semantic_threshold']:.2f} | "
            f"{summary['quality']['recall_at_k'][largest]:.3f} | "
            f"{summary['quality']['hit_rate_at_k']['1']:.3f} | "
            f"{summary['negative_quality']['false_positive_rate_at_k'][largest]:.3f} | "
            f"{row['changed_case_count']} |"
        )

    lines.extend(
        [
            "",
            "## Fusion sweep",
            "",
            f"| Lexical policy | Lexical weight | Recall@{largest} | Hit@1 | MRR | Changed cases |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in analysis["fusion_sweep"]:
        summary = row["summary"]
        lines.append(
            f"| {row['lexical_policy']} | {row['lexical_weight']:.2f} | "
            f"{summary['quality']['recall_at_k'][largest]:.3f} | "
            f"{summary['quality']['hit_rate_at_k']['1']:.3f} | "
            f"{summary['quality']['mrr']:.3f} | {row['changed_case_count']} |"
        )

    threshold = analysis["recommendations"]["threshold"]
    fusion = analysis["recommendations"]["fusion"]
    combined = analysis["recommendations"]["combined"]
    locked = analysis["recommendations"]["locked"]
    if analysis["analysis_mode"] == "holdout":
        lines.extend(["", "## Locked holdout policy", ""])
        summary = locked["summary"]
        lines.extend(
            [
                f"- Semantic threshold: `{locked['semantic_threshold']:.2f}`",
                f"- Lexical policy: `{locked['lexical_policy']}`",
                f"- Lexical weight: `{locked['lexical_weight']:.2f}`",
                f"- Recall@{largest}: "
                f"`{summary['quality']['recall_at_k'][largest]:.3f}`",
                f"- Hit@1: `{summary['quality']['hit_rate_at_k']['1']:.3f}`",
                f"- Negative FP@{largest}: "
                f"`{summary['negative_quality']['false_positive_rate_at_k'][largest]:.3f}`",
                "",
                "The sweep tables above are diagnostic only. Selecting a new "
                "threshold from this holdout would leak evaluation data into tuning.",
                "",
            ]
        )
        return "\n".join(lines)

    lines.extend(["", "## Evidence-preserving recommendations", ""])
    if threshold:
        lines.append(
            f"- Threshold `{threshold['semantic_threshold']:.2f}` is the strongest "
            f"tested cutoff that preserves baseline Recall@{largest}."
        )
    else:
        lines.append("- No tested threshold preserves baseline recall.")
    if fusion:
        lines.append(
            f"- Fusion policy `{fusion['lexical_policy']}` with lexical weight "
            f"`{fusion['lexical_weight']:.2f}` does not regress baseline Hit@1 "
            f"or Recall@{largest}."
        )
    else:
        lines.append("- No tested fusion policy avoids a baseline regression.")
    if combined:
        summary = combined["summary"]
        lines.append(
            f"- Combined development policy: Recall@{largest} "
            f"`{summary['quality']['recall_at_k'][largest]:.3f}`, Hit@1 "
            f"`{summary['quality']['hit_rate_at_k']['1']:.3f}`, negative "
            f"FP@{largest} "
            f"`{summary['negative_quality']['false_positive_rate_at_k'][largest]:.3f}`."
        )
    lines.extend(
        [
            "",
            "These are development-set recommendations, not production thresholds. "
            "Validate them on a separately reviewed holdout before adoption.",
            "",
        ]
    )
    return "\n".join(lines)


def _validate_results(payload):
    if not isinstance(payload, dict):
        raise ValueError("Benchmark results must be a JSON object.")
    for key in ("generated_at", "dataset", "config", "summary", "cases"):
        if key not in payload:
            raise ValueError(f"Benchmark results are missing {key!r}.")
    if not isinstance(payload["cases"], list) or not payload["cases"]:
        raise ValueError("Benchmark results must contain at least one case.")
