import unittest

from virtual_staff_engineer.evaluation.metrics import (
    aggregate_metrics,
    evaluate_ranking,
)
from virtual_staff_engineer.evaluation.optimization import analyze_optimization


def candidate(chunk_id, rule_key, score, rank, **lexical_scores):
    result = {
        "rank": rank,
        "rule_key": rule_key,
        "playbook_chunk_id": chunk_id,
        "similarity_score": score,
    }
    result.update(lexical_scores)
    return result


def method_result(expected, ranked, candidates):
    return {
        "latency_ms": 1,
        "ranked_rule_keys": ranked,
        "metrics": evaluate_ranking(expected, ranked, [1, 5]),
        "candidates": candidates,
    }


def build_results():
    positive_semantic = [
        candidate("a", "A", 0.70, 1),
        candidate("b", "B", 0.65, 2),
    ]
    positive_lexical = [
        candidate(
            "b",
            "B",
            0,
            1,
            exact_rule_key_match=False,
            full_text_rank=0,
            trigram_score=0.21,
            lexical_score=0.0525,
        )
    ]
    negative_semantic = [candidate("c", "C", 0.55, 1)]
    cases = [
        {
            "case_id": "positive-001",
            "query_type": "semantic",
            "query": "A relevant paraphrase",
            "expected_rule_keys": ["A"],
            "methods": {
                "semantic": method_result(["A"], ["A", "B"], positive_semantic),
                "lexical": method_result(["A"], ["B"], positive_lexical),
                "hybrid": method_result(["A"], ["B", "A"], []),
            },
        },
        {
            "case_id": "negative-001",
            "query_type": "negative",
            "query": "Unrelated question",
            "expected_rule_keys": [],
            "methods": {
                "semantic": method_result([], ["C"], negative_semantic),
                "lexical": method_result([], [], []),
                "hybrid": method_result([], ["C"], []),
            },
        },
    ]
    overall = {}
    for method in ("semantic", "lexical", "hybrid"):
        overall[method] = aggregate_metrics(
            [case["methods"][method] for case in cases],
            [1, 5],
        )
    return {
        "generated_at": "2026-08-04T00:00:00+00:00",
        "dataset": {"dataset_id": "test-v1", "source_path": "cases.json"},
        "config": {"cutoffs": [1, 5], "rrf_k": 60},
        "summary": {"overall": overall},
        "cases": cases,
    }


class EvaluationOptimizationTests(unittest.TestCase):
    def test_threshold_sweep_can_remove_negative_without_losing_recall(self):
        analysis = analyze_optimization(
            build_results(),
            thresholds=(0.56, 0.71),
            lexical_weights=(0, 1),
        )

        recommendation = analysis["recommendations"]["threshold"]
        self.assertEqual(recommendation["semantic_threshold"], 0.56)
        self.assertEqual(
            recommendation["summary"]["quality"]["recall_at_k"]["5"],
            1.0,
        )
        self.assertEqual(
            recommendation["summary"]["negative_quality"]
            ["false_positive_rate_at_k"]["5"],
            0.0,
        )

    def test_confident_fusion_ignores_weak_lexical_regression(self):
        analysis = analyze_optimization(
            build_results(),
            thresholds=(0.5,),
            lexical_weights=(1,),
        )
        rows = {
            row["lexical_policy"]: row for row in analysis["fusion_sweep"]
        }

        self.assertEqual(
            rows["all"]["summary"]["quality"]["hit_rate_at_k"]["1"],
            0.0,
        )
        self.assertEqual(
            rows["confident"]["summary"]["quality"]["hit_rate_at_k"]["1"],
            1.0,
        )
        self.assertEqual(
            analysis["recommendations"]["fusion"]["lexical_policy"],
            "confident",
        )

    def test_locked_holdout_policy_is_evaluated_without_recommendation(self):
        analysis = analyze_optimization(
            build_results(),
            thresholds=(0.56, 0.71),
            lexical_weights=(0, 1),
            locked_policy={
                "semantic_threshold": 0.56,
                "lexical_policy": "confident",
                "lexical_weight": 1.0,
            },
        )

        self.assertEqual(analysis["analysis_mode"], "holdout")
        self.assertIsNone(analysis["recommendations"]["threshold"])
        self.assertIsNone(analysis["recommendations"]["fusion"])
        self.assertEqual(
            analysis["recommendations"]["locked"]["semantic_threshold"],
            0.56,
        )


if __name__ == "__main__":
    unittest.main()
