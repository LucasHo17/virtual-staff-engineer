import hashlib
import unittest

from virtual_staff_engineer.remediation.contracts import (
    PersistedPatchProposal,
    SourceSnapshot,
)
from virtual_staff_engineer.remediation.validation import (
    DeterministicPatchValidator,
    PatchApplyError,
    apply_unified_diff,
)


class DeterministicPatchValidatorTests(unittest.TestCase):
    def test_valid_python_patch_applies_in_memory(self):
        proposal = _proposal()
        source = SourceSnapshot("app.py", proposal.original_content)

        result = DeterministicPatchValidator().validate(proposal, source)

        self.assertEqual(result.status, "valid")
        self.assertEqual(result.changed_lines, 2)
        self.assertEqual(len(result.resulting_sha256), 64)
        self.assertTrue(all(check.status == "passed" for check in result.checks))

    def test_stale_source_is_recorded_as_invalid(self):
        proposal = _proposal()
        source = SourceSnapshot("app.py", "logger.info('already changed')\n")

        result = DeterministicPatchValidator().validate(proposal, source)

        self.assertEqual(result.status, "invalid")
        current_hash_check = next(
            check
            for check in result.checks
            if check.name == "current_source_hash"
        )
        self.assertEqual(current_hash_check.status, "failed")

    def test_invalid_syntax_and_change_budget_are_rejected(self):
        original = "value = 1\n"
        proposal = PersistedPatchProposal(
            patch_proposal_id="proposal-1",
            remediation_action_id="action-1",
            source_path="app.py",
            source_revision=None,
            original_content=original,
            original_sha256=_sha(original),
            unified_diff=(
                "--- a/app.py\n+++ b/app.py\n@@ -1 +1,2 @@\n"
                "-value = 1\n+if True\n+value = 2"
            ),
        )

        result = DeterministicPatchValidator(
            maximum_changed_lines=2
        ).validate(proposal, SourceSnapshot("app.py", original))

        self.assertEqual(result.status, "invalid")
        failed = {
            check.name for check in result.checks if check.status == "failed"
        }
        self.assertEqual(failed, {"change_budget", "syntax"})

    def test_rejects_diff_with_mismatched_context(self):
        with self.assertRaisesRegex(PatchApplyError, "context"):
            apply_unified_diff(
                "actual()\n",
                (
                    "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
                    "-different()\n+safe()"
                ),
                "app.py",
            )


def _proposal():
    original = "logger.info(token)\n"
    return PersistedPatchProposal(
        patch_proposal_id="proposal-1",
        remediation_action_id="action-1",
        source_path="app.py",
        source_revision=None,
        original_content=original,
        original_sha256=_sha(original),
        unified_diff=(
            "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
            "-logger.info(token)\n+logger.info('request received')"
        ),
    )


def _sha(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
