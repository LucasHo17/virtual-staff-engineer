import hashlib
import hmac
import json
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
            input_tokens=100,
            output_tokens=50,
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


class FakeWebhookRepository:
    def __init__(self):
        self.deliveries = {}
        self.job_context = None
        self.pull_requests = ()

    def record(self, delivery):
        created = delivery.delivery_id not in self.deliveries
        self.deliveries.setdefault(delivery.delivery_id, delivery)
        return SimpleNamespace(delivery=delivery, created=created)

    def get_job_context(self, workflow_job_id):
        return self.job_context

    def list_pull_requests(self, limit=20):
        return self.pull_requests[:limit]


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakeRepository()
        self.webhook_repository = FakeWebhookRepository()
        app = create_app(
            repository=self.repository,
            authenticator=ApiKeyAuthenticator(
                viewer_key="viewer-secret",
                reviewer_key="reviewer-secret",
                viewer_subject="alice",
                reviewer_subject="bob",
            ),
            webhook_repository=self.webhook_repository,
            webhook_secret="webhook-secret",
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
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get(
                "/jobs/job-1", headers={"X-API-Key": "viewer-secret"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["end_to_end_ms"], 5.0)
        self.assertEqual(response.json()["retry_count"], 0)
        self.assertIsNone(response.json()["estimated_analysis_cost_usd"])
        self.assertNotIn("reasoning", response.json())
        self.assertEqual(response.json()["origin"], "manual")

    def test_github_job_status_and_pull_request_feed_expose_provenance(self):
        context = SimpleNamespace(
            delivery_id="delivery-1",
            repository_owner="example",
            repository_name="demo",
            pull_request_number=7,
            pull_request_title="Secure token logging",
            pull_request_url="https://github.com/example/demo/pull/7",
            head_sha="a" * 40,
            source_path="app.py",
            created_pull_request_url=None,
        )
        job = SimpleNamespace(
            workflow_job_id="job-1",
            source_path="app.py",
            status="completed",
            checkpoint="analysis_completed",
            failure_code=None,
            created_pull_request_url=None,
        )
        pull_request = SimpleNamespace(
            delivery_id="delivery-1",
            repository_owner="example",
            repository_name="demo",
            pull_request_number=7,
            pull_request_title="Secure token logging",
            pull_request_url="https://github.com/example/demo/pull/7",
            head_sha="a" * 40,
            base_sha="b" * 40,
            status="completed",
            changed_file_count=1,
            analyzable_file_count=1,
            skipped_file_count=0,
            received_at=self.repository.job.created_at,
            completed_at=self.repository.job.completed_at,
            jobs=(job,),
        )
        self.webhook_repository.job_context = context
        self.webhook_repository.pull_requests = (pull_request,)

        status_response = self.client.get(
            "/jobs/job-1", headers={"X-API-Key": "viewer-secret"}
        )
        feed_response = self.client.get(
            "/github/pull-requests",
            headers={"X-API-Key": "viewer-secret"},
        )

        self.assertEqual(status_response.json()["origin"], "github")
        self.assertEqual(
            status_response.json()["github"]["repository_name"], "demo"
        )
        self.assertEqual(feed_response.status_code, 200)
        self.assertEqual(feed_response.json()[0]["jobs"][0]["source_path"], "app.py")

    def test_cost_is_estimated_only_when_both_rates_are_configured(self):
        with patch.dict(
            os.environ,
            {
                "VSE_INPUT_COST_PER_MILLION": "1",
                "VSE_OUTPUT_COST_PER_MILLION": "2",
            },
            clear=True,
        ):
            response = self.client.get(
                "/jobs/job-1", headers={"X-API-Key": "viewer-secret"}
            )
        self.assertEqual(
            response.json()["estimated_analysis_cost_usd"], 0.0002
        )

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

    def test_signed_pull_request_webhook_is_deduplicated_without_api_key(self):
        raw_body = json.dumps(_pull_request_payload()).encode("utf-8")
        headers = _webhook_headers(raw_body, delivery_id="delivery-1")

        accepted = self.client.post(
            "/webhooks/github", content=raw_body, headers=headers
        )
        duplicate = self.client.post(
            "/webhooks/github", content=raw_body, headers=headers
        )

        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(accepted.json()["status"], "accepted")
        self.assertEqual(duplicate.json()["status"], "duplicate")
        self.assertEqual(len(self.webhook_repository.deliveries), 1)
        delivery = self.webhook_repository.deliveries["delivery-1"]
        self.assertEqual(delivery.repository_owner, "example")
        self.assertEqual(delivery.repository_name, "demo")
        self.assertEqual(delivery.pull_request_number, 7)

    def test_webhook_rejects_missing_or_invalid_signature(self):
        raw_body = json.dumps(_pull_request_payload()).encode("utf-8")
        missing = _webhook_headers(raw_body)
        missing.pop("X-Hub-Signature-256")
        invalid = _webhook_headers(raw_body)
        invalid["X-Hub-Signature-256"] = "sha256=" + "0" * 64

        self.assertEqual(
            self.client.post(
                "/webhooks/github", content=raw_body, headers=missing
            ).status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                "/webhooks/github", content=raw_body, headers=invalid
            ).status_code,
            401,
        )
        self.assertFalse(self.webhook_repository.deliveries)

    def test_webhook_pongs_and_ignores_unneeded_events_and_actions(self):
        ping_body = b'{"zen":"Keep it logically awesome."}'
        ping = self.client.post(
            "/webhooks/github",
            content=ping_body,
            headers=_webhook_headers(ping_body, event="ping"),
        )
        closed_payload = _pull_request_payload(action="closed")
        closed_body = json.dumps(closed_payload).encode("utf-8")
        ignored = self.client.post(
            "/webhooks/github",
            content=closed_body,
            headers=_webhook_headers(
                closed_body, delivery_id="delivery-closed"
            ),
        )

        self.assertEqual(ping.json()["status"], "pong")
        self.assertEqual(ignored.json()["status"], "ignored")
        self.assertFalse(self.webhook_repository.deliveries)

    def test_supported_webhook_requires_pr_identity_fields(self):
        payload = _pull_request_payload()
        del payload["installation"]
        raw_body = json.dumps(payload).encode("utf-8")

        response = self.client.post(
            "/webhooks/github",
            content=raw_body,
            headers=_webhook_headers(raw_body),
        )

        self.assertEqual(response.status_code, 422)
        self.assertFalse(self.webhook_repository.deliveries)


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


def _pull_request_payload(action="opened"):
    return {
        "action": action,
        "installation": {"id": 1234},
        "repository": {
            "name": "demo",
            "owner": {"login": "example"},
        },
        "pull_request": {
            "number": 7,
            "head": {"sha": "a" * 40},
        },
    }


def _webhook_headers(raw_body, delivery_id="delivery-1", event="pull_request"):
    signature = hmac.new(
        b"webhook-secret", raw_body, hashlib.sha256
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-GitHub-Delivery": delivery_id,
        "X-GitHub-Event": event,
        "X-Hub-Signature-256": "sha256=" + signature,
    }


if __name__ == "__main__":
    unittest.main()
