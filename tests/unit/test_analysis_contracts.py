import unittest

from virtual_staff_engineer.analysis.contracts import (
    AnalysisInput,
    EvaluationDecision,
    EvaluationResult,
    ProposedFinding,
    RuleEvidence,
    SearchQuery,
)


class AnalysisContractTests(unittest.TestCase):
    def test_analysis_input_exposes_stable_line_numbers(self):
        analysis_input = AnalysisInput(
            input_type="code_diff",
            content="safe_call()\nlogger.info(token)",
            source_path="app.py",
        )

        self.assertEqual(
            analysis_input.numbered_content,
            "1: safe_call()\n2: logger.info(token)",
        )

    def test_analysis_input_rejects_unknown_or_empty_input(self):
        with self.assertRaisesRegex(ValueError, "input_type"):
            AnalysisInput("chat_message", "hello")
        with self.assertRaisesRegex(ValueError, "content"):
            AnalysisInput("design_document", "  ")

    def test_rule_evidence_requires_valid_rank_and_score(self):
        with self.assertRaisesRegex(ValueError, "rank_position"):
            self._evidence(rank_position=0)
        with self.assertRaisesRegex(ValueError, "retrieval_score"):
            self._evidence(retrieval_score=float("nan"))

    def test_proposed_finding_is_not_an_evaluation_decision(self):
        finding = self._finding()

        self.assertEqual(finding.rule_key, "SEC-01")
        self.assertFalse(hasattr(finding, "verdict"))

    def test_proposed_finding_rejects_invalid_location_and_confidence(self):
        with self.assertRaisesRegex(ValueError, "end_line"):
            self._finding(start_line=4, end_line=3)
        with self.assertRaisesRegex(ValueError, "confidence"):
            self._finding(confidence=1.1)

    def test_evaluation_can_reject_a_finding_without_more_context(self):
        result = EvaluationResult(
            decisions=(
                EvaluationDecision(
                    finding_index=0,
                    verdict="unsupported",
                    reason="The cited input describes compliant behavior.",
                ),
            )
        )

        self.assertFalse(result.needs_more_context)
        self.assertEqual(result.decisions[0].verdict, "unsupported")

    def test_more_context_requires_a_query(self):
        with self.assertRaisesRegex(ValueError, "additional_queries"):
            EvaluationResult(decisions=(), needs_more_context=True)

        result = EvaluationResult(
            decisions=(),
            needs_more_context=True,
            additional_queries=(
                SearchQuery(
                    query="access token logging restrictions",
                    purpose="Verify whether token logging is prohibited.",
                ),
            ),
        )
        self.assertTrue(result.needs_more_context)

    def test_duplicate_evaluation_decisions_are_rejected(self):
        decision = EvaluationDecision(0, "supported", "Evidence matches.")
        with self.assertRaisesRegex(ValueError, "only one"):
            EvaluationResult(decisions=(decision, decision))

    @staticmethod
    def _evidence(**overrides):
        values = {
            "playbook_chunk_id": "chunk-1",
            "playbook_version_id": "version-1",
            "rule_key": "SEC-01",
            "filename": "evaluation_playbook.md",
            "section": "Sensitive Data in Logs",
            "content": "Access tokens must not be written to logs.",
            "rank_position": 1,
            "retrieval_score": 0.03,
            "semantic_rank": 1,
            "lexical_rank": None,
        }
        values.update(overrides)
        return RuleEvidence(**values)

    @staticmethod
    def _finding(**overrides):
        values = {
            "rule_key": "SEC-01",
            "playbook_chunk_id": "chunk-1",
            "source_path": "app.py",
            "start_line": 2,
            "end_line": 2,
            "input_excerpt": "logger.info(token)",
            "explanation": "An access token is written to logs.",
            "severity": "high",
            "confidence": 0.95,
        }
        values.update(overrides)
        return ProposedFinding(**values)


if __name__ == "__main__":
    unittest.main()
