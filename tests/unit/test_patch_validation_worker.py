import hashlib
import unittest
from types import SimpleNamespace

from virtual_staff_engineer.jobs.lifecycle import JobState
from virtual_staff_engineer.jobs.worker import PatchValidationWorker
from virtual_staff_engineer.remediation.contracts import (
    PersistedPatchProposal,
    SourceSnapshot,
)
from virtual_staff_engineer.remediation.validation import (
    DeterministicPatchValidator,
)


class FakeRepository:
    def __init__(self, job):
        self.job = job
        self.claim_calls = []
        self.completed = []
        self.failures = []

    def claim_next(self, worker_id, **options):
        self.claim_calls.append((worker_id, options))
        return self.job

    def begin_patch_validation(self, workflow_job_id, lease_token):
        return _proposal()

    def heartbeat(self, *args, **kwargs):
        return self.job

    def complete_patch_validation(self, *args, **kwargs):
        self.completed.append((args, kwargs))
        result = args[3]
        status = (
            JobState.AWAITING_APPROVAL
            if result.status == "valid"
            else JobState.FAILED
        )
        return SimpleNamespace(status=status)

    def schedule_failure(self, *args, **kwargs):
        self.failures.append((args, kwargs))
        return SimpleNamespace(status=JobState.FAILED)


class FakeSourceProvider:
    def __init__(self, content):
        self.content = content

    def load(self, source_path):
        return SourceSnapshot(source_path, self.content)


class PatchValidationWorkerTests(unittest.TestCase):
    def test_valid_patch_advances_to_approval(self):
        repository = FakeRepository(_job())
        worker = PatchValidationWorker(
            "validator-1",
            DeterministicPatchValidator(),
            FakeSourceProvider("logger.info(token)\n"),
            repository,
            lease_seconds=3,
        )

        execution = worker.run_once()

        self.assertEqual(execution.job.status, JobState.AWAITING_APPROVAL)
        self.assertEqual(
            repository.claim_calls[0][1]["resume_states"],
            (JobState.VALIDATING_PATCH,),
        )
        self.assertEqual(
            repository.completed[0][1]["validator_version"],
            "deterministic-v1",
        )

    def test_stale_source_persists_invalid_result_without_retry(self):
        repository = FakeRepository(_job())
        worker = PatchValidationWorker(
            "validator-1",
            DeterministicPatchValidator(),
            FakeSourceProvider("changed()\n"),
            repository,
            lease_seconds=3,
        )

        execution = worker.run_once()

        self.assertEqual(execution.job.status, JobState.FAILED)
        self.assertEqual(repository.completed[0][0][3].status, "invalid")
        self.assertEqual(repository.failures, [])


def _job():
    return SimpleNamespace(
        workflow_job_id="job-1",
        lease_token="lease-1",
        attempt_count=1,
    )


def _proposal():
    original = "logger.info(token)\n"
    return PersistedPatchProposal(
        patch_proposal_id="proposal-1",
        remediation_action_id="action-1",
        source_path="app.py",
        source_revision=None,
        original_content=original,
        original_sha256=hashlib.sha256(original.encode()).hexdigest(),
        unified_diff=(
            "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n"
            "-logger.info(token)\n+logger.info('request received')"
        ),
    )


if __name__ == "__main__":
    unittest.main()
