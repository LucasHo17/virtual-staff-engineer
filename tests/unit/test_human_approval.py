import unittest

from virtual_staff_engineer.remediation.approval import (
    ApprovalCheck,
    ApprovalRequest,
    ApprovalRule,
    HumanDecision,
)


class HumanApprovalContractTests(unittest.TestCase):
    def test_normalizes_an_explicit_human_decision(self):
        decision = HumanDecision(
            decision="approved",
            actor=" reviewer@example.com ",
            comment=" Looks safe. ",
        )

        self.assertEqual(decision.actor, "reviewer@example.com")
        self.assertEqual(decision.comment, "Looks safe.")

    def test_rejects_unknown_decisions_and_blank_actor(self):
        with self.assertRaises(ValueError):
            HumanDecision("maybe", "reviewer")
        with self.assertRaises(ValueError):
            HumanDecision("rejected", " ")
        with self.assertRaises(ValueError):
            HumanDecision("rejected", "reviewer", " ")

    def test_authenticated_decision_requires_complete_identity_provenance(self):
        decision = HumanDecision(
            "approved",
            "octocat",
            authentication_method="github_token",
            authenticated_subject="42",
            authentication_issuer="https://github.com",
        )
        self.assertEqual(decision.authenticated_subject, "42")
        with self.assertRaisesRegex(ValueError, "subject and issuer"):
            HumanDecision(
                "approved", "octocat", authentication_method="github_token"
            )
        with self.assertRaisesRegex(ValueError, "cannot claim"):
            HumanDecision(
                "approved", "octocat", authenticated_subject="42"
            )

    def test_approval_request_requires_valid_result_and_review_evidence(self):
        with self.assertRaisesRegex(ValueError, "Only valid"):
            ApprovalRequest(
                workflow_job_id="job-1",
                remediation_action_id="action-1",
                patch_proposal_id="proposal-1",
                source_path="app.py",
                source_revision=None,
                original_sha256="a" * 64,
                unified_diff="--- a/app.py\n+++ b/app.py",
                explanation="Fix the issue.",
                rules=(ApprovalRule("SEC-01", "Do not log tokens."),),
                validation_status="invalid",
                resulting_sha256="b" * 64,
                checks=(ApprovalCheck("syntax", "passed", "Valid."),),
            )


if __name__ == "__main__":
    unittest.main()
