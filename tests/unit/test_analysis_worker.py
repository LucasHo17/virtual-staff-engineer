import unittest
import time
from types import SimpleNamespace

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.jobs.lifecycle import JobState
from virtual_staff_engineer.jobs.retry import ExponentialBackoffPolicy
from virtual_staff_engineer.jobs.worker import AnalysisWorker, classify_failure


class FakeRepository:
    def __init__(self, job=None):
        self.job = job
        self.claim_calls = []
        self.completed = []
        self.failures = []
        self.heartbeats = 0

    def claim_next(self, worker_id, **options):
        self.claim_calls.append((worker_id, options))
        return self.job

    def begin_analysis(self, workflow_job_id, lease_token):
        return AnalysisInput("code_diff", "safe_call()", "app.py")

    def heartbeat(self, *args, **kwargs):
        self.heartbeats += 1
        return self.job

    def complete_analysis(
        self, workflow_job_id, lease_token, result, **usage
    ):
        self.completed.append((workflow_job_id, lease_token, result, usage))
        return SimpleNamespace(status=JobState.COMPLETED)

    def schedule_failure(
        self, workflow_job_id, lease_token, failure, delay_seconds
    ):
        self.failures.append(
            (workflow_job_id, lease_token, failure, delay_seconds)
        )
        return SimpleNamespace(status=JobState.RETRY_SCHEDULED)


class FakeOrchestrator:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def run(self, analysis_input):
        if self.error is not None:
            raise self.error
        return self.result


class SlowOrchestrator(FakeOrchestrator):
    def run(self, analysis_input):
        time.sleep(0.04)
        return super().run(analysis_input)


class UsageReasoner:
    def __init__(self):
        self.input_tokens = 10
        self.output_tokens = 4

    def usage_snapshot(self):
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class UsageOrchestrator(FakeOrchestrator):
    def __init__(self, result):
        super().__init__(result=result)
        self.reasoner = UsageReasoner()

    def run(self, analysis_input):
        self.reasoner.input_tokens += 30
        self.reasoner.output_tokens += 8
        return super().run(analysis_input)


def _job(attempt_count=1):
    return SimpleNamespace(
        workflow_job_id="job-1",
        lease_token="lease-1",
        attempt_count=attempt_count,
    )


class AnalysisWorkerTests(unittest.TestCase):
    def test_returns_without_work_when_queue_is_empty(self):
        repository = FakeRepository()
        worker = AnalysisWorker(
            "worker-1", FakeOrchestrator(), repository, lease_seconds=3
        )

        execution = worker.run_once()

        self.assertFalse(execution.claimed)
        self.assertEqual(
            repository.claim_calls[0][1]["resume_states"],
            (JobState.ANALYZING,),
        )

    def test_completes_successful_analysis(self):
        result = object()
        repository = FakeRepository(_job())
        worker = AnalysisWorker(
            "worker-1",
            FakeOrchestrator(result=result),
            repository,
            lease_seconds=3,
        )

        execution = worker.run_once()

        self.assertTrue(execution.claimed)
        self.assertEqual(execution.job.status, JobState.COMPLETED)
        self.assertEqual(repository.completed[0][2], result)
        self.assertEqual(repository.failures, [])

    def test_persists_only_tokens_consumed_by_this_job(self):
        repository = FakeRepository(_job())
        worker = AnalysisWorker(
            "worker-1",
            UsageOrchestrator(result=object()),
            repository,
            lease_seconds=3,
        )

        worker.run_once()

        self.assertEqual(
            repository.completed[0][3],
            {"input_tokens": 30, "output_tokens": 8},
        )

    def test_schedules_timeout_with_attempt_based_backoff(self):
        repository = FakeRepository(_job(attempt_count=2))
        worker = AnalysisWorker(
            "worker-1",
            FakeOrchestrator(error=TimeoutError("provider timed out")),
            repository,
            lease_seconds=3,
            backoff_policy=ExponentialBackoffPolicy(
                base_seconds=5,
                maximum_seconds=60,
                jitter_ratio=0,
            ),
        )

        execution = worker.run_once()

        failure = repository.failures[0][2]
        self.assertEqual(failure.code.value, "provider_timeout")
        self.assertEqual(repository.failures[0][3], 10)
        self.assertEqual(execution.job.status, JobState.RETRY_SCHEDULED)

    def test_renews_lease_during_slow_analysis(self):
        repository = FakeRepository(_job())
        worker = AnalysisWorker(
            "worker-1",
            SlowOrchestrator(result=object()),
            repository,
            lease_seconds=3,
            heartbeat_interval_seconds=0.01,
        )

        worker.run_once()

        self.assertGreaterEqual(repository.heartbeats, 1)

    def test_unknown_error_is_a_permanent_contract_failure(self):
        failure = classify_failure(ValueError("malformed model JSON"))

        self.assertEqual(failure.code.value, "model_contract_invalid")
        self.assertEqual(failure.disposition.value, "permanent")


if __name__ == "__main__":
    unittest.main()
