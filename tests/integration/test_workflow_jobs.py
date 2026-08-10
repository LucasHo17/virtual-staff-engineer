import os
import unittest
import uuid

import psycopg

from virtual_staff_engineer.config import require_database_url


try:
    TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL") or require_database_url()
except RuntimeError:
    TEST_DATABASE_URL = None


class WorkflowJobIntegrationTests(unittest.TestCase):
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
        self.analysis_run_ids = []
        self.workflow_job_ids = []

    def tearDown(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                for workflow_job_id in self.workflow_job_ids:
                    cur.execute(
                        """
                        DELETE FROM workflow_job_transitions
                        WHERE workflow_job_id = %s;
                        """,
                        (workflow_job_id,),
                    )
                    cur.execute(
                        "DELETE FROM workflow_jobs WHERE workflow_job_id = %s;",
                        (workflow_job_id,),
                    )
                for analysis_run_id in self.analysis_run_ids:
                    cur.execute(
                        "DELETE FROM analysis_runs WHERE analysis_run_id = %s;",
                        (analysis_run_id,),
                    )

    def test_retry_cycle_records_every_transition_and_terminal_time(self):
        analysis_run_id = self._create_analysis_run()
        workflow_job_id = self._create_job(analysis_run_id)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                self._claim(cur, workflow_job_id, attempt_count=1)
                cur.execute(
                    """
                    UPDATE workflow_jobs
                    SET status = 'retry_scheduled',
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL,
                        failure_code = 'rate_limited',
                        failure_disposition = 'retryable',
                        error_message = 'Retry after provider quota reset.',
                        available_at = CURRENT_TIMESTAMP
                    WHERE workflow_job_id = %s;
                    """,
                    (workflow_job_id,),
                )
                cur.execute(
                    """
                    UPDATE workflow_jobs
                    SET status = 'queued',
                        failure_code = NULL,
                        failure_disposition = NULL,
                        error_message = NULL
                    WHERE workflow_job_id = %s;
                    """,
                    (workflow_job_id,),
                )
                self._claim(cur, workflow_job_id, attempt_count=2)
                cur.execute(
                    """
                    UPDATE workflow_jobs
                    SET status = 'completed',
                        checkpoint = 'analysis_completed',
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL
                    WHERE workflow_job_id = %s;
                    """,
                    (workflow_job_id,),
                )
                cur.execute(
                    """
                    SELECT status, attempt_count, checkpoint,
                           started_at IS NOT NULL, completed_at IS NOT NULL
                    FROM workflow_jobs
                    WHERE workflow_job_id = %s;
                    """,
                    (workflow_job_id,),
                )
                job = cur.fetchone()
                cur.execute(
                    """
                    SELECT from_status, to_status
                    FROM workflow_job_transitions
                    WHERE workflow_job_id = %s
                    ORDER BY transition_sequence;
                    """,
                    (workflow_job_id,),
                )
                transitions = cur.fetchall()

        self.assertEqual(
            job,
            ("completed", 2, "analysis_completed", True, True),
        )
        self.assertEqual(
            transitions,
            [
                (None, "queued"),
                ("queued", "analyzing"),
                ("analyzing", "retry_scheduled"),
                ("retry_scheduled", "queued"),
                ("queued", "analyzing"),
                ("analyzing", "completed"),
            ],
        )

    def test_database_rejects_illegal_state_skip(self):
        analysis_run_id = self._create_analysis_run()
        workflow_job_id = self._create_job(analysis_run_id)

        with self.assertRaises(psycopg.errors.CheckViolation):
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE workflow_jobs
                        SET status = 'approved'
                        WHERE workflow_job_id = %s;
                        """,
                        (workflow_job_id,),
                    )

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM workflow_jobs WHERE workflow_job_id = %s;",
                    (workflow_job_id,),
                )
                self.assertEqual(cur.fetchone()[0], "queued")

    def test_database_rejects_checkpoint_regression(self):
        analysis_run_id = self._create_analysis_run()
        workflow_job_id = self._create_job(analysis_run_id)

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_jobs
                    SET checkpoint = 'patch_validated'
                    WHERE workflow_job_id = %s;
                    """,
                    (workflow_job_id,),
                )

        with self.assertRaises(psycopg.errors.CheckViolation):
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE workflow_jobs
                        SET checkpoint = 'analysis_completed'
                        WHERE workflow_job_id = %s;
                        """,
                        (workflow_job_id,),
                    )

    def test_database_requires_retry_failure_and_active_lease(self):
        analysis_run_id = self._create_analysis_run()
        workflow_job_id = self._create_job(analysis_run_id)

        with self.assertRaises(psycopg.errors.CheckViolation):
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE workflow_jobs
                        SET status = 'analyzing'
                        WHERE workflow_job_id = %s;
                        """,
                        (workflow_job_id,),
                    )

        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                self._claim(cur, workflow_job_id, attempt_count=1)

        with self.assertRaises(psycopg.errors.CheckViolation):
            with psycopg.connect(TEST_DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE workflow_jobs
                        SET status = 'retry_scheduled',
                            lease_owner = NULL,
                            lease_token = NULL,
                            lease_expires_at = NULL,
                            heartbeat_at = NULL
                        WHERE workflow_job_id = %s;
                        """,
                        (workflow_job_id,),
                    )

    def _create_analysis_run(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analysis_runs (
                        status, model_name, workflow_version, prompt_version
                    )
                    VALUES ('queued', 'test-model', 'phase3-test', 'phase3-test')
                    RETURNING analysis_run_id;
                    """
                )
                analysis_run_id = cur.fetchone()[0]
        self.analysis_run_ids.append(analysis_run_id)
        return analysis_run_id

    def _create_job(self, analysis_run_id):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workflow_jobs (analysis_run_id, idempotency_key)
                    VALUES (%s, %s)
                    RETURNING workflow_job_id;
                    """,
                    (analysis_run_id, f"phase3-test-{uuid.uuid4()}"),
                )
                workflow_job_id = cur.fetchone()[0]
        self.workflow_job_ids.append(workflow_job_id)
        return workflow_job_id

    @staticmethod
    def _claim(cur, workflow_job_id, attempt_count):
        cur.execute(
            """
            UPDATE workflow_jobs
            SET status = 'analyzing',
                attempt_count = %s,
                lease_owner = 'integration-worker',
                lease_token = uuid_generate_v4(),
                heartbeat_at = CURRENT_TIMESTAMP,
                lease_expires_at = CURRENT_TIMESTAMP + INTERVAL '5 minutes'
            WHERE workflow_job_id = %s;
            """,
            (attempt_count, workflow_job_id),
        )


if __name__ == "__main__":
    unittest.main()
