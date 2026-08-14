import hashlib
from dataclasses import dataclass

from virtual_staff_engineer.github.app_client import (
    GitHubPullRequestChangedError,
    GitHubPullRequestTooLargeError,
)
from virtual_staff_engineer.github.client import GitHubApiError
from virtual_staff_engineer.jobs.lifecycle import (
    FailureCode,
    FailureDisposition,
    JobFailure,
)
from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy


@dataclass(frozen=True)
class GitHubIngestionExecution:
    claimed: bool
    delivery_id: str = None
    status: str = None
    workflow_job_ids: tuple = ()


class GitHubWebhookIngestionWorker:
    """Fetch one signed delivery snapshot and submit idempotent per-file jobs."""

    def __init__(
        self,
        worker_id,
        github_client,
        delivery_repository,
        workflow_repository,
        model_name,
        lease_seconds=300,
        backoff_policy=None,
        random_source=None,
    ):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a non-empty string.")
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must be a non-empty string.")
        self.worker_id = worker_id.strip()
        self.github_client = github_client
        self.delivery_repository = delivery_repository
        self.workflow_repository = workflow_repository
        self.model_name = model_name.strip()
        self.lease_seconds = lease_seconds
        self.backoff_policy = backoff_policy or ExponentialBackoffPolicy()
        self.random_source = random_source

    def run_once(self):
        claim = self.delivery_repository.claim_next(
            self.worker_id, lease_seconds=self.lease_seconds
        )
        if claim is None:
            return GitHubIngestionExecution(claimed=False)
        try:
            snapshot = self.github_client.fetch_pull_request(claim.delivery)
            commit_id = self.delivery_repository.persist_snapshot(claim, snapshot)
            job_ids = []
            for analysis_input in snapshot.analysis_inputs(commit_id):
                result = self.workflow_repository.submit(
                    analysis_input,
                    idempotency_key=_job_key(snapshot, analysis_input.source_path),
                    model_name=self.model_name,
                    workflow_version="phase5-github-v1",
                    prompt_version="phase2-v1",
                    priority=100,
                    max_attempts=5,
                )
                job_id = str(result.job.workflow_job_id)
                self.delivery_repository.link_job(
                    claim, job_id, analysis_input.source_path
                )
                job_ids.append(job_id)
            status = self.delivery_repository.complete(claim, snapshot)
            return GitHubIngestionExecution(
                claimed=True,
                delivery_id=claim.delivery.delivery_id,
                status=status,
                workflow_job_ids=tuple(job_ids),
            )
        except Exception as exc:
            failure = classify_ingestion_failure(exc)
            delay = 0
            if failure.disposition is FailureDisposition.RETRYABLE:
                delay = self.backoff_policy.delay_seconds(
                    claim.attempt_count,
                    random_source=self.random_source,
                )
            status = self.delivery_repository.schedule_failure(
                claim, failure, delay_seconds=delay
            )
            return GitHubIngestionExecution(
                claimed=True,
                delivery_id=claim.delivery.delivery_id,
                status=status,
            )


def classify_ingestion_failure(error):
    message = str(error).strip() or error.__class__.__name__
    if isinstance(error, GitHubPullRequestChangedError):
        return JobFailure(FailureCode.STALE_SOURCE, message)
    if isinstance(error, GitHubPullRequestTooLargeError):
        return JobFailure(FailureCode.UNSUPPORTED_REPOSITORY_STATE, message)
    if isinstance(error, (ConnectionError, TimeoutError)):
        return JobFailure(FailureCode.GITHUB_UNAVAILABLE, message)
    if isinstance(error, GitHubApiError):
        if error.status_code in {403, 429}:
            code = FailureCode.RATE_LIMITED
        elif error.status_code is None or error.status_code >= 500:
            code = FailureCode.GITHUB_UNAVAILABLE
        else:
            code = FailureCode.UNSUPPORTED_REPOSITORY_STATE
        return JobFailure(code, message)
    return JobFailure(FailureCode.UNSUPPORTED_REPOSITORY_STATE, message)


def _job_key(snapshot, source_path):
    path_digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()
    return (
        f"github:{snapshot.repository_owner}/{snapshot.repository_name}:"
        f"pr:{snapshot.pull_request_number}:head:{snapshot.head_sha.lower()}:"
        f"file:{path_digest}"
    )
