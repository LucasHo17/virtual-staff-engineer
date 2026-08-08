import unittest
from pathlib import Path

from virtual_staff_engineer.analysis.contracts import (
    AnalysisProposal,
    EvaluationDecision,
    EvaluationResult,
    ProposedFinding,
    RuleEvidence,
    SearchQuery,
)
from virtual_staff_engineer.evaluation.analysis_dataset import (
    load_analysis_dataset,
)
from virtual_staff_engineer.evaluation.analysis_report import (
    render_analysis_markdown,
)
from virtual_staff_engineer.evaluation.analysis_runner import (
    AnalysisBenchmarkConfig,
    run_analysis_benchmark,
    summarize_analysis_cases,
)


DATASET_PATH = Path("evaluation_data/analysis_workflow_cases.json")


class FakeReasoner:
    model = "fake-model"

    def __init__(self):
        self.calls = 0

    def plan_queries(self, analysis_input):
        self.calls += 1
        return (SearchQuery("SEC-01 logging", "Find logging rules."),)

    def propose_findings(self, analysis_input, evidence):
        self.calls += 1
        return AnalysisProposal(
            findings=(
                ProposedFinding(
                    rule_key="SEC-01",
                    playbook_chunk_id="chunk-1",
                    source_path=analysis_input.source_path,
                    start_line=1,
                    end_line=1,
                    input_excerpt=analysis_input.lines[0],
                    explanation="Token appears in logs.",
                    severity="high",
                    confidence=0.9,
                ),
            )
        )

    def evaluate_findings(self, analysis_input, findings, evidence):
        self.calls += 1
        return EvaluationResult(
            decisions=(
                EvaluationDecision(0, "supported", "Evidence matches."),
            )
        )

    def usage_snapshot(self):
        return {
            "model_calls": self.calls,
            "input_tokens": self.calls * 10,
            "output_tokens": self.calls * 2,
            "thinking_tokens": self.calls,
        }


class FakeRetrievalTool:
    def search(self, query):
        return (
            RuleEvidence(
                playbook_chunk_id="chunk-1",
                playbook_version_id="version-1",
                rule_key="SEC-01",
                filename="evaluation_playbook.md",
                section="Sensitive Data in Logs",
                content="Access tokens must not be logged.",
                retrieval_query=query.query,
                rank_position=1,
                retrieval_score=0.03,
                semantic_rank=1,
            ),
        )


class AnalysisRunnerTests(unittest.TestCase):
    def test_runs_workflow_and_records_quality_usage_and_provenance(self):
        dataset = load_analysis_dataset(DATASET_PATH)
        case = dataset.cases[0]
        config = AnalysisBenchmarkConfig(
            model="fake-model",
            input_cost_per_million=1.0,
            output_cost_per_million=2.0,
        )

        result = run_analysis_benchmark(
            dataset,
            cases=(case,),
            config=config,
            reasoner=FakeReasoner(),
            retrieval_tool=FakeRetrievalTool(),
            corpus_verifier=lambda dataset, database_url=None: {
                "filename": "evaluation_playbook.md",
                "version": 1,
                "chunk_count": 31,
            },
        )

        self.assertEqual(result["run_status"], "partial")
        self.assertEqual(result["cases"][0]["actual_rule_keys"], ["SEC-01"])
        self.assertEqual(result["summary"]["quality"]["precision"], 1.0)
        self.assertEqual(result["summary"]["usage"]["model_calls"], 3)
        self.assertGreater(
            result["summary"]["usage"]["estimated_reasoning_cost_usd"],
            0,
        )

        markdown = render_analysis_markdown(result)
        self.assertIn("Phase 2 Agent Evaluation", markdown)
        self.assertIn("violating-001 — PASS", markdown)

    def test_summary_separates_clean_and_irrelevant_false_positives(self):
        cases = [
            _case_result("clean", [], [], "completed_clean", "completed_clean"),
            _case_result("irrelevant", [], ["GOV-01"], "completed_clean", "review_required"),
            _case_result("ambiguous", [], [], "inconclusive", "inconclusive"),
        ]
        summary = summarize_analysis_cases(
            cases,
            AnalysisBenchmarkConfig(model="fake-model"),
        )

        self.assertEqual(summary["quality"]["clean_false_positive_rate"], 0.0)
        self.assertEqual(
            summary["quality"]["irrelevant_false_positive_rate"], 1.0
        )
        self.assertEqual(
            summary["quality"]["ambiguous_inconclusive_rate"], 1.0
        )


def _case_result(case_type, expected, actual, expected_status, actual_status):
    expected_set = set(expected)
    actual_set = set(actual)
    return {
        "case_type": case_type,
        "metrics": {
            "true_positives": len(expected_set & actual_set),
            "false_positives": len(actual_set - expected_set),
            "false_negatives": len(expected_set - actual_set),
            "exact_rule_match": expected_set == actual_set,
            "status_match": expected_status == actual_status,
        },
        "actual_status": actual_status,
        "latency_ms": 10.0,
        "usage": {
            "model_calls": 1,
            "input_tokens": 10,
            "output_tokens": 2,
            "thinking_tokens": 1,
        },
        "proposal_count": len(actual),
        "deterministic_rejection_count": 0,
        "decisions": [],
        "unsupported_decision_count": 0,
        "query_count": 1,
        "iterations": 1,
    }


if __name__ == "__main__":
    unittest.main()
