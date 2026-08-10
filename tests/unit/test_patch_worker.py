import unittest
from types import SimpleNamespace

from virtual_staff_engineer.jobs.lifecycle import JobState
from virtual_staff_engineer.jobs.worker import PatchGenerationWorker
from virtual_staff_engineer.remediation.contracts import (
    GeneratedPatch,
    PatchGenerationSeed,
    PatchRuleEvidence,
    PatchViolation,
    SourceSnapshot,
)


class FakePatchRepository:
    def __init__(self, job=None):
        self.job = job
        self.claim_calls = []
        self.completed = []
        self.failures = []

    def claim_next(self, worker_id, **options):
        self.claim_calls.append((worker_id, options))
        return self.job

    def begin_patch_generation(self, workflow_job_id, lease_token):
        return _seed()

    def heartbeat(self, *args, **kwargs):
        return self.job

    def complete_patch_generation(self, *args, **kwargs):
        self.completed.append((args, kwargs))
        return SimpleNamespace(status=JobState.QUEUED)

    def schedule_failure(
        self, workflow_job_id, lease_token, failure, delay_seconds
    ):
        self.failures.append(failure)
        return SimpleNamespace(status=JobState.FAILED)


class FakeSourceProvider:
    def __init__(self, error=None):
        self.error = error

    def load(self, source_path, revision=None):
        if self.error:
            raise self.error
        return SourceSnapshot(source_path, "logger.info(token)\n", revision)


class FakeGenerator:
    model = "patch-model"
    prompt_version = "patch-v1"

    def generate(self, context):
        return GeneratedPatch(
            unified_diff=(
                "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
                "-logger.info(token)\n+logger.info('request received')"
            ),
            explanation="Remove sensitive logging.",
            addressed_violation_ids=("violation-1",),
            addressed_rule_keys=("SEC-01",),
        )


class PatchGenerationWorkerTests(unittest.TestCase):
    def test_claims_only_patch_stage_and_persists_proposal(self):
        repository = FakePatchRepository(_job())
        worker = PatchGenerationWorker(
            "patch-worker",
            FakeGenerator(),
            FakeSourceProvider(),
            repository,
            lease_seconds=3,
        )

        execution = worker.run_once()

        self.assertTrue(execution.claimed)
        self.assertEqual(
            repository.claim_calls[0][1]["resume_states"],
            (JobState.GENERATING_PATCH,),
        )
        self.assertEqual(
            repository.completed[0][1]["model_name"], "patch-model"
        )
        self.assertEqual(repository.failures, [])

    def test_missing_source_is_a_permanent_stale_source_failure(self):
        repository = FakePatchRepository(_job())
        worker = PatchGenerationWorker(
            "patch-worker",
            FakeGenerator(),
            FakeSourceProvider(FileNotFoundError("missing app.py")),
            repository,
            lease_seconds=3,
        )

        execution = worker.run_once()

        self.assertEqual(execution.job.status, JobState.FAILED)
        self.assertEqual(repository.failures[0].code.value, "stale_source")


def _job():
    return SimpleNamespace(
        workflow_job_id="job-1",
        lease_token="lease-1",
        attempt_count=1,
    )


def _seed():
    return PatchGenerationSeed(
        source_path="app.py",
        source_revision=None,
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
                        "chunk-1",
                        "SEC-01",
                        "Do not log sensitive values.",
                    ),
                ),
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
