import hashlib
import os
import unittest
import uuid

import psycopg

from virtual_staff_engineer.config import require_database_url
from virtual_staff_engineer.github import (
    GitHubDeliveryConflictError,
    GitHubPullRequestDelivery,
    GitHubWebhookDeliveryRepository,
)


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
                        "SELECT to_regclass('github_webhook_deliveries') "
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
        self.repository = GitHubWebhookDeliveryRepository(TEST_DATABASE_URL)

    def tearDown(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
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

    def _delivery(self, head_sha="a" * 40):
        payload_hash = hashlib.sha256(head_sha.encode("utf-8")).hexdigest()
        return GitHubPullRequestDelivery(
            delivery_id=self.delivery_id,
            event_name="pull_request",
            action="opened",
            repository_owner="example",
            repository_name="demo",
            installation_id=123,
            pull_request_number=7,
            head_sha=head_sha,
            payload_sha256=payload_hash,
        )


if __name__ == "__main__":
    unittest.main()
