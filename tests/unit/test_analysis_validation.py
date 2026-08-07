import unittest

from virtual_staff_engineer.analysis.contracts import (
    AnalysisInput,
    ProposedFinding,
    RuleEvidence,
)
from virtual_staff_engineer.analysis.validation import validate_findings


class FindingValidationTests(unittest.TestCase):
    def setUp(self):
        self.analysis_input = AnalysisInput(
            "code_diff",
            "safe_call()\nlogger.info(token)",
            "app.py",
        )
        self.evidence = (_evidence(),)

    def test_accepts_real_rule_and_verbatim_input_citations(self):
        finding = _finding()

        result = validate_findings(
            self.analysis_input, (finding,), self.evidence
        )

        self.assertEqual(result.valid_findings, (finding,))
        self.assertEqual(result.rejections, ())

    def test_rejects_chunk_not_returned_by_retrieval(self):
        result = self._validate(
            _finding(playbook_chunk_id="fabricated-chunk")
        )
        self.assert_rejection(result, "unknown_playbook_chunk")

    def test_rejects_rule_key_that_does_not_match_chunk(self):
        result = self._validate(_finding(rule_key="SEC-99"))
        self.assert_rejection(result, "rule_key_mismatch")

    def test_rejects_source_path_that_does_not_match_input(self):
        result = self._validate(_finding(source_path="other.py"))
        self.assert_rejection(result, "source_path_mismatch")

    def test_requires_input_placeholder_when_source_path_is_unknown(self):
        input_without_path = AnalysisInput(
            "design_document", "Store tokens safely."
        )
        result = validate_findings(
            input_without_path,
            (_finding(
                source_path="architecture.md",
                start_line=1,
                end_line=1,
                input_excerpt="Store tokens safely.",
            ),),
            self.evidence,
        )
        self.assert_rejection(result, "source_path_mismatch")

    def test_rejects_line_range_outside_input(self):
        result = self._validate(
            _finding(start_line=3, end_line=3, input_excerpt="missing")
        )
        self.assert_rejection(result, "line_range_out_of_bounds")

    def test_rejects_excerpt_not_equal_to_cited_lines(self):
        result = self._validate(_finding(input_excerpt="token"))
        self.assert_rejection(result, "input_excerpt_mismatch")

    def test_accepts_exact_multiline_excerpt(self):
        finding = _finding(
            start_line=1,
            end_line=2,
            input_excerpt="safe_call()\nlogger.info(token)",
        )
        result = self._validate(finding)
        self.assertEqual(result.valid_findings, (finding,))

    def test_rejects_duplicate_rule_and_location(self):
        finding = _finding()
        result = validate_findings(
            self.analysis_input,
            (finding, finding),
            self.evidence,
        )

        self.assertEqual(result.valid_findings, (finding,))
        self.assertEqual(result.rejections[0].finding_index, 1)
        self.assertEqual(result.rejections[0].code, "duplicate_finding")

    def test_duplicate_identity_does_not_depend_on_chunk_id(self):
        second_evidence = _evidence(
            playbook_chunk_id="chunk-2",
            playbook_version_id="version-2",
        )
        result = validate_findings(
            self.analysis_input,
            (
                _finding(),
                _finding(playbook_chunk_id="chunk-2"),
            ),
            (self.evidence[0], second_evidence),
        )

        self.assertEqual(len(result.valid_findings), 1)
        self.assertEqual(result.rejections[0].code, "duplicate_finding")

    def _validate(self, finding):
        return validate_findings(
            self.analysis_input,
            (finding,),
            self.evidence,
        )

    def assert_rejection(self, result, expected_code):
        self.assertEqual(result.valid_findings, ())
        self.assertEqual(len(result.rejections), 1)
        self.assertEqual(result.rejections[0].code, expected_code)


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


def _evidence(**overrides):
    values = {
        "playbook_chunk_id": "chunk-1",
        "playbook_version_id": "version-1",
        "rule_key": "SEC-01",
        "filename": "evaluation_playbook.md",
        "section": "Sensitive Data in Logs",
        "content": "Access tokens must not be written to logs.",
        "retrieval_query": "access token logging",
        "rank_position": 1,
        "retrieval_score": 0.03,
        "semantic_rank": 1,
    }
    values.update(overrides)
    return RuleEvidence(**values)


if __name__ == "__main__":
    unittest.main()
