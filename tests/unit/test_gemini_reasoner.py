import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from virtual_staff_engineer.analysis.contracts import AnalysisInput, RuleEvidence
from virtual_staff_engineer.analysis.gemini import GeminiReasoner


class FakeModels:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self.payloads.pop(0)))


class FakeLimiter:
    def __init__(self):
        self.calls = 0

    def acquire(self):
        self.calls += 1


class GeminiReasonerTests(unittest.TestCase):
    def test_structured_reasoning_flow(self):
        models = FakeModels(
            [
                {
                    "queries": [
                        {
                            "query": "access token logging",
                            "purpose": "Retrieve sensitive logging rules.",
                        }
                    ]
                },
                {
                    "findings": [
                        {
                            "rule_key": "SEC-01",
                            "playbook_chunk_id": "chunk-1",
                            "start_line": 1,
                            "end_line": 1,
                            "explanation": "A token is written to logs.",
                            "severity": "high",
                            "confidence": 0.95,
                        }
                    ],
                    "needs_more_input": False,
                    "context_reason": None,
                },
                {
                    "decisions": [
                        {
                            "finding_index": 0,
                            "verdict": "supported",
                            "reason": "The input and rule support the claim.",
                        }
                    ],
                    "needs_more_context": False,
                    "additional_queries": [],
                    "context_reason": None,
                },
            ]
        )
        limiter = FakeLimiter()
        reasoner = GeminiReasoner(
            model="test-reasoning-model",
            client=SimpleNamespace(models=models),
            thinking_budget=512,
            request_limiter=limiter,
        )
        analysis_input = AnalysisInput(
            "code_diff", "logger.info(token)", "app.py"
        )
        evidence = (_evidence(),)

        queries = reasoner.plan_queries(analysis_input)
        proposal = reasoner.propose_findings(analysis_input, evidence)
        evaluation = reasoner.evaluate_findings(
            analysis_input, proposal.findings, evidence
        )

        self.assertEqual(queries[0].query, "access token logging")
        self.assertEqual(proposal.findings[0].rule_key, "SEC-01")
        self.assertEqual(proposal.findings[0].source_path, "app.py")
        self.assertEqual(
            proposal.findings[0].input_excerpt,
            "logger.info(token)",
        )
        self.assertEqual(evaluation.decisions[0].verdict, "supported")
        self.assertEqual(len(models.calls), 3)
        self.assertEqual(limiter.calls, 3)
        analyst_prompt = models.calls[1]["contents"]
        self.assertIn(
            "Do not assume hypothetical mitigations",
            analyst_prompt,
        )
        self.assertIn(
            "directly show behavior that conflicts",
            analyst_prompt,
        )
        self.assertIn(
            "choose the narrowest rule",
            analyst_prompt,
        )
        for call in models.calls:
            self.assertEqual(call["model"], "test-reasoning-model")
            self.assertEqual(
                call["config"].response_mime_type,
                "application/json",
            )
            self.assertEqual(call["config"].temperature, 0)
            self.assertEqual(
                call["config"].thinking_config.thinking_budget,
                512,
            )

    def test_constructs_multiline_excerpt_from_model_line_range(self):
        models = FakeModels(
            [
                {
                    "findings": [
                        {
                            "rule_key": "SEC-01",
                            "playbook_chunk_id": "chunk-1",
                            "start_line": 1,
                            "end_line": 2,
                            "explanation": "Sensitive values reach logs.",
                            "severity": "high",
                            "confidence": 0.9,
                        }
                    ],
                    "needs_more_input": False,
                    "context_reason": None,
                }
            ]
        )
        reasoner = GeminiReasoner(
            model="test-model",
            client=SimpleNamespace(models=models),
        )
        analysis_input = AnalysisInput(
            "design_document",
            "Clients retry timed-out requests\nwithout an idempotency key.",
        )

        proposal = reasoner.propose_findings(
            analysis_input,
            (_evidence(),),
        )

        finding = proposal.findings[0]
        self.assertEqual(finding.source_path, "<input>")
        self.assertEqual(
            finding.input_excerpt,
            "Clients retry timed-out requests\nwithout an idempotency key.",
        )

    def test_rejects_model_line_range_outside_submitted_input(self):
        models = FakeModels(
            [
                {
                    "findings": [
                        {
                            "rule_key": "SEC-01",
                            "playbook_chunk_id": "chunk-1",
                            "start_line": 2,
                            "end_line": 2,
                            "explanation": "Invalid location.",
                            "severity": "high",
                            "confidence": 0.9,
                        }
                    ],
                    "needs_more_input": False,
                    "context_reason": None,
                }
            ]
        )
        reasoner = GeminiReasoner(
            model="test-model",
            client=SimpleNamespace(models=models),
        )

        with self.assertRaisesRegex(ValueError, "outside the submitted input"):
            reasoner.propose_findings(
                AnalysisInput("code_diff", "one_line()", "app.py"),
                (_evidence(),),
            )

    def test_model_name_must_be_explicitly_configured(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GEMINI_REASONING_MODEL"):
                GeminiReasoner(client=SimpleNamespace())

    def test_invalid_json_is_rejected(self):
        models = SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(text="not-json")
        )
        reasoner = GeminiReasoner(
            model="test-model",
            client=SimpleNamespace(models=models),
        )

        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            reasoner.plan_queries(
                AnalysisInput("design_document", "Use PostgreSQL.")
            )


def _evidence():
    return RuleEvidence(
        playbook_chunk_id="chunk-1",
        playbook_version_id="version-1",
        rule_key="SEC-01",
        filename="evaluation_playbook.md",
        section="Sensitive Data in Logs",
        content="Access tokens must not be written to logs.",
        retrieval_query="access token logging",
        rank_position=1,
        retrieval_score=0.03,
        semantic_rank=1,
    )


if __name__ == "__main__":
    unittest.main()
