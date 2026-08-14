import hashlib
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone

import psycopg

from virtual_staff_engineer.config import require_database_url
from virtual_staff_engineer.github import (
    GitHubDeliveryConflictError,
    GitHubPullRequestDelivery,
    GitHubPullRequestFile,
    GitHubPullRequestSnapshot,
    GitHubWebhookClaim,
    GitHubWebhookDeliveryRepository,
)
from virtual_staff_engineer.remediation import GitHubSnapshotSourceProvider


try:
    TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or require_database_url()
except RuntimeError:
    TEST_DATABASE_URL = None


class GitHubWebhookRepositoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TEST_DATABASE_URL:
            raise unittest.SkipTest("Set TEST_DATABASE_URL or DATABASE_URL.")
        try:
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT to_regclass('github_pr_file_snapshots') "
                        "IS NOT NULL;"
                    )
                    if not cur.fetchone()[0]:
                        raise unittest.SkipTest(
                            "Run python scripts/migrate.py before webhook tests."
                        )
        except psycopg.Error as exc:
            raise unittest.SkipTest(
                f"PostgreSQL is unavailable for integration tests: {exc}"
            ) from exc

    def setUp(self):
        self.delivery_id = "webhook-test-" + str(uuid.uuid4())
        self.repository_name = "demo-" + str(uuid.uuid4())
        self.repository = GitHubWebhookDeliveryRepository(TEST_DATABASE_URL)

    def tearDown(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM github_pr_file_snapshots
                    WHERE commit_id IN (
                        SELECT commit.commit_id
                        FROM commits AS commit
                        JOIN repositories AS repository
                          ON repository.repository_id = commit.repository_id
                        WHERE repository.owner = 'webhook-test-owner'
                          AND repository.name = %s
                    );
                    """,
                    (self.repository_name,),
                )
                cur.execute(
                    """
                    DELETE FROM commits
                    WHERE repository_id IN (
                        SELECT repository_id FROM repositories
                        WHERE owner = 'webhook-test-owner' AND name = %s
                    );
                    """,
                    (self.repository_name,),
                )
                cur.execute(
                    "DELETE FROM repositories "
                    "WHERE owner = 'webhook-test-owner' AND name = %s;",
                    (self.repository_name,),
                )
                cur.execute(
                    "DELETE FROM github_webhook_deliveries "
                    "WHERE delivery_id = %s;",
                    (self.delivery_id,),
                )

    def test_records_once_and_rejects_delivery_identity_conflict(self):
        delivery = self._delivery()

        first = self.repository.record(delivery)
        duplicate = self.repository.record(delivery)

        self.assertTrue(first.created)
        self.assertFalse(duplicate.created)
        with self.assertRaises(GitHubDeliveryConflictError):
            self.repository.record(self._delivery(head_sha="b" * 40))

    def test_persists_and_reads_immutable_pr_source_snapshot(self):
        delivery = self._delivery()
        self.repository.record(delivery)
        lease_token = str(uuid.uuid4())
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE github_webhook_deliveries
                    SET status = 'processing',
                        attempt_count = 1,
                        lease_owner = 'integration-test',
                        lease_token = %s,
                        lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '5 minutes'
                    WHERE delivery_id = %s;
                    """,
                    (lease_token, self.delivery_id),
                )
        claim = GitHubWebhookClaim(
            delivery=delivery,
            status="processing",
            attempt_count=1,
            max_attempts=5,
            lease_owner="integration-test",
            lease_token=lease_token,
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        snapshot = GitHubPullRequestSnapshot(
            repository_owner=delivery.repository_owner,
            repository_name=delivery.repository_name,
            installation_id=delivery.installation_id,
            pull_request_number=delivery.pull_request_number,
            title="Integration PR",
            html_url=(
                "https://github.com/webhook-test-owner/"
                + self.repository_name
                + "/pull/7"
            ),
            head_sha=delivery.head_sha,
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

        self.repository.persist_snapshot(claim, snapshot)
        source = GitHubSnapshotSourceProvider(TEST_DATABASE_URL).load(
            "app.py", revision=delivery.head_sha
        )

        self.assertEqual(source.content, "new\n")
        self.assertEqual(source.revision, delivery.head_sha)

    def _delivery(self, head_sha="a" * 40):
        payload_hash = hashlib.sha256(head_sha.encode("utf-8")).hexdigest()
        return GitHubPullRequestDelivery(
            delivery_id=self.delivery_id,
            event_name="pull_request",
            action="opened",
            repository_owner="webhook-test-owner",
            repository_name=self.repository_name,
            installation_id=123,
            pull_request_number=7,
            head_sha=head_sha,
            payload_sha256=payload_hash,
        )


if __name__ == "__main__":
    unittest.main()
