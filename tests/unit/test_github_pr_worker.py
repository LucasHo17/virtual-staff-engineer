import unittest
from types import SimpleNamespace

from virtual_staff_engineer.github import (
    GitHubPullRequestResult,
    GitHubStaleSourceError,
)
from virtual_staff_engineer.jobs import GitHubPullRequestWorker, JobState
from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy


class FakeRepository:
    def __init__(self, job=None):
        self.job = job
        self.completed = []
        self.failures = []

    def claim_pr_next(self, worker_id, lease_seconds):
        return self.job

    def begin_pr_creation(self, workflow_job_id, lease_token):
        return object()

    def heartbeat(self, *args, **kwargs):
        return self.job

    def complete_pr_creation(self, *args):
        self.completed.append(args)
        return SimpleNamespace(status=JobState.COMPLETED)

    def schedule_failure(self, *args, **kwargs):
        self.failures.append((args, kwargs))
        failure = args[2]
        state = (
            JobState.RETRY_SCHEDULED
            if failure.disposition.value == "retryable"
            else JobState.FAILED
        )
        return SimpleNamespace(status=state)


class FakeClient:
    def __init__(self, error=None):
        self.error = error

    def ensure_pull_request(self, context):
        if self.error:
            raise self.error
        return GitHubPullRequestResult(
            "vse/remediation-1",
            "c" * 40,
            7,
            "https://github.com/acme/service/pull/7",
        )


def job(attempt_count=1):
    return SimpleNamespace(
        workflow_job_id="job-1",
        lease_token="lease-1",
        attempt_count=attempt_count,
    )


class GitHubPullRequestWorkerTests(unittest.TestCase):
    def test_completes_reconciled_pull_request(self):
        repository = FakeRepository(job())
        execution = GitHubPullRequestWorker(
            "pr-worker", FakeClient(), repository, lease_seconds=3
        ).run_once()
        self.assertEqual(execution.job.status, JobState.COMPLETED)
        self.assertEqual(len(repository.completed), 1)
        self.assertEqual(repository.failures, [])

    def test_network_failure_is_retried_with_backoff(self):
        repository = FakeRepository(job(attempt_count=2))
        execution = GitHubPullRequestWorker(
            "pr-worker",
            FakeClient(ConnectionError("offline")),
            repository,
            lease_seconds=3,
            backoff_policy=ExponentialBackoffPolicy(
                base_seconds=5, maximum_seconds=60, jitter_ratio=0
            ),
        ).run_once()
        self.assertEqual(execution.job.status, JobState.RETRY_SCHEDULED)
        self.assertEqual(repository.failures[0][0][2].code.value, "github_unavailable")
        self.assertEqual(repository.failures[0][1]["delay_seconds"], 10)

    def test_stale_source_is_permanent(self):
        repository = FakeRepository(job())
        execution = GitHubPullRequestWorker(
            "pr-worker",
            FakeClient(GitHubStaleSourceError("changed")),
            repository,
            lease_seconds=3,
        ).run_once()
        self.assertEqual(execution.job.status, JobState.FAILED)
        self.assertEqual(repository.failures[0][0][2].code.value, "stale_source")


if __name__ == "__main__":
    unittest.main()
