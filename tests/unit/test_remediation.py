import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from virtual_staff_engineer.remediation.contracts import (
    GeneratedPatch,
    PatchGenerationContext,
    PatchRuleEvidence,
    PatchViolation,
    SourceSnapshot,
    validate_generated_patch,
)
from virtual_staff_engineer.remediation.gemini import GeminiPatchGenerator
from virtual_staff_engineer.remediation.source import FilesystemSourceProvider


class FakeModels:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(self.payload))


class RemediationContractTests(unittest.TestCase):
    def test_validates_exact_evidence_grounded_single_file_patch(self):
        context = _context()
        patch = _patch()

        self.assertIs(validate_generated_patch(context, patch), patch)

    def test_rejects_missing_violation_or_wrong_source_path(self):
        context = _context()
        with self.assertRaisesRegex(ValueError, "every and only"):
            validate_generated_patch(
                context,
                GeneratedPatch(
                    unified_diff=_patch().unified_diff,
                    explanation="Partial proposal.",
                    addressed_violation_ids=("other",),
                    addressed_rule_keys=("SEC-01",),
                ),
            )
        with self.assertRaisesRegex(ValueError, "exact source path"):
            validate_generated_patch(
                context,
                GeneratedPatch(
                    unified_diff=(
                        "--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n-x\n+y"
                    ),
                    explanation="Wrong file.",
                    addressed_violation_ids=("violation-1",),
                    addressed_rule_keys=("SEC-01",),
                ),
            )

    def test_filesystem_provider_blocks_path_escape_and_hashes_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app.py").write_text("safe_call()\n", encoding="utf-8")
            provider = FilesystemSourceProvider(root)

            snapshot = provider.load("app.py")

            self.assertEqual(snapshot.content, "safe_call()\n")
            self.assertEqual(len(snapshot.content_sha256), 64)
            with self.assertRaisesRegex(ValueError, "escapes"):
                provider.load("../secret.txt")
            with self.assertRaisesRegex(ValueError, "historical revisions"):
                provider.load("app.py", revision="a" * 40)

    def test_gemini_generator_returns_structured_proposal(self):
        models = FakeModels(
            {
                "unified_diff": _patch().unified_diff,
                "explanation": "Remove the sensitive log value.",
                "addressed_violation_ids": ["violation-1"],
                "addressed_rule_keys": ["SEC-01"],
            }
        )
        generator = GeminiPatchGenerator(
            model="patch-model",
            prompt_version="patch-v1",
            client=SimpleNamespace(models=models),
            thinking_budget=128,
        )

        result = generator.generate(_context())

        self.assertEqual(result.addressed_rule_keys, ("SEC-01",))
        self.assertEqual(models.calls[0]["model"], "patch-model")
        self.assertEqual(models.calls[0]["config"].temperature, 0)
        self.assertIn("proposal only", models.calls[0]["contents"])


def _context():
    return PatchGenerationContext(
        source=SourceSnapshot(
            source_path="app.py",
            content="logger.info(token)\n",
            revision=None,
        ),
        violations=(
            PatchViolation(
                violation_id="violation-1",
                source_path="app.py",
                start_line=1,
                end_line=1,
                input_excerpt="logger.info(token)",
                explanation="Sensitive token is logged.",
                evidence=(
                    PatchRuleEvidence(
                        playbook_chunk_id="chunk-1",
                        rule_key="SEC-01",
                        rule_snapshot="Do not log sensitive values.",
                    ),
                ),
            ),
        ),
    )


def _patch():
    return GeneratedPatch(
        unified_diff=(
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1 +1 @@\n"
            "-logger.info(token)\n"
            "+logger.info('request received')"
        ),
        explanation="Remove the sensitive log value.",
        addressed_violation_ids=("violation-1",),
        addressed_rule_keys=("SEC-01",),
    )


if __name__ == "__main__":
    unittest.main()
