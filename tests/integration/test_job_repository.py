import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg

from virtual_staff_engineer.analysis.contracts import (
    AnalysisInput,
    EvaluationDecision,
    ProposedFinding,
    RuleEvidence,
    SearchQuery,
)
from virtual_staff_engineer.analysis.orchestrator import AnalysisResult
from virtual_staff_engineer.config import require_database_url
from virtual_staff_engineer.jobs.lifecycle import (
    FailureCode,
    JobFailure,
    JobState,
)
from virtual_staff_engineer.jobs.repository import (
    IdempotencyConflictError,
    LeaseLostError,
    WorkflowJobRepository,
)
from virtual_staff_engineer.remediation.contracts import (
    GeneratedPatch,
    PatchGenerationContext,
    SourceSnapshot,
)
from virtual_staff_engineer.remediation.validation import (
    DeterministicPatchValidator,
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
                    SELECT workflow_job_id,
                           analysis_run_id,
                           remediation_action_id
                    FROM workflow_jobs
                    WHERE idempotency_key LIKE %s;
                    """,
                    (f"{self.idempotency_prefix}%",),
                )
                rows = cur.fetchall()
                for workflow_job_id, _, remediation_action_id in rows:
                    cur.execute(
                        """
                        DELETE FROM workflow_job_transitions
                        WHERE workflow_job_id = %s;
                        """,
                        (workflow_job_id,),
                    )
                    if remediation_action_id is not None:
                        cur.execute(
                            """
                            DELETE FROM patch_validation_checks
                            WHERE patch_validation_id IN (
                                SELECT pvr.patch_validation_id
                                FROM patch_validation_runs AS pvr
                                JOIN patch_proposals AS pp
                                  ON pp.patch_proposal_id =
                                     pvr.patch_proposal_id
                                WHERE pp.remediation_action_id = %s
                            );
                            """,
                            (remediation_action_id,),
                        )
                        cur.execute(
                            """
                            DELETE FROM patch_validation_runs
                            WHERE patch_proposal_id IN (
                                SELECT patch_proposal_id
                                FROM patch_proposals
                                WHERE remediation_action_id = %s
                            );
                            """,
                            (remediation_action_id,),
                        )
                        cur.execute(
                            """
                            DELETE FROM patch_proposal_rules
                            WHERE patch_proposal_id IN (
                                SELECT patch_proposal_id
                                FROM patch_proposals
                                WHERE remediation_action_id = %s
                            );
                            """,
                            (remediation_action_id,),
                        )
                        cur.execute(
                            """
                            DELETE FROM patch_proposals
                            WHERE remediation_action_id = %s;
                            """,
                            (remediation_action_id,),
                        )
                        cur.execute(
                            """
                            DELETE FROM remediation_action_violations
                            WHERE remediation_action_id = %s;
                            """,
                            (remediation_action_id,),
                        )
                cur.execute(
                    """
                    DELETE FROM workflow_jobs
                    WHERE idempotency_key LIKE %s;
                    """,
                    (f"{self.idempotency_prefix}%",),
                )
                for _, _, remediation_action_id in rows:
                    if remediation_action_id is not None:
                        cur.execute(
                            """
                            DELETE FROM remediation_actions
                            WHERE remediation_action_id = %s;
                            """,
                            (remediation_action_id,),
                        )
                for _, analysis_run_id, _ in rows:
                    cur.execute(
                        """
                        DELETE FROM violation_evidence
                        WHERE violation_id IN (
                            SELECT violation_id FROM violations
                            WHERE analysis_run_id = %s
                        );
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        "DELETE FROM violations WHERE analysis_run_id = %s;",
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_finding_reviews
                        WHERE analysis_run_id = %s;
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_retrieval_evidence
                        WHERE analysis_query_id IN (
                            SELECT analysis_query_id
                            FROM analysis_run_queries
                            WHERE analysis_run_id = %s
                        );
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_run_queries
                        WHERE analysis_run_id = %s;
                        """,
                        (analysis_run_id,),
                    )
                    cur.execute(
                        """
                        DELETE FROM analysis_run_playbook_versions
                        WHERE analysis_run_id = %s;
                        """,
                        (analysis_run_id,),
                    )
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

    def test_retryable_failure_is_delayed_and_preserves_analysis(self):
        submitted = self._submit(
            f"{self.idempotency_prefix}-retryable",
            AnalysisInput("code_diff", "retry_me()", "worker.py"),
            max_attempts=2,
        ).job
        claimed = self.repository.claim_next("worker-a")
        self.repository.begin_analysis(
            claimed.workflow_job_id, claimed.lease_token
        )

        scheduled = self.repository.schedule_failure(
            claimed.workflow_job_id,
            claimed.lease_token,
            JobFailure(FailureCode.PROVIDER_TIMEOUT, "provider timed out"),
            delay_seconds=30,
        )

        self.assertEqual(scheduled.status, JobState.RETRY_SCHEDULED)
        self.assertEqual(scheduled.resume_state, JobState.ANALYZING)
        self.assertGreater(scheduled.available_at, claimed.available_at)
        self.assertIsNone(scheduled.lease_token)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM analysis_runs WHERE analysis_run_id = %s;",
                    (submitted.analysis_run_id,),
                )
                self.assertEqual(cur.fetchone()[0], "analyzing")

    def test_permanent_failure_terminates_job_and_analysis(self):
        submitted = self._submit(
            f"{self.idempotency_prefix}-permanent",
            AnalysisInput("code_diff", "bad_contract()", "worker.py"),
        ).job
        claimed = self.repository.claim_next("worker-a")
        self.repository.begin_analysis(
            claimed.workflow_job_id, claimed.lease_token
        )

        failed = self.repository.schedule_failure(
            claimed.workflow_job_id,
            claimed.lease_token,
            JobFailure(
                FailureCode.MODEL_CONTRACT_INVALID,
                "model response did not match the contract",
            ),
        )

        self.assertEqual(failed.status, JobState.FAILED)
        self.assertEqual(failed.failure_disposition, "permanent")
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM analysis_runs WHERE analysis_run_id = %s;",
                    (submitted.analysis_run_id,),
                )
                self.assertEqual(cur.fetchone()[0], "failed")

    def test_analysis_completion_is_atomic_and_idempotent(self):
        submitted = self._submit(
            f"{self.idempotency_prefix}-complete",
            AnalysisInput("code_diff", "safe_call()", "worker.py"),
        ).job
        claimed = self.repository.claim_next("worker-a")
        self.repository.begin_analysis(
            claimed.workflow_job_id, claimed.lease_token
        )
        result = AnalysisResult(
            status="completed_clean",
            findings=(),
            evaluated_findings=(),
            decisions=(),
            rejected_findings=(),
            evidence=(),
            queries=(),
            iterations=1,
        )

        completed = self.repository.complete_analysis(
            claimed.workflow_job_id, claimed.lease_token, result
        )
        repeated = self.repository.complete_analysis(
            claimed.workflow_job_id, claimed.lease_token, result
        )

        self.assertEqual(completed.status, JobState.COMPLETED)
        self.assertEqual(completed.checkpoint.value, "analysis_completed")
        self.assertEqual(repeated.workflow_job_id, completed.workflow_job_id)
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM analysis_runs WHERE analysis_run_id = %s;",
                    (submitted.analysis_run_id,),
                )
                self.assertEqual(cur.fetchone()[0], "completed_clean")

    def test_supported_analysis_queues_patch_stage_without_lease(self):
        evidence = self._load_rule_evidence()
        analysis_input = AnalysisInput(
            "code_diff", "unsafe_call()", "worker.py"
        )
        submitted = self._submit(
            f"{self.idempotency_prefix}-handoff", analysis_input
        ).job
        claimed = self.repository.claim_next("analysis-worker")
        self.repository.begin_analysis(
            claimed.workflow_job_id, claimed.lease_token
        )
        finding = ProposedFinding(
            rule_key=evidence.rule_key,
            playbook_chunk_id=evidence.playbook_chunk_id,
            source_path="worker.py",
            start_line=1,
            end_line=1,
            input_excerpt="unsafe_call()",
            explanation="The input violates the cited rule.",
            severity="high",
            confidence=0.9,
        )
        result = AnalysisResult(
            status="review_required",
            findings=(finding,),
            evaluated_findings=(finding,),
            decisions=(
                EvaluationDecision(0, "supported", "Evidence matches."),
            ),
            rejected_findings=(),
            evidence=(evidence,),
            queries=(
                SearchQuery(evidence.retrieval_query, "Find governing rule."),
            ),
            iterations=1,
        )

        handed_off = self.repository.complete_analysis(
            claimed.workflow_job_id, claimed.lease_token, result
        )

        self.assertEqual(handed_off.status, JobState.QUEUED)
        self.assertEqual(handed_off.resume_state, JobState.GENERATING_PATCH)
        self.assertIsNone(handed_off.lease_token)
        patch_claim = self.repository.claim_next("patch-worker")
        self.assertEqual(patch_claim.workflow_job_id, submitted.workflow_job_id)
        self.assertEqual(patch_claim.status, JobState.GENERATING_PATCH)
        seed = self.repository.begin_patch_generation(
            patch_claim.workflow_job_id, patch_claim.lease_token
        )
        context = PatchGenerationContext(
            source=SourceSnapshot(
                source_path=seed.source_path,
                content="unsafe_call()\n",
                revision=seed.source_revision,
            ),
            violations=seed.violations,
        )
        generated = GeneratedPatch(
            unified_diff=(
                "--- a/worker.py\n"
                "+++ b/worker.py\n"
                "@@ -1 +1 @@\n"
                "-unsafe_call()\n"
                "+safe_call()"
            ),
            explanation="Replace the unsafe behavior.",
            addressed_violation_ids=tuple(
                violation.violation_id for violation in seed.violations
            ),
            addressed_rule_keys=tuple(
                sorted(
                    {
                        item.rule_key
                        for violation in seed.violations
                        for item in violation.evidence
                    }
                )
            ),
        )

        validation_ready = self.repository.complete_patch_generation(
            patch_claim.workflow_job_id,
            patch_claim.lease_token,
            context,
            generated,
            model_name="test-patch-model",
            prompt_version="patch-v1",
        )
        repeated = self.repository.complete_patch_generation(
            patch_claim.workflow_job_id,
            patch_claim.lease_token,
            context,
            generated,
            model_name="test-patch-model",
            prompt_version="patch-v1",
        )

        self.assertEqual(validation_ready.status, JobState.QUEUED)
        self.assertEqual(
            validation_ready.resume_state, JobState.VALIDATING_PATCH
        )
        self.assertEqual(
            validation_ready.checkpoint.value, "patch_generated"
        )
        self.assertIsNone(validation_ready.lease_token)
        self.assertIsNotNone(validation_ready.remediation_action_id)
        self.assertEqual(
            repeated.remediation_action_id,
            validation_ready.remediation_action_id,
        )
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pp.source_path,
                           pp.original_content,
                           pp.original_sha256,
                           pp.unified_diff,
                           pp.explanation,
                           pp.model_name,
                           pp.prompt_version,
                           (SELECT count(*)
                            FROM remediation_action_violations AS rav
                            WHERE rav.remediation_action_id =
                                  pp.remediation_action_id),
                           (SELECT count(*)
                            FROM patch_proposal_rules AS ppr
                            WHERE ppr.patch_proposal_id = pp.patch_proposal_id)
                    FROM patch_proposals AS pp
                    WHERE pp.remediation_action_id = %s;
                    """,
                    (validation_ready.remediation_action_id,),
                )
                proposal = cur.fetchone()
        self.assertEqual(proposal[0], "worker.py")
        self.assertEqual(proposal[1], "unsafe_call()\n")
        self.assertEqual(len(proposal[2]), 64)
        self.assertEqual(proposal[3], generated.unified_diff)
        self.assertEqual(proposal[4], generated.explanation)
        self.assertEqual(proposal[5:7], ("test-patch-model", "patch-v1"))
        self.assertEqual(proposal[7], len(seed.violations))
        self.assertGreaterEqual(proposal[8], 1)

        validation_claim = self.repository.claim_next("validation-worker")
        self.assertEqual(
            validation_claim.workflow_job_id, submitted.workflow_job_id
        )
        self.assertEqual(
            validation_claim.status, JobState.VALIDATING_PATCH
        )
        persisted_proposal = self.repository.begin_patch_validation(
            validation_claim.workflow_job_id,
            validation_claim.lease_token,
        )
        validator = DeterministicPatchValidator()
        validation_result = validator.validate(
            persisted_proposal,
            SourceSnapshot("worker.py", "unsafe_call()\n"),
        )
        approval_ready = self.repository.complete_patch_validation(
            validation_claim.workflow_job_id,
            validation_claim.lease_token,
            persisted_proposal,
            validation_result,
            validator_version=validator.version,
        )
        repeated_validation = self.repository.complete_patch_validation(
            validation_claim.workflow_job_id,
            validation_claim.lease_token,
            persisted_proposal,
            validation_result,
            validator_version=validator.version,
        )

        self.assertEqual(
            approval_ready.status, JobState.AWAITING_APPROVAL
        )
        self.assertEqual(
            approval_ready.checkpoint.value, "patch_validated"
        )
        self.assertIsNone(approval_ready.lease_token)
        self.assertEqual(
            repeated_validation.workflow_job_id,
            approval_ready.workflow_job_id,
        )
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pvr.status,
                           pvr.validator_version,
                           pvr.changed_lines,
                           pvr.resulting_sha256,
                           count(pvc.check_name)
                    FROM patch_validation_runs AS pvr
                    JOIN patch_validation_checks AS pvc
                      ON pvc.patch_validation_id = pvr.patch_validation_id
                    WHERE pvr.patch_proposal_id = %s
                    GROUP BY pvr.patch_validation_id;
                    """,
                    (persisted_proposal.patch_proposal_id,),
                )
                validation_row = cur.fetchone()
        self.assertEqual(validation_row[0], "valid")
        self.assertEqual(validation_row[1], "deterministic-v1")
        self.assertEqual(validation_row[2], 2)
        self.assertEqual(len(validation_row[3]), 64)
        self.assertEqual(validation_row[4], 5)

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

    @staticmethod
    def _load_rule_evidence():
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pc.playbook_chunk_id,
                           pc.playbook_version_id,
                           pc.rule_key,
                           pd.filename,
                           pc.section,
                           pc.content
                    FROM playbook_chunks AS pc
                    JOIN playbook_versions AS pv
                      ON pv.playbook_version_id = pc.playbook_version_id
                    JOIN playbook_documents AS pd
                      ON pd.document_id = pv.document_id
                    WHERE pd.archived_at IS NULL
                    ORDER BY pc.created_at
                    LIMIT 1;
                    """
                )
                row = cur.fetchone()
        if row is None:
            raise unittest.SkipTest("Ingest a playbook before this test.")
        return RuleEvidence(
            playbook_chunk_id=str(row[0]),
            playbook_version_id=str(row[1]),
            rule_key=row[2],
            filename=row[3],
            section=row[4],
            content=row[5],
            retrieval_query="governing engineering rule",
            rank_position=1,
            retrieval_score=1.0,
            semantic_rank=1,
        )


if __name__ == "__main__":
    unittest.main()
