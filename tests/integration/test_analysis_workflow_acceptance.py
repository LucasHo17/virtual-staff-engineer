import unittest
from pathlib import Path

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
)
from virtual_staff_engineer.evaluation.analysis_dataset import (
    load_analysis_dataset,
)


DATASET_PATH = Path("evaluation_data/analysis_workflow_cases.json")


class ScriptedAcceptanceReasoner:
    """Exercise workflow branches without pretending to measure model quality."""

    def __init__(self, case):
        self.case = case
        self.rule_key = case.candidate_rule_keys[0]
        self.evaluation_calls = 0

    def plan_queries(self, analysis_input):
        return (
            SearchQuery(
                f"{self.rule_key} applicability",
                f"Retrieve {self.rule_key} for this acceptance scenario.",
            ),
        )

    def propose_findings(self, analysis_input, evidence):
        if self.case.case_type == "irrelevant":
            return AnalysisProposal(findings=())
        if self.case.case_type == "ambiguous":
            return AnalysisProposal(
                findings=(),
                needs_more_input=True,
                context_reason=self.case.notes,
            )
        return AnalysisProposal(
            findings=(ProposedFinding(
                rule_key=self.rule_key,
                playbook_chunk_id=f"chunk-{self.rule_key}",
                source_path=analysis_input.source_path,
                start_line=1,
                end_line=1,
                input_excerpt=analysis_input.lines[0],
                explanation="Scripted proposal for workflow acceptance.",
                severity="high",
                confidence=0.9,
            ),),
        )

    def evaluate_findings(self, analysis_input, findings, evidence):
        self.evaluation_calls += 1
        if self.case.case_type == "violating":
            return EvaluationResult(
                decisions=(
                    EvaluationDecision(
                        0,
                        "supported",
                        "The scripted violation is supported.",
                    ),
                )
            )
        if self.case.case_type == "clean":
            return EvaluationResult(
                decisions=(
                    EvaluationDecision(
                        0,
                        "unsupported",
                        "The input describes compliant behavior.",
                    ),
                )
            )
        raise AssertionError("Ambiguous input must stop before evaluation.")


class ScriptedRetrievalTool:
    def __init__(self, rule_key):
        self.rule_key = rule_key

    def search(self, query):
        return (
            RuleEvidence(
                playbook_chunk_id=f"chunk-{self.rule_key}",
                playbook_version_id="acceptance-version-1",
                rule_key=self.rule_key,
                filename="evaluation_playbook.md",
                section=f"Rule {self.rule_key}",
                content=f"Acceptance evidence for {self.rule_key}.",
                retrieval_query=query.query,
                rank_position=1,
                retrieval_score=0.03,
                semantic_rank=1,
            ),
        )


class AnalysisWorkflowAcceptanceTests(unittest.TestCase):
    def test_all_labeled_workflow_scenarios_reach_expected_terminal_state(self):
        dataset = load_analysis_dataset(DATASET_PATH, require_frozen=False)

        for case in dataset.cases:
            with self.subTest(case_id=case.case_id):
                reasoner = ScriptedAcceptanceReasoner(case)
                orchestrator = BoundedAnalysisOrchestrator(
                    reasoner,
                    ScriptedRetrievalTool(case.candidate_rule_keys[0]),
                )
                result = orchestrator.run(
                    AnalysisInput(
                        case.input_type,
                        case.content,
                        case.source_path,
                    )
                )

                actual_rule_keys = tuple(
                    finding.rule_key for finding in result.findings
                )
                self.assertEqual(result.status, case.expected_status)
                self.assertEqual(actual_rule_keys, case.expected_rule_keys)
                self.assertEqual(result.rejected_findings, ())

                if case.case_type == "ambiguous":
                    self.assertEqual(result.iterations, 1)
                    self.assertEqual(len(result.queries), 1)
                    self.assertEqual(reasoner.evaluation_calls, 0)
                    self.assertEqual(result.inconclusive_reason, case.notes)
                elif case.case_type == "irrelevant":
                    self.assertEqual(reasoner.evaluation_calls, 0)
                else:
                    self.assertEqual(reasoner.evaluation_calls, 1)


if __name__ == "__main__":
    unittest.main()
