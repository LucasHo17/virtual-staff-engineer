import unittest

from virtual_staff_engineer.analysis.contracts import (
    AnalysisInput,
    AnalysisProposal,
    EvaluationDecision,
    EvaluationResult,
    ProposedFinding,
    RuleEvidence,
    SearchQuery,
)
from virtual_staff_engineer.analysis.orchestrator import (
    BoundedAnalysisOrchestrator,
    WorkflowLimits,
)
from virtual_staff_engineer.analysis.retrieval_tool import HybridRetrievalTool
from virtual_staff_engineer.retrieval.models import HybridSearchResult


class FakeReasoner:
    def __init__(self, queries, finding_rounds, evaluation_rounds):
        self.queries = tuple(queries)
        self.finding_rounds = list(finding_rounds)
        self.evaluation_rounds = list(evaluation_rounds)
        self.proposal_calls = 0
        self.evaluation_calls = 0

    def plan_queries(self, analysis_input):
        return self.queries

    def propose_findings(self, analysis_input, evidence):
        result = self.finding_rounds[self.proposal_calls]
        self.proposal_calls += 1
        return AnalysisProposal(findings=tuple(result))

    def evaluate_findings(self, analysis_input, findings, evidence):
        result = self.evaluation_rounds[self.evaluation_calls]
        self.evaluation_calls += 1
        return result


class FakeRetrievalTool:
    def __init__(self):
        self.queries = []

    def search(self, query):
        self.queries.append(query.query)
        suffix = len(self.queries)
        return (_evidence(f"chunk-{suffix}", query.query),)


class AnalysisOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.analysis_input = AnalysisInput(
            "code_diff",
            "safe_call()\nlogger.info(token)",
            "app.py",
        )

    def test_clean_run_stops_without_calling_evaluator(self):
        reasoner = FakeReasoner(
            queries=(_query("logging sensitive tokens"),),
            finding_rounds=((),),
            evaluation_rounds=(),
        )
        retrieval = FakeRetrievalTool()

        result = BoundedAnalysisOrchestrator(reasoner, retrieval).run(
            self.analysis_input
        )

        self.assertEqual(result.status, "completed_clean")
        self.assertEqual(result.findings, ())
        self.assertEqual(result.iterations, 1)
        self.assertEqual(reasoner.evaluation_calls, 0)
        self.assertEqual(retrieval.queries, ["logging sensitive tokens"])

    def test_supported_finding_requires_evaluator_decision(self):
        finding = _finding()
        reasoner = FakeReasoner(
            queries=(_query("logging sensitive tokens"),),
            finding_rounds=((finding,),),
            evaluation_rounds=(
                EvaluationResult(
                    decisions=(
                        EvaluationDecision(0, "supported", "Evidence matches."),
                    )
                ),
            ),
        )

        result = BoundedAnalysisOrchestrator(
            reasoner, FakeRetrievalTool()
        ).run(self.analysis_input)

        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.findings, (finding,))
        self.assertEqual(result.decisions[0].verdict, "supported")

    def test_evaluator_can_reject_every_proposal(self):
        finding = _finding()
        reasoner = FakeReasoner(
            queries=(_query("logging sensitive tokens"),),
            finding_rounds=((finding,),),
            evaluation_rounds=(
                EvaluationResult(
                    decisions=(
                        EvaluationDecision(
                            0,
                            "unsupported",
                            "The value is redacted before logging.",
                        ),
                    )
                ),
            ),
        )

        result = BoundedAnalysisOrchestrator(
            reasoner, FakeRetrievalTool()
        ).run(self.analysis_input)

        self.assertEqual(result.status, "completed_clean")
        self.assertEqual(result.findings, ())

    def test_fabricated_evidence_is_rejected_before_evaluator(self):
        reasoner = FakeReasoner(
            queries=(_query("logging sensitive tokens"),),
            finding_rounds=((_finding(playbook_chunk_id="invented-chunk"),),),
            evaluation_rounds=(),
        )

        result = BoundedAnalysisOrchestrator(
            reasoner, FakeRetrievalTool()
        ).run(self.analysis_input)

        self.assertEqual(result.status, "completed_clean")
        self.assertEqual(result.findings, ())
        self.assertEqual(reasoner.evaluation_calls, 0)
        self.assertEqual(
            result.rejected_findings[0].code,
            "unknown_playbook_chunk",
        )

    def test_more_context_runs_one_additional_bounded_iteration(self):
        finding = _finding()
        reasoner = FakeReasoner(
            queries=(_query("logging sensitive tokens"),),
            finding_rounds=((finding,), (finding,)),
            evaluation_rounds=(
                EvaluationResult(
                    decisions=(),
                    needs_more_context=True,
                    additional_queries=(
                        _query("SEC-01 redaction requirements"),
                    ),
                    context_reason="More playbook evidence is required.",
                ),
                EvaluationResult(
                    decisions=(
                        EvaluationDecision(0, "supported", "Evidence matches."),
                    )
                ),
            ),
        )
        retrieval = FakeRetrievalTool()

        result = BoundedAnalysisOrchestrator(reasoner, retrieval).run(
            self.analysis_input
        )

        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.iterations, 2)
        self.assertEqual(
            retrieval.queries,
            ["logging sensitive tokens", "SEC-01 redaction requirements"],
        )
        self.assertEqual(len(result.evidence), 2)

    def test_context_request_at_iteration_limit_is_inconclusive(self):
        finding = _finding()
        reasoner = FakeReasoner(
            queries=(_query("logging sensitive tokens"),),
            finding_rounds=((finding,),),
            evaluation_rounds=(
                EvaluationResult(
                    decisions=(),
                    needs_more_context=True,
                    additional_queries=(_query("more context"),),
                    context_reason="More playbook evidence is required.",
                ),
            ),
        )
        limits = WorkflowLimits(max_iterations=1)

        result = BoundedAnalysisOrchestrator(
            reasoner, FakeRetrievalTool(), limits
        ).run(self.analysis_input)

        self.assertEqual(result.status, "inconclusive")
        self.assertEqual(result.findings, ())
        self.assertEqual(result.iterations, 1)

    def test_query_and_evidence_limits_are_enforced(self):
        reasoner = FakeReasoner(
            queries=tuple(_query(f"query {number}") for number in range(5)),
            finding_rounds=((),),
            evaluation_rounds=(),
        )
        retrieval = FakeRetrievalTool()
        limits = WorkflowLimits(
            max_initial_queries=2,
            max_total_queries=2,
            max_evidence_chunks=1,
        )

        result = BoundedAnalysisOrchestrator(
            reasoner, retrieval, limits
        ).run(self.analysis_input)

        self.assertEqual(len(result.queries), 1)
        self.assertEqual(len(result.evidence), 1)
        self.assertEqual(retrieval.queries, ["query 0"])

    def test_completed_evaluation_must_decide_every_finding(self):
        reasoner = FakeReasoner(
            queries=(_query("logging sensitive tokens"),),
            finding_rounds=(
                (
                    _finding(),
                    _finding(
                        start_line=1,
                        end_line=1,
                        input_excerpt="safe_call()",
                    ),
                ),
            ),
            evaluation_rounds=(
                EvaluationResult(
                    decisions=(
                        EvaluationDecision(0, "supported", "Evidence matches."),
                    )
                ),
            ),
        )

        with self.assertRaisesRegex(ValueError, "decide every finding"):
            BoundedAnalysisOrchestrator(
                reasoner, FakeRetrievalTool()
            ).run(self.analysis_input)


class HybridRetrievalToolTests(unittest.TestCase):
    def test_converts_phase_one_result_to_query_traced_evidence(self):
        calls = []

        def fake_search(query, **kwargs):
            calls.append((query, kwargs))
            return (
                HybridSearchResult(
                    playbook_chunk_id="chunk-1",
                    playbook_version_id="version-1",
                    document_id="document-1",
                    filename="evaluation_playbook.md",
                    category="evaluation",
                    version=1,
                    rule_key="SEC-01",
                    chunk_index=1,
                    section="Sensitive Data in Logs",
                    content="Access tokens must not be written to logs.",
                    embedding_model="test-model",
                    semantic_rank=2,
                    lexical_rank=1,
                    similarity_score=0.8,
                    lexical_score=1.0,
                    rrf_score=0.03,
                ),
            )

        tool = HybridRetrievalTool(
            top_k=3,
            candidate_k=10,
            category="evaluation",
            search_function=fake_search,
        )
        evidence = tool.search(_query("token logs"))

        self.assertEqual(calls[0][0], "token logs")
        self.assertEqual(calls[0][1]["top_k"], 3)
        self.assertEqual(evidence[0].retrieval_query, "token logs")
        self.assertEqual(evidence[0].rule_key, "SEC-01")
        self.assertEqual(evidence[0].rank_position, 1)


def _query(text):
    return SearchQuery(text, f"Retrieve rules about {text}.")


def _evidence(chunk_id, query):
    return RuleEvidence(
        playbook_chunk_id=chunk_id,
        playbook_version_id="version-1",
        rule_key="SEC-01",
        filename="evaluation_playbook.md",
        section="Sensitive Data in Logs",
        content="Access tokens must not be written to logs.",
        retrieval_query=query,
        rank_position=1,
        retrieval_score=0.03,
        semantic_rank=1,
    )


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
