import math


def evaluate_ranking(expected_rule_keys, retrieved_rule_keys, cutoffs):
    """Calculate rule-level metrics for one query and one retrieval method."""
    normalized_cutoffs = validate_cutoffs(cutoffs)
    expected = set(expected_rule_keys)
    retrieved = _deduplicate(retrieved_rule_keys)
    is_negative = not expected

    metrics = {
        "is_negative": is_negative,
        "recall_at_k": {},
        "precision_at_k": {},
        "hit_at_k": {},
        "false_positive_at_k": {},
        "reciprocal_rank": None if is_negative else 0.0,
    }

    for cutoff in normalized_cutoffs:
        top_results = retrieved[:cutoff]
        hits = len(expected.intersection(top_results))
        key = str(cutoff)
        if is_negative:
            metrics["recall_at_k"][key] = None
            metrics["precision_at_k"][key] = None
            metrics["hit_at_k"][key] = None
            metrics["false_positive_at_k"][key] = int(bool(top_results))
        else:
            metrics["recall_at_k"][key] = hits / len(expected)
            metrics["precision_at_k"][key] = hits / cutoff
            metrics["hit_at_k"][key] = int(hits > 0)
            metrics["false_positive_at_k"][key] = None

    if not is_negative:
        for rank, rule_key in enumerate(retrieved, start=1):
            if rule_key in expected:
                metrics["reciprocal_rank"] = 1 / rank
                break

    return metrics


def aggregate_metrics(case_results, cutoffs):
    """Aggregate per-case metrics and latency for one retrieval method."""
    normalized_cutoffs = validate_cutoffs(cutoffs)
    positive = [item for item in case_results if not item["metrics"]["is_negative"]]
    negative = [item for item in case_results if item["metrics"]["is_negative"]]
    latencies = [item["latency_ms"] for item in case_results]

    quality = {
        "recall_at_k": {},
        "precision_at_k": {},
        "hit_rate_at_k": {},
        "mrr": _mean(
            [item["metrics"]["reciprocal_rank"] for item in positive]
        ),
    }
    negative_quality = {
        "false_positive_rate_at_k": {},
        "no_result_rate_at_k": {},
    }

    for cutoff in normalized_cutoffs:
        key = str(cutoff)
        quality["recall_at_k"][key] = _mean(
            [item["metrics"]["recall_at_k"][key] for item in positive]
        )
        quality["precision_at_k"][key] = _mean(
            [item["metrics"]["precision_at_k"][key] for item in positive]
        )
        quality["hit_rate_at_k"][key] = _mean(
            [item["metrics"]["hit_at_k"][key] for item in positive]
        )
        false_positive_rate = _mean(
            [
                item["metrics"]["false_positive_at_k"][key]
                for item in negative
            ]
        )
        negative_quality["false_positive_rate_at_k"][key] = (
            false_positive_rate
        )
        negative_quality["no_result_rate_at_k"][key] = (
            None
            if false_positive_rate is None
            else 1 - false_positive_rate
        )

    return {
        "case_count": len(case_results),
        "positive_case_count": len(positive),
        "negative_case_count": len(negative),
        "quality": quality,
        "negative_quality": negative_quality,
        "latency_ms": {
            "mean": _mean(latencies),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
        },
    }


def percentile(values, percentile_value):
    """Return the nearest-rank percentile used by the benchmark report."""
    if not values:
        return None
    if percentile_value < 0 or percentile_value > 100:
        raise ValueError("percentile must be between 0 and 100.")
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile_value / 100) * len(ordered)))
    return ordered[rank - 1]


def validate_cutoffs(cutoffs):
    normalized = tuple(sorted(set(cutoffs)))
    if not normalized:
        raise ValueError("At least one evaluation cutoff is required.")
    if any(
        isinstance(cutoff, bool)
        or not isinstance(cutoff, int)
        or cutoff < 1
        for cutoff in normalized
    ):
        raise ValueError("Evaluation cutoffs must be positive integers.")
    return normalized


def _deduplicate(values):
    return list(dict.fromkeys(values))


def _mean(values):
    if not values:
        return None
    return sum(values) / len(values)
