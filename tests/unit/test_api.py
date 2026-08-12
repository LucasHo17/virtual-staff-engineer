import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from virtual_staff_engineer.api.app import create_app
from virtual_staff_engineer.api.auth import ApiKeyAuthenticator
from virtual_staff_engineer.jobs.lifecycle import JobCheckpoint, JobState
from virtual_staff_engineer.jobs.observability import (
    WorkflowEvent,
    WorkflowObservation,
)
from virtual_staff_engineer.jobs.repository import SubmissionResult
from virtual_staff_engineer.remediation.approval import (
    ApprovalCheck,
    ApprovalRequest,
    ApprovalRule,
    HumanDecisionResult,
)


class FakeRepository:
    def __init__(self):
        self.job = _job()
        self.submissions = []
        self.decisions = []

    def submit(self, analysis_input, **options):
        self.submissions.append((analysis_input, options))
        return SubmissionResult(self.job, True)

    def get(self, workflow_job_id):
        return self.job if workflow_job_id == self.job.workflow_job_id else None

    def observe(self, workflow_job_id):
        if workflow_job_id != self.job.workflow_job_id:
            return None
        return WorkflowObservation(
            job=self.job,
            events=self.list_events(workflow_job_id),
            stage_timings=(),
            queue_wait_ms=None,
            human_wait_ms=None,
            automated_processing_ms=5.0,
            end_to_end_ms=5.0,
        )

    def list_events(self, workflow_job_id, after_sequence=0):
        event = WorkflowEvent(
            1, None, "completed", 1, "analysis_completed", None, None,
            self.job.created_at,
        )
        return (event,) if after_sequence < 1 else ()

    def get_approval_request(self, workflow_job_id):
        if workflow_job_id != self.job.workflow_job_id:
            return None
        return ApprovalRequest(
            workflow_job_id=workflow_job_id,
            remediation_action_id="action-1",
            patch_proposal_id="proposal-1",
            source_path="app.py",
            source_revision=None,
            original_sha256="a" * 64,
            unified_diff="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-a\n+b",
            explanation="Apply the rule.",
            rules=(ApprovalRule("SEC-01", "Do not log tokens."),),
            validation_status="valid",
            resulting_sha256="b" * 64,
            checks=(ApprovalCheck("syntax", "passed", "Valid."),),
        )

    def record_human_decision(self, workflow_job_id, decision):
        self.decisions.append(decision)
        approved = SimpleNamespace(
            workflow_job_id=workflow_job_id,
            status=JobState.APPROVED,
        )
        return HumanDecisionResult(approved, True)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeRepository()
        app = create_app(
            repository=self.repository,
            authenticator=ApiKeyAuthenticator(
                viewer_key="viewer-secret",
                reviewer_key="reviewer-secret",
                viewer_subject="alice",
                reviewer_subject="bob",
            ),
        )
        self.client = TestClient(app)

    def test_health_is_public_but_jobs_require_authentication(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/jobs/job-1").status_code, 401)

    def test_submission_returns_immediately_with_durable_job(self):
        with patch.dict(
            os.environ, {"GEMINI_REASONING_MODEL": "test-model"}
        ):
            response = self.client.post(
                "/analysis-runs",
                headers={"X-API-Key": "viewer-secret"},
                json={
                    "input_type": "code_diff",
                    "content": "+ logger.info(token)",
                    "source_path": "app.py",
                    "idempotency_key": "repo:change:1",
                },
            )
        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["created"])
        submitted, options = self.repository.submissions[0]
        self.assertEqual(submitted.input_type, "code_diff")
        self.assertEqual(options["model_name"], "test-model")

    def test_status_exposes_metrics_without_reasoning(self):
        response = self.client.get(
            "/jobs/job-1", headers={"X-API-Key": "viewer-secret"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["end_to_end_ms"], 5.0)
        self.assertNotIn("reasoning", response.json())

    def test_only_reviewer_can_decide_and_actor_comes_from_auth(self):
        payload = {"decision": "approved", "comment": "Ship it."}
        denied = self.client.post(
            "/jobs/job-1/decision",
            headers={"X-API-Key": "viewer-secret"},
            json=payload,
        )
        accepted = self.client.post(
            "/jobs/job-1/decision",
            headers={"X-API-Key": "reviewer-secret"},
            json=payload,
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(accepted.status_code, 200)
        decision = self.repository.decisions[0]
        self.assertEqual(decision.actor, "bob")
        self.assertEqual(decision.authentication_method, "api_key")

    def test_terminal_sse_stream_contains_safe_status_event(self):
        response = self.client.get(
            "/jobs/job-1/events",
            headers={"X-API-Key": "viewer-secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("event: workflow_status", response.text)
        self.assertIn('"status": "completed"', response.text)
        self.assertNotIn("reasoning", response.text)


def _job():
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        workflow_job_id="job-1",
        analysis_run_id="analysis-1",
        remediation_action_id=None,
        status=JobState.COMPLETED,
        idempotency_key="key-1",
        priority=100,
        attempt_count=1,
        max_attempts=3,
        available_at=now,
        checkpoint=JobCheckpoint.ANALYSIS_COMPLETED,
        resume_state=JobState.ANALYZING,
        lease_owner=None,
        lease_token=None,
        lease_expires_at=None,
        heartbeat_at=None,
        failure_code=None,
        failure_disposition=None,
        error_message=None,
        started_at=now,
        completed_at=now,
        created_at=now,
        updated_at=now,
    )


if __name__ == "__main__":
    unittest.main()
