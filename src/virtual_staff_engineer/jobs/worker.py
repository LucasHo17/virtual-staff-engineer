import threading
import re
from dataclasses import dataclass

from virtual_staff_engineer.jobs.lifecycle import (
    FailureCode,
    FailureDisposition,
    JobFailure,
    JobState,
)
from virtual_staff_engineer.jobs.repository import LeaseLostError
from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy
from virtual_staff_engineer.github.client import (
    GitHubApiError,
    GitHubStaleSourceError,
)
from virtual_staff_engineer.remediation.contracts import (
    PatchGenerationContext,
    validate_generated_patch,
)


@dataclass(frozen=True)
class WorkerExecution:
    """The durable outcome of one worker polling cycle."""

    claimed: bool
    job: object = None


class AnalysisWorker:
    """Claim and execute only the analysis stage of the durable workflow."""

    def __init__(
        self,
        worker_id,
        orchestrator,
        repository,
        lease_seconds=60,
        heartbeat_interval_seconds=None,
        backoff_policy=None,
        failure_classifier=None,
        random_source=None,
    ):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a non-empty string.")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds < 3
        ):
            raise ValueError("lease_seconds must be an integer of at least 3.")
        interval = (
            max(1, lease_seconds // 3)
            if heartbeat_interval_seconds is None
            else heartbeat_interval_seconds
        )
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or interval <= 0
        ):
            raise ValueError(
                "heartbeat_interval_seconds must be a positive number."
            )
        if interval >= lease_seconds:
            raise ValueError(
                "heartbeat_interval_seconds must be shorter than the lease."
            )
        self.worker_id = worker_id.strip()
        self.orchestrator = orchestrator
        self.repository = repository
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = interval
        self.backoff_policy = backoff_policy or ExponentialBackoffPolicy()
        self.failure_classifier = failure_classifier or classify_failure
        self.random_source = random_source

    def run_once(self):
        job = self.repository.claim_next(
            self.worker_id,
            lease_seconds=self.lease_seconds,
            resume_states=(JobState.ANALYZING,),
        )
        if job is None:
            return WorkerExecution(claimed=False)

        try:
            analysis_input = self.repository.begin_analysis(
                job.workflow_job_id, job.lease_token
            )
            usage_before = _usage_snapshot(self.orchestrator)
            heartbeat = _LeaseHeartbeat(
                repository=self.repository,
                workflow_job_id=job.workflow_job_id,
                lease_token=job.lease_token,
                lease_seconds=self.lease_seconds,
                interval_seconds=self.heartbeat_interval_seconds,
            )
            with heartbeat:
                result = self.orchestrator.run(analysis_input)
            if heartbeat.error is not None:
                raise heartbeat.error
            usage_after = _usage_snapshot(self.orchestrator)
            completed = self.repository.complete_analysis(
                job.workflow_job_id,
                job.lease_token,
                result,
                input_tokens=max(
                    0, usage_after[0] - usage_before[0]
                ),
                output_tokens=max(
                    0, usage_after[1] - usage_before[1]
                ),
            )
            return WorkerExecution(claimed=True, job=completed)
        except LeaseLostError:
            raise
        except Exception as exc:
            failure = self.failure_classifier(exc)
            delay = 0
            if failure.disposition is FailureDisposition.RETRYABLE:
                delay = _retry_delay(
                    self.backoff_policy, failure, job.attempt_count,
                    self.random_source,
                )
            scheduled = self.repository.schedule_failure(
                job.workflow_job_id,
                job.lease_token,
                failure,
                delay_seconds=delay,
            )
            return WorkerExecution(claimed=True, job=scheduled)


class PatchGenerationWorker:
    """Generate and persist proposals without applying source mutations."""

    def __init__(
        self,
        worker_id,
        generator,
        source_provider,
        repository,
        lease_seconds=60,
        heartbeat_interval_seconds=None,
        backoff_policy=None,
        failure_classifier=None,
        random_source=None,
    ):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a non-empty string.")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds < 3
        ):
            raise ValueError("lease_seconds must be an integer of at least 3.")
        interval = (
            max(1, lease_seconds // 3)
            if heartbeat_interval_seconds is None
            else heartbeat_interval_seconds
        )
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or interval <= 0
            or interval >= lease_seconds
        ):
            raise ValueError(
                "heartbeat interval must be positive and shorter than lease."
            )
        for attribute in ("model", "prompt_version"):
            value = getattr(generator, attribute, None)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"generator.{attribute} must be a non-empty string."
                )
        self.worker_id = worker_id.strip()
        self.generator = generator
        self.source_provider = source_provider
        self.repository = repository
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = interval
        self.backoff_policy = backoff_policy or ExponentialBackoffPolicy()
        self.failure_classifier = (
            failure_classifier or classify_patch_failure
        )
        self.random_source = random_source

    def run_once(self):
        job = self.repository.claim_next(
            self.worker_id,
            lease_seconds=self.lease_seconds,
            resume_states=(JobState.GENERATING_PATCH,),
        )
        if job is None:
            return WorkerExecution(claimed=False)
        try:
            seed = self.repository.begin_patch_generation(
                job.workflow_job_id, job.lease_token
            )
            source = self.source_provider.load(
                seed.source_path, revision=seed.source_revision
            )
            context = PatchGenerationContext(
                source=source, violations=seed.violations
            )
            heartbeat = _LeaseHeartbeat(
                repository=self.repository,
                workflow_job_id=job.workflow_job_id,
                lease_token=job.lease_token,
                lease_seconds=self.lease_seconds,
                interval_seconds=self.heartbeat_interval_seconds,
            )
            with heartbeat:
                patch = self.generator.generate(context)
            if heartbeat.error is not None:
                raise heartbeat.error
            validate_generated_patch(context, patch)
            completed = self.repository.complete_patch_generation(
                job.workflow_job_id,
                job.lease_token,
                context,
                patch,
                model_name=self.generator.model,
                prompt_version=self.generator.prompt_version,
            )
            return WorkerExecution(claimed=True, job=completed)
        except LeaseLostError:
            raise
        except Exception as exc:
            failure = self.failure_classifier(exc)
            delay = 0
            if failure.disposition is FailureDisposition.RETRYABLE:
                delay = _retry_delay(
                    self.backoff_policy, failure, job.attempt_count,
                    self.random_source,
                )
            scheduled = self.repository.schedule_failure(
                job.workflow_job_id,
                job.lease_token,
                failure,
                delay_seconds=delay,
            )
            return WorkerExecution(claimed=True, job=scheduled)


class PatchValidationWorker:
    """Validate persisted proposals without modifying the source tree."""

    def __init__(
        self,
        worker_id,
        validator,
        source_provider,
        repository,
        lease_seconds=60,
        heartbeat_interval_seconds=None,
        backoff_policy=None,
        failure_classifier=None,
        random_source=None,
    ):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a non-empty string.")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds < 3
        ):
            raise ValueError("lease_seconds must be an integer of at least 3.")
        interval = (
            max(1, lease_seconds // 3)
            if heartbeat_interval_seconds is None
            else heartbeat_interval_seconds
        )
        if (
            isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or interval <= 0
            or interval >= lease_seconds
        ):
            raise ValueError(
                "heartbeat interval must be positive and shorter than lease."
            )
        version = getattr(validator, "version", None)
        if not isinstance(version, str) or not version.strip():
            raise ValueError("validator.version must be a non-empty string.")
        self.worker_id = worker_id.strip()
        self.validator = validator
        self.source_provider = source_provider
        self.repository = repository
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = interval
        self.backoff_policy = backoff_policy or ExponentialBackoffPolicy()
        self.failure_classifier = (
            failure_classifier or classify_patch_failure
        )
        self.random_source = random_source

    def run_once(self):
        job = self.repository.claim_next(
            self.worker_id,
            lease_seconds=self.lease_seconds,
            resume_states=(JobState.VALIDATING_PATCH,),
        )
        if job is None:
            return WorkerExecution(claimed=False)
        try:
            proposal = self.repository.begin_patch_validation(
                job.workflow_job_id, job.lease_token
            )
            current_source = self.source_provider.load(
                proposal.source_path,
                revision=proposal.source_revision,
            )
            heartbeat = _LeaseHeartbeat(
                repository=self.repository,
                workflow_job_id=job.workflow_job_id,
                lease_token=job.lease_token,
                lease_seconds=self.lease_seconds,
                interval_seconds=self.heartbeat_interval_seconds,
            )
            with heartbeat:
                result = self.validator.validate(proposal, current_source)
            if heartbeat.error is not None:
                raise heartbeat.error
            completed = self.repository.complete_patch_validation(
                job.workflow_job_id,
                job.lease_token,
                proposal,
                result,
                validator_version=self.validator.version,
            )
            return WorkerExecution(claimed=True, job=completed)
        except LeaseLostError:
            raise
        except Exception as exc:
            failure = self.failure_classifier(exc)
            delay = 0
            if failure.disposition is FailureDisposition.RETRYABLE:
                delay = _retry_delay(
                    self.backoff_policy, failure, job.attempt_count,
                    self.random_source,
                )
            scheduled = self.repository.schedule_failure(
                job.workflow_job_id,
                job.lease_token,
                failure,
                delay_seconds=delay,
            )
            return WorkerExecution(claimed=True, job=scheduled)


class GitHubPullRequestWorker:
    """Create only the exact approved patch on an isolated GitHub branch."""

    def __init__(
        self,
        worker_id,
        github_client,
        repository,
        lease_seconds=60,
        heartbeat_interval_seconds=None,
        backoff_policy=None,
        random_source=None,
    ):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a non-empty string.")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds < 3
        ):
            raise ValueError("lease_seconds must be an integer of at least 3.")
        interval = (
            max(1, lease_seconds // 3)
            if heartbeat_interval_seconds is None
            else heartbeat_interval_seconds
        )
        if interval <= 0 or interval >= lease_seconds:
            raise ValueError(
                "heartbeat interval must be positive and shorter than lease."
            )
        self.worker_id = worker_id.strip()
        self.github_client = github_client
        self.repository = repository
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = interval
        self.backoff_policy = backoff_policy or ExponentialBackoffPolicy()
        self.random_source = random_source

    def run_once(self):
        job = self.repository.claim_pr_next(
            self.worker_id, lease_seconds=self.lease_seconds
        )
        if job is None:
            return WorkerExecution(claimed=False)
        try:
            context = self.repository.begin_pr_creation(
                job.workflow_job_id, job.lease_token
            )
            heartbeat = _LeaseHeartbeat(
                repository=self.repository,
                workflow_job_id=job.workflow_job_id,
                lease_token=job.lease_token,
                lease_seconds=self.lease_seconds,
                interval_seconds=self.heartbeat_interval_seconds,
            )
            with heartbeat:
                result = self.github_client.ensure_pull_request(context)
            if heartbeat.error is not None:
                raise heartbeat.error
            completed = self.repository.complete_pr_creation(
                job.workflow_job_id, job.lease_token, context, result
            )
            return WorkerExecution(claimed=True, job=completed)
        except LeaseLostError:
            raise
        except Exception as exc:
            failure = classify_github_failure(exc)
            delay = 0
            if failure.disposition is FailureDisposition.RETRYABLE:
                delay = _retry_delay(
                    self.backoff_policy, failure, job.attempt_count,
                    self.random_source,
                )
            scheduled = self.repository.schedule_failure(
                job.workflow_job_id,
                job.lease_token,
                failure,
                delay_seconds=delay,
            )
            return WorkerExecution(claimed=True, job=scheduled)


def classify_failure(error):
    """Map operational exceptions to the explicit workflow taxonomy."""
    message = str(error).strip() or error.__class__.__name__
    class_name = error.__class__.__name__.lower()
    status_code = _provider_status_code(error, message)
    normalized_message = message.lower().replace("_", "")
    if (
        status_code == 429
        or "resourceexhausted" in class_name
        or "resourceexhausted" in normalized_message
        or "quota exceeded" in normalized_message
    ):
        code = FailureCode.RATE_LIMITED
    elif isinstance(error, TimeoutError) or "deadline" in class_name:
        code = FailureCode.PROVIDER_TIMEOUT
    elif isinstance(error, ConnectionError):
        code = FailureCode.NETWORK_ERROR
    else:
        code = FailureCode.MODEL_CONTRACT_INVALID
    return JobFailure(
        code=code,
        message=message,
        retry_after_seconds=(
            _provider_retry_after_seconds(error, message)
            if code is FailureCode.RATE_LIMITED
            else None
        ),
    )


def classify_patch_failure(error):
    base = classify_failure(error)
    if base.disposition is FailureDisposition.RETRYABLE:
        return base
    message = str(error).strip() or error.__class__.__name__
    code = (
        FailureCode.STALE_SOURCE
        if isinstance(error, FileNotFoundError)
        else FailureCode.PATCH_INVALID
    )
    return JobFailure(code=code, message=message)


def classify_github_failure(error):
    message = str(error).strip() or error.__class__.__name__
    if isinstance(error, GitHubStaleSourceError):
        return JobFailure(code=FailureCode.STALE_SOURCE, message=message)
    if isinstance(error, (ConnectionError, TimeoutError)):
        return JobFailure(code=FailureCode.GITHUB_UNAVAILABLE, message=message)
    if isinstance(error, GitHubApiError):
        code = (
            FailureCode.RATE_LIMITED
            if error.status_code in {403, 429}
            else FailureCode.GITHUB_UNAVAILABLE
            if error.status_code is None or error.status_code >= 500
            else FailureCode.UNSUPPORTED_REPOSITORY_STATE
        )
        return JobFailure(code=code, message=message)
    return JobFailure(
        code=FailureCode.UNSUPPORTED_REPOSITORY_STATE, message=message
    )


def _usage_snapshot(orchestrator):
    reasoner = getattr(orchestrator, "reasoner", None)
    snapshot = getattr(reasoner, "usage_snapshot", None)
    if not callable(snapshot):
        return (0, 0)
    usage = snapshot()
    return (
        int(usage.get("input_tokens", 0) or 0),
        int(usage.get("output_tokens", 0) or 0),
    )


def _retry_delay(policy, failure, attempt_count, random_source):
    return policy.delay_seconds(
        attempt_count,
        random_source=random_source,
        minimum_seconds=failure.retry_after_seconds or 0,
    )


def _provider_status_code(error, message):
    for attribute in ("status_code", "code"):
        value = getattr(error, attribute, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    match = re.search(r"(?:^|\D)(429)(?:\D|$)", message)
    return int(match.group(1)) if match else None


def _provider_retry_after_seconds(error, message):
    for attribute in ("retry_after_seconds", "retry_after"):
        value = getattr(error, attribute, None)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return min(86400.0, max(0.0, float(value)))
    patterns = (
        r"retry\s+in\s+([0-9]+(?:\.[0-9]+)?)s",
        r"retryDelay['\"\s:]+([0-9]+(?:\.[0-9]+)?)s",
    )
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return min(86400.0, float(match.group(1)))
    return None


class _LeaseHeartbeat:
    def __init__(
        self,
        repository,
        workflow_job_id,
        lease_token,
        lease_seconds,
        interval_seconds,
    ):
        self.repository = repository
        self.workflow_job_id = workflow_job_id
        self.lease_token = lease_token
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self.error = None
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"lease-heartbeat-{workflow_job_id}",
            daemon=True,
        )

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._stop.set()
        self._thread.join()

    def _run(self):
        while not self._stop.wait(self.interval_seconds):
            try:
                self.repository.heartbeat(
                    self.workflow_job_id,
                    self.lease_token,
                    lease_seconds=self.lease_seconds,
                )
            except Exception as exc:
                self.error = exc
                self._stop.set()
                return
