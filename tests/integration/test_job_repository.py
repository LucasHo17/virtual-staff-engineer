import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.config import require_database_url
from virtual_staff_engineer.jobs.lifecycle import JobState
from virtual_staff_engineer.jobs.repository import (
    IdempotencyConflictError,
    LeaseLostError,
    WorkflowJobRepository,
)


try:
    TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or require_database_url()
except RuntimeError:
    TEST_DATABASE_URL = None


class WorkflowJobRepositoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TEST_DATABASE_URL:
            raise unittest.SkipTest("Set TEST_DATABASE_URL or DATABASE_URL.")
        try:
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT to_regclass('workflow_jobs') IS NOT NULL;"
                    )
                    if not cur.fetchone()[0]:
                        raise unittest.SkipTest(
                            "Run python scripts/migrate.py before Phase 3 tests."
                        )
        except psycopg.Error as exc:
            raise unittest.SkipTest(
                f"PostgreSQL is unavailable for integration tests: {exc}"
            ) from exc

    def setUp(self):
        self.repository = WorkflowJobRepository(TEST_DATABASE_URL)
        self.idempotency_prefix = f"job-repository-{uuid.uuid4()}"

    def tearDown(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT workflow_job_id, analysis_run_id
                    FROM workflow_jobs
                    WHERE idempotency_key LIKE %s;
                    """,
                    (f"{self.idempotency_prefix}%",),
                )
                rows = cur.fetchall()
                for workflow_job_id, _ in rows:
                    cur.execute(
                        """
                        DELETE FROM workflow_job_transitions
                        WHERE workflow_job_id = %s;
                        """,
                        (workflow_job_id,),
                    )
                cur.execute(
                    """
                    DELETE FROM workflow_jobs
                    WHERE idempotency_key LIKE %s;
                    """,
                    (f"{self.idempotency_prefix}%",),
                )
                for _, analysis_run_id in rows:
                    cur.execute(
                        "DELETE FROM analysis_runs WHERE analysis_run_id = %s;",
                        (analysis_run_id,),
                    )

    def test_submit_is_idempotent_and_rejects_key_reuse(self):
        key = f"{self.idempotency_prefix}-same-request"
        analysis_input = AnalysisInput(
            "code_diff", "safe_call()", "app.py"
        )

        first = self._submit(key, analysis_input)
        second = self._submit(key, analysis_input)

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(
            first.job.workflow_job_id,
            second.job.workflow_job_id,
        )
        self.assertEqual(
            first.job.analysis_run_id,
            second.job.analysis_run_id,
        )
        with self.assertRaises(IdempotencyConflictError):
            self._submit(
                key,
                AnalysisInput("code_diff", "different_call()", "app.py"),
            )
        self.assertEqual(self._job_count(key), 1)
        self.assertEqual(self._analysis_count(analysis_input.content), 1)

    def test_concurrent_duplicate_submission_creates_one_job_and_run(self):
        key = f"{self.idempotency_prefix}-concurrent-submit"
        analysis_input = AnalysisInput(
            "design_document",
            "The service validates every incoming token.",
            "auth.md",
        )

        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(
                executor.map(
                    lambda _: self._submit(key, analysis_input),
                    range(6),
                )
            )

        self.assertEqual(
            len({result.job.workflow_job_id for result in results}),
            1,
        )
        self.assertEqual(sum(result.created for result in results), 1)
        self.assertEqual(self._job_count(key), 1)
        self.assertEqual(self._analysis_count(analysis_input.content), 1)

    def test_claim_respects_priority_and_never_double_claims(self):
        low = self._submit(
            f"{self.idempotency_prefix}-low",
            AnalysisInput("code_diff", "low_priority()", "low.py"),
            priority=10,
        ).job
        high = self._submit(
            f"{self.idempotency_prefix}-high",
            AnalysisInput("code_diff", "high_priority()", "high.py"),
            priority=900,
        ).job

        first = self.repository.claim_next("worker-a", lease_seconds=60)
        second = self.repository.claim_next("worker-b", lease_seconds=60)

        self.assertEqual(first.workflow_job_id, high.workflow_job_id)
        self.assertEqual(second.workflow_job_id, low.workflow_job_id)
        self.assertNotEqual(first.lease_token, second.lease_token)
        self.assertEqual(first.attempt_count, 1)
        self.assertEqual(second.attempt_count, 1)

    def test_concurrent_workers_claim_each_job_at_most_once(self):
        expected_ids = set()
        for index in range(8):
            result = self._submit(
                f"{self.idempotency_prefix}-claim-{index}",
                AnalysisInput(
                    "code_diff",
                    f"process_{index}()",
                    f"worker_{index}.py",
                ),
            )
            expected_ids.add(result.job.workflow_job_id)

        with ThreadPoolExecutor(max_workers=8) as executor:
            claims = list(
                executor.map(
                    lambda index: WorkflowJobRepository(
                        TEST_DATABASE_URL
                    ).claim_next(f"worker-{index}"),
                    range(8),
                )
            )

        claimed_ids = [claim.workflow_job_id for claim in claims if claim]
        self.assertEqual(set(claimed_ids), expected_ids)
        self.assertEqual(len(claimed_ids), len(set(claimed_ids)))

    def test_heartbeat_requires_current_unexpired_lease_token(self):
        submitted = self._submit(
            f"{self.idempotency_prefix}-heartbeat",
            AnalysisInput("code_diff", "heartbeat()", "worker.py"),
        ).job
        claimed = self.repository.claim_next("worker-a", lease_seconds=60)
        self.assertEqual(claimed.workflow_job_id, submitted.workflow_job_id)

        renewed = self.repository.heartbeat(
            claimed.workflow_job_id,
            claimed.lease_token,
            lease_seconds=120,
        )
        self.assertEqual(renewed.lease_token, claimed.lease_token)
        self.assertGreater(renewed.lease_expires_at, claimed.lease_expires_at)

        with self.assertRaises(LeaseLostError):
            self.repository.heartbeat(
                claimed.workflow_job_id,
                uuid.uuid4(),
            )

        self._expire_lease(claimed.workflow_job_id)
        with self.assertRaises(LeaseLostError):
            self.repository.heartbeat(
                claimed.workflow_job_id,
                claimed.lease_token,
            )

    def test_expired_lease_resumes_same_stage_on_next_claim(self):
        submitted = self._submit(
            f"{self.idempotency_prefix}-recover",
            AnalysisInput("code_diff", "recover()", "worker.py"),
            max_attempts=3,
        ).job
        claimed = self.repository.claim_next("worker-a")
        self.assertEqual(claimed.workflow_job_id, submitted.workflow_job_id)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_jobs
                    SET status = 'generating_patch',
                        checkpoint = 'analysis_completed'
                    WHERE workflow_job_id = %s;
                    """,
                    (claimed.workflow_job_id,),
                )
        self._expire_lease(claimed.workflow_job_id)

        recovered = self.repository.recover_expired_leases()
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].status, JobState.RETRY_SCHEDULED)
        self.assertEqual(
            recovered[0].resume_state,
            JobState.GENERATING_PATCH,
        )

        resumed = self.repository.claim_next("worker-b")
        self.assertEqual(resumed.workflow_job_id, claimed.workflow_job_id)
        self.assertEqual(resumed.status, JobState.GENERATING_PATCH)
        self.assertEqual(resumed.attempt_count, 2)

    def test_expired_final_attempt_becomes_terminal_failure(self):
        submitted = self._submit(
            f"{self.idempotency_prefix}-exhausted",
            AnalysisInput("code_diff", "fail_once()", "worker.py"),
            max_attempts=1,
        ).job
        claimed = self.repository.claim_next("worker-a")
        self.assertEqual(claimed.workflow_job_id, submitted.workflow_job_id)
        self._expire_lease(claimed.workflow_job_id)

        recovered = self.repository.recover_expired_leases()

        self.assertEqual(recovered[0].status, JobState.FAILED)
        self.assertEqual(recovered[0].failure_code, "lease_expired")
        self.assertIsNotNone(recovered[0].completed_at)
        self.assertIsNone(self.repository.claim_next("worker-b"))

    def _submit(
        self,
        key,
        analysis_input,
        priority=100,
        max_attempts=3,
    ):
        return self.repository.submit(
            analysis_input,
            idempotency_key=key,
            model_name="test-model",
            workflow_version="phase3-test",
            prompt_version="phase3-test",
            priority=priority,
            max_attempts=max_attempts,
        )

    def _job_count(self, key):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*)
                    FROM workflow_jobs
                    WHERE idempotency_key = %s;
                    """,
                    (key,),
                )
                return cur.fetchone()[0]

    def _analysis_count(self, input_content):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*)
                    FROM analysis_runs
                    WHERE input_content = %s;
                    """,
                    (input_content,),
                )
                return cur.fetchone()[0]

    @staticmethod
    def _expire_lease(workflow_job_id):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_jobs
                    SET heartbeat_at = CURRENT_TIMESTAMP - INTERVAL '2 minutes',
                        lease_expires_at = CURRENT_TIMESTAMP - INTERVAL '1 minute'
                    WHERE workflow_job_id = %s;
                    """,
                    (workflow_job_id,),
                )


if __name__ == "__main__":
    unittest.main()
