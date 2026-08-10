import threading
from dataclasses import dataclass

from virtual_staff_engineer.jobs.lifecycle import (
    FailureCode,
    FailureDisposition,
    JobFailure,
    JobState,
)
from virtual_staff_engineer.jobs.repository import LeaseLostError
from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy


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
            completed = self.repository.complete_analysis(
                job.workflow_job_id,
                job.lease_token,
                result,
            )
            return WorkerExecution(claimed=True, job=completed)
        except LeaseLostError:
            raise
        except Exception as exc:
            failure = self.failure_classifier(exc)
            delay = 0
            if failure.disposition is FailureDisposition.RETRYABLE:
                delay = self.backoff_policy.delay_seconds(
                    job.attempt_count,
                    random_source=self.random_source,
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
    status_code = getattr(error, "status_code", None)
    if status_code == 429 or "resourceexhausted" in class_name:
        code = FailureCode.RATE_LIMITED
    elif isinstance(error, TimeoutError) or "deadline" in class_name:
        code = FailureCode.PROVIDER_TIMEOUT
    elif isinstance(error, ConnectionError):
        code = FailureCode.NETWORK_ERROR
    else:
        code = FailureCode.MODEL_CONTRACT_INVALID
    return JobFailure(code=code, message=message)


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
