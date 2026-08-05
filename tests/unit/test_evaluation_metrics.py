import unittest

from virtual_staff_engineer.evaluation.metrics import (
    aggregate_metrics,
    evaluate_ranking,
    percentile,
)


class EvaluationMetricsTests(unittest.TestCase):
    def test_multi_rule_metrics_are_calculated_at_each_cutoff(self):
        metrics = evaluate_ranking(
            ["A", "B"],
            ["A", "C", "B", "B"],
            [1, 3],
        )

        self.assertEqual(metrics["recall_at_k"]["1"], 0.5)
        self.assertEqual(metrics["precision_at_k"]["1"], 1.0)
        self.assertEqual(metrics["recall_at_k"]["3"], 1.0)
        self.assertAlmostEqual(metrics["precision_at_k"]["3"], 2 / 3)
        self.assertEqual(metrics["reciprocal_rank"], 1.0)

    def test_negative_case_records_false_positive(self):
        metrics = evaluate_ranking([], ["A"], [1, 3])

        self.assertIsNone(metrics["recall_at_k"]["1"])
        self.assertEqual(metrics["false_positive_at_k"]["1"], 1)
        self.assertEqual(metrics["false_positive_at_k"]["3"], 1)

    def test_aggregation_separates_positive_and_negative_quality(self):
        items = [
            {
                "latency_ms": 10,
                "metrics": evaluate_ranking(["A"], ["A"], [1]),
            },
            {
                "latency_ms": 30,
                "metrics": evaluate_ranking([], [], [1]),
            },
        ]

        summary = aggregate_metrics(items, [1])

        self.assertEqual(summary["positive_case_count"], 1)
        self.assertEqual(summary["negative_case_count"], 1)
        self.assertEqual(summary["quality"]["recall_at_k"]["1"], 1.0)
        self.assertEqual(
            summary["negative_quality"]["false_positive_rate_at_k"]["1"],
            0.0,
        )
        self.assertEqual(summary["latency_ms"]["mean"], 20)

    def test_percentile_uses_nearest_rank(self):
        self.assertEqual(percentile([10, 20, 30, 40], 50), 20)
        self.assertEqual(percentile([10, 20, 30, 40], 95), 40)


if __name__ == "__main__":
    unittest.main()
