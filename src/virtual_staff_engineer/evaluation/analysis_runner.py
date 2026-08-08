import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.analysis.gemini import GeminiReasoner
from virtual_staff_engineer.analysis.orchestrator import (
    BoundedAnalysisOrchestrator,
    WorkflowLimits,
)
from virtual_staff_engineer.analysis.retrieval_tool import HybridRetrievalTool
from virtual_staff_engineer.evaluation.corpus import verify_corpus
from virtual_staff_engineer.retrieval.hybrid import DEFAULT_CANDIDATE_K
from virtual_staff_engineer.retrieval.validation import validate_top_k


@dataclass(frozen=True)
class AnalysisBenchmarkConfig:
    model: str
    top_k: int = 5
    candidate_k: int = DEFAULT_CANDIDATE_K
    max_iterations: int = 2
    case_delay_seconds: float = 0.0
    thinking_budget: Optional[int] = None
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0

    def validated(self):
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a non-empty string.")
        validate_top_k(self.top_k)
        validate_top_k(self.candidate_k)
        if self.candidate_k < self.top_k:
            raise ValueError("candidate_k must be at least top_k.")
        WorkflowLimits(max_iterations=self.max_iterations)
        if (
            isinstance(self.case_delay_seconds, bool)
            or not isinstance(self.case_delay_seconds, (int, float))
            or not math.isfinite(self.case_delay_seconds)
            or self.case_delay_seconds < 0
        ):
            raise ValueError(
                "case_delay_seconds must be a finite non-negative number."
            )
        if self.thinking_budget is not None and (
            isinstance(self.thinking_budget, bool)
            or not isinstance(self.thinking_budget, int)
            or self.thinking_budget < -1
        ):
            raise ValueError(
                "thinking_budget must be None, -1, or a non-negative integer."
            )
        for field_name in (
            "input_cost_per_million",
            "output_cost_per_million",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(
                    f"{field_name} must be a finite non-negative number."
                )
        return self


def run_analysis_benchmark(
    dataset,
    cases=None,
    config=None,
    database_url=None,
    reasoner=None,
    retrieval_tool=None,
    corpus_verifier=verify_corpus,
    progress_callback=None,
):
    """Run the real Phase 2 workflow and compare it with frozen labels."""
    if config is None:
        raise ValueError("An AnalysisBenchmarkConfig is required.")
    resolved_config = config.validated()
    selected_cases = tuple(cases if cases is not None else dataset.cases)
    if not selected_cases:
        raise ValueError("At least one analysis case is required.")

    corpus = corpus_verifier(dataset, database_url=database_url)
    resolved_reasoner = reasoner or GeminiReasoner(
        model=resolved_config.model,
        thinking_budget=resolved_config.thinking_budget,
    )
    resolved_tool = retrieval_tool or HybridRetrievalTool(
        top_k=resolved_config.top_k,
        candidate_k=resolved_config.candidate_k,
        category=dataset.playbook.category,
        database_url=database_url,
        ai_client=getattr(resolved_reasoner, "client", None),
    )
    orchestrator = BoundedAnalysisOrchestrator(
        resolved_reasoner,
        resolved_tool,
        WorkflowLimits(max_iterations=resolved_config.max_iterations),
    )

    case_results = []
    for case_index, case in enumerate(selected_cases):
        usage_before = _usage_snapshot(resolved_reasoner)
        started_at = time.perf_counter()
        try:
            result = orchestrator.run(
                AnalysisInput(
                    case.input_type,
                    case.content,
                    case.source_path,
                )
            )
        except Exception as exc:
            raise RuntimeError(
                f"Analysis benchmark failed for case {case.case_id}: {exc}"
            ) from exc
        latency_ms = (time.perf_counter() - started_at) * 1000
        usage_after = _usage_snapshot(resolved_reasoner)
        case_result = _evaluate_case(
            case, result, latency_ms, usage_before, usage_after
        )
        case_results.append(case_result)
        if progress_callback is not None:
            progress_callback(case_result, len(case_results), len(selected_cases))
        if (
            resolved_config.case_delay_seconds > 0
            and case_index < len(selected_cases) - 1
        ):
            time.sleep(resolved_config.case_delay_seconds)

    summary = summarize_analysis_cases(case_results, resolved_config)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_status": (
            "complete"
            if len(selected_cases) == len(dataset.cases)
            else "partial"
        ),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "status": dataset.status,
            "source_path": dataset.source_path,
            "total_case_count": len(dataset.cases),
            "selected_case_count": len(selected_cases),
            "review": dataset.review,
        },
        "corpus": corpus,
        "config": asdict(resolved_config),
        "summary": summary,
        "cases": case_results,
    }


def summarize_analysis_cases(case_results, config):
    true_positives = sum(case["metrics"]["true_positives"] for case in case_results)
    false_positives = sum(case["metrics"]["false_positives"] for case in case_results)
    false_negatives = sum(case["metrics"]["false_negatives"] for case in case_results)
    precision = _safe_divide(true_positives, true_positives + false_positives)
    recall = _safe_divide(true_positives, true_positives + false_negatives)
    f1 = _safe_divide(2 * precision * recall, precision + recall)
    latencies = [case["latency_ms"] for case in case_results]
    total_usage = {
        key: sum(case["usage"][key] for case in case_results)
        for key in (
            "model_calls",
            "input_tokens",
            "output_tokens",
            "thinking_tokens",
        )
    }
    billed_output_tokens = (
        total_usage["output_tokens"] + total_usage["thinking_tokens"]
    )
    estimated_cost = (
        total_usage["input_tokens"] * config.input_cost_per_million
        + billed_output_tokens * config.output_cost_per_million
    ) / 1_000_000
    proposal_count = sum(case["proposal_count"] for case in case_results)
    rejection_count = sum(
        case["deterministic_rejection_count"] for case in case_results
    )
    evaluated_decisions = sum(
        len(case["decisions"]) for case in case_results
    )
    unsupported_count = sum(
        case["unsupported_decision_count"] for case in case_results
    )

    by_type = {}
    for case_type in sorted({case["case_type"] for case in case_results}):
        matching = [
            case for case in case_results if case["case_type"] == case_type
        ]
        by_type[case_type] = {
            "case_count": len(matching),
            "status_accuracy": _average(
                [case["metrics"]["status_match"] for case in matching]
            ),
            "exact_rule_accuracy": _average(
                [case["metrics"]["exact_rule_match"] for case in matching]
            ),
            "false_positive_rate": _average(
                [case["metrics"]["false_positives"] > 0 for case in matching]
            ),
            "inconclusive_rate": _average(
                [case["actual_status"] == "inconclusive" for case in matching]
            ),
        }

    return {
        "case_count": len(case_results),
        "quality": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "exact_rule_accuracy": _average(
                [case["metrics"]["exact_rule_match"] for case in case_results]
            ),
            "status_accuracy": _average(
                [case["metrics"]["status_match"] for case in case_results]
            ),
            "violating_detection_rate": _type_rate(
                case_results, "violating", "exact_rule_match"
            ),
            "clean_false_positive_rate": _type_false_positive_rate(
                case_results, "clean"
            ),
            "irrelevant_false_positive_rate": _type_false_positive_rate(
                case_results, "irrelevant"
            ),
            "ambiguous_inconclusive_rate": _type_status_rate(
                case_results, "ambiguous", "inconclusive"
            ),
        },
        "safety": {
            "deterministic_rejection_count": rejection_count,
            "deterministic_rejection_rate": _safe_divide(
                rejection_count, proposal_count
            ),
            "unsupported_decision_count": unsupported_count,
            "unsupported_decision_rate": _safe_divide(
                unsupported_count, evaluated_decisions
            ),
        },
        "workflow": {
            "average_queries": _average(
                [case["query_count"] for case in case_results]
            ),
            "average_iterations": _average(
                [case["iterations"] for case in case_results]
            ),
        },
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "mean": _average(latencies),
        },
        "usage": {
            **total_usage,
            "billed_output_tokens": billed_output_tokens,
            "embedding_requests": sum(
                case["query_count"] for case in case_results
            ),
            "estimated_reasoning_cost_usd": estimated_cost,
        },
        "by_case_type": by_type,
    }


def _evaluate_case(case, result, latency_ms, usage_before, usage_after):
    actual_rule_keys = list(
        dict.fromkeys(finding.rule_key for finding in result.findings)
    )
    expected = set(case.expected_rule_keys)
    actual = set(actual_rule_keys)
    decisions = [asdict(decision) for decision in result.decisions]
    return {
        "case_id": case.case_id,
        "case_type": case.case_type,
        "input_type": case.input_type,
        "source_path": case.source_path,
        "content": case.content,
        "notes": case.notes,
        "candidate_rule_keys": list(case.candidate_rule_keys),
        "expected_rule_keys": list(case.expected_rule_keys),
        "actual_rule_keys": actual_rule_keys,
        "expected_status": case.expected_status,
        "actual_status": result.status,
        "inconclusive_reason": result.inconclusive_reason,
        "metrics": {
            "true_positives": len(expected & actual),
            "false_positives": len(actual - expected),
            "false_negatives": len(expected - actual),
            "exact_rule_match": actual == expected,
            "status_match": result.status == case.expected_status,
        },
        "latency_ms": latency_ms,
        "query_count": len(result.queries),
        "iterations": result.iterations,
        "queries": [asdict(query) for query in result.queries],
        "findings": [asdict(finding) for finding in result.findings],
        "decisions": decisions,
        "rejections": [
            {
                "finding_index": rejection.finding_index,
                "code": rejection.code,
                "reason": rejection.reason,
            }
            for rejection in result.rejected_findings
        ],
        "proposal_count": (
            len(result.evaluated_findings) + len(result.rejected_findings)
        ),
        "deterministic_rejection_count": len(result.rejected_findings),
        "unsupported_decision_count": sum(
            decision["verdict"] == "unsupported" for decision in decisions
        ),
        "usage": {
            key: usage_after[key] - usage_before[key]
            for key in usage_before
        },
    }


def _usage_snapshot(reasoner):
    snapshot_method = getattr(reasoner, "usage_snapshot", None)
    if snapshot_method is None:
        return {
            "model_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "thinking_tokens": 0,
        }
    return snapshot_method()


def _safe_divide(numerator, denominator):
    return numerator / denominator if denominator else 0.0


def _average(values):
    return sum(values) / len(values) if values else 0.0


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _type_rate(case_results, case_type, metric):
    matching = [
        case for case in case_results if case["case_type"] == case_type
    ]
    return _average([case["metrics"][metric] for case in matching])


def _type_false_positive_rate(case_results, case_type):
    matching = [
        case for case in case_results if case["case_type"] == case_type
    ]
    return _average(
        [case["metrics"]["false_positives"] > 0 for case in matching]
    )


def _type_status_rate(case_results, case_type, status):
    matching = [
        case for case in case_results if case["case_type"] == case_type
    ]
    return _average(
        [case["actual_status"] == status for case in matching]
    )
