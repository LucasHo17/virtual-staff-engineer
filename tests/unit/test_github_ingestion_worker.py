import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from virtual_staff_engineer.github import (
    GitHubPullRequestDelivery,
    GitHubPullRequestFile,
    GitHubPullRequestSnapshot,
    GitHubWebhookClaim,
    GitHubWebhookIngestionWorker,
)
from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy


class FakeDeliveryRepository:
    def __init__(self, claim):
        self.claim = claim
        self.persisted = []
        self.links = []
        self.completed = []
        self.failures = []

    def claim_next(self, *args, **kwargs):
        claim, self.claim = self.claim, None
        return claim

    def persist_snapshot(self, claim, snapshot):
        self.persisted.append((claim, snapshot))
        return "00000000-0000-0000-0000-000000000001"

    def link_job(self, *args):
        self.links.append(args)

    def complete(self, claim, snapshot):
        self.completed.append((claim, snapshot))
        return "completed"

    def schedule_failure(self, claim, failure, delay_seconds=0):
        self.failures.append((claim, failure, delay_seconds))
        return "retry_scheduled" if failure.disposition.value == "retryable" else "failed"


class FakeWorkflowRepository:
    def __init__(self):
        self.submissions = []

    def submit(self, analysis_input, **options):
        self.submissions.append((analysis_input, options))
        return SimpleNamespace(
            job=SimpleNamespace(workflow_job_id=f"job-{len(self.submissions)}")
        )


class GitHubIngestionWorkerTests(unittest.TestCase):
    def test_submits_idempotent_per_file_jobs_and_completes_delivery(self):
        delivery_repository = FakeDeliveryRepository(_claim())
        workflow_repository = FakeWorkflowRepository()
        worker = GitHubWebhookIngestionWorker(
            "ingestion-1",
            SimpleNamespace(fetch_pull_request=lambda _: _snapshot()),
            delivery_repository,
            workflow_repository,
            model_name="test-model",
        )

        execution = worker.run_once()

        self.assertTrue(execution.claimed)
        self.assertEqual(execution.status, "completed")
        self.assertEqual(execution.workflow_job_ids, ("job-1",))
        analysis_input, options = workflow_repository.submissions[0]
        self.assertEqual(analysis_input.source_path, "app.py")
        self.assertEqual(
            analysis_input.commit_id,
            "00000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(options["workflow_version"], "phase5-github-v1")
        self.assertIn("pr:7:head:", options["idempotency_key"])
        self.assertEqual(delivery_repository.links[0][1:], ("job-1", "app.py"))
        self.assertEqual(len(delivery_repository.completed), 1)

    def test_transient_fetch_failure_is_scheduled_for_retry(self):
        delivery_repository = FakeDeliveryRepository(_claim())

        def fail(_):
            raise ConnectionError("temporary network failure")

        worker = GitHubWebhookIngestionWorker(
            "ingestion-1",
            SimpleNamespace(fetch_pull_request=fail),
            delivery_repository,
            FakeWorkflowRepository(),
            model_name="test-model",
            backoff_policy=ExponentialBackoffPolicy(
                base_seconds=1, maximum_seconds=1, jitter_ratio=0
            ),
        )

        execution = worker.run_once()

        self.assertEqual(execution.status, "retry_scheduled")
        self.assertEqual(delivery_repository.failures[0][1].code.value, "github_unavailable")
        self.assertEqual(delivery_repository.failures[0][2], 1)

    def test_returns_unclaimed_when_queue_is_empty(self):
        execution = GitHubWebhookIngestionWorker(
            "ingestion-1",
            SimpleNamespace(),
            FakeDeliveryRepository(None),
            FakeWorkflowRepository(),
            model_name="test-model",
        ).run_once()

        self.assertFalse(execution.claimed)


def _claim():
    now = datetime.now(timezone.utc)
    return GitHubWebhookClaim(
        delivery=_delivery(),
        status="processing",
        attempt_count=1,
        max_attempts=5,
        lease_owner="ingestion-1",
        lease_token="00000000-0000-0000-0000-000000000002",
        lease_expires_at=now + timedelta(minutes=5),
    )


def _delivery():
    return GitHubPullRequestDelivery(
        delivery_id="delivery-1",
        event_name="pull_request",
        action="opened",
        repository_owner="example",
        repository_name="demo",
        installation_id=42,
        pull_request_number=7,
        head_sha="a" * 40,
        payload_sha256=hashlib.sha256(b"payload").hexdigest(),
    )


def _snapshot():
    return GitHubPullRequestSnapshot(
        repository_owner="example",
        repository_name="demo",
        installation_id=42,
        pull_request_number=7,
        title="Test PR",
        html_url="https://github.com/example/demo/pull/7",
        head_sha="a" * 40,
        base_sha="b" * 40,
        files=(
            GitHubPullRequestFile(
                filename="app.py",
                blob_sha="c" * 40,
                status="modified",
                additions=1,
                deletions=1,
                changes=2,
                patch="@@ -1 +1 @@\n-old\n+new",
                source_content="new\n",
            ),
        ),
    )


if __name__ == "__main__":
    unittest.main()
