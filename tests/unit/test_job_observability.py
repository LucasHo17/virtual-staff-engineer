import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from virtual_staff_engineer.jobs.observability import (
    WorkflowEvent,
    build_observation,
)


class WorkflowObservabilityTests(unittest.TestCase):
    def test_derives_queue_stage_human_and_automated_timings(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        job = SimpleNamespace(
            created_at=start,
            completed_at=start + timedelta(seconds=20),
        )
        events = (
            _event(1, "queued", start),
            _event(2, "analyzing", start + timedelta(seconds=2)),
            _event(3, "awaiting_approval", start + timedelta(seconds=8)),
            _event(4, "approved", start + timedelta(seconds=13)),
            _event(5, "creating_pr", start + timedelta(seconds=15)),
            _event(6, "completed", start + timedelta(seconds=20)),
        )

        observation = build_observation(job, events)

        self.assertEqual(observation.queue_wait_ms, 2000.0)
        self.assertEqual(observation.human_wait_ms, 5000.0)
        self.assertEqual(observation.end_to_end_ms, 20000.0)
        self.assertEqual(observation.automated_processing_ms, 15000.0)
        self.assertEqual(
            [(item.stage, item.duration_ms) for item in observation.stage_timings],
            [("analyzing", 6000.0), ("creating_pr", 5000.0)],
        )

    def test_in_progress_observation_uses_explicit_observed_time(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        job = SimpleNamespace(created_at=start, completed_at=None)
        observation = build_observation(
            job,
            (_event(1, "queued", start),),
            observed_at=start + timedelta(seconds=3),
        )
        self.assertIsNone(observation.queue_wait_ms)
        self.assertEqual(observation.end_to_end_ms, 3000.0)


def _event(sequence, to_status, created_at):
    return WorkflowEvent(
        sequence=sequence,
        from_status=None,
        to_status=to_status,
        attempt_count=0,
        checkpoint="submitted",
        failure_code=None,
        error_message=None,
        created_at=created_at,
    )


if __name__ == "__main__":
    unittest.main()
