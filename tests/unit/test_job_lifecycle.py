import unittest

from virtual_staff_engineer.jobs.lifecycle import (
    FailureCode,
    FailureDisposition,
    JobCheckpoint,
    JobFailure,
    JobState,
    JobTransition,
    validate_checkpoint_advance,
    validate_transition,
)


class JobLifecycleTests(unittest.TestCase):
    def test_happy_path_and_clean_completion_are_explicit(self):
        transitions = (
            (JobState.QUEUED, JobState.ANALYZING),
            (JobState.ANALYZING, JobState.GENERATING_PATCH),
            (JobState.GENERATING_PATCH, JobState.VALIDATING_PATCH),
            (JobState.VALIDATING_PATCH, JobState.AWAITING_APPROVAL),
            (JobState.AWAITING_APPROVAL, JobState.APPROVED),
            (JobState.APPROVED, JobState.CREATING_PR),
            (JobState.CREATING_PR, JobState.COMPLETED),
            (JobState.ANALYZING, JobState.COMPLETED),
            (JobState.QUEUED, JobState.VALIDATING_PATCH),
        )

        for current, target in transitions:
            self.assertEqual(
                validate_transition(current, target),
                (current, target),
            )

    def test_illegal_skip_and_terminal_transition_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "queued -> approved"):
            validate_transition(JobState.QUEUED, JobState.APPROVED)
        with self.assertRaisesRegex(ValueError, "completed -> queued"):
            validate_transition(JobState.COMPLETED, JobState.QUEUED)

    def test_retry_requires_a_retryable_failure(self):
        retryable = JobFailure(
            FailureCode.RATE_LIMITED,
            "Provider asked the worker to retry later.",
        )
        transition = JobTransition(
            JobState.ANALYZING,
            JobState.RETRY_SCHEDULED,
            retryable,
        )

        self.assertEqual(
            transition.failure.disposition,
            FailureDisposition.RETRYABLE,
        )
        with self.assertRaisesRegex(ValueError, "retryable JobFailure"):
            JobTransition(
                JobState.ANALYZING,
                JobState.RETRY_SCHEDULED,
                JobFailure(FailureCode.INVALID_INPUT, "Bad input."),
            )

    def test_failure_taxonomy_cannot_be_reclassified(self):
        with self.assertRaisesRegex(ValueError, "must be classified"):
            JobFailure(
                FailureCode.PATCH_INVALID,
                "Patch failed deterministic validation.",
                FailureDisposition.RETRYABLE,
            )

    def test_failed_requires_failure_details(self):
        with self.assertRaisesRegex(ValueError, "requires a JobFailure"):
            validate_transition(JobState.ANALYZING, JobState.FAILED)

    def test_checkpoints_are_monotonic_and_idempotent(self):
        self.assertEqual(
            validate_checkpoint_advance(
                JobCheckpoint.ANALYSIS_COMPLETED,
                JobCheckpoint.PATCH_GENERATED,
            ),
            JobCheckpoint.PATCH_GENERATED,
        )
        self.assertEqual(
            validate_checkpoint_advance(
                JobCheckpoint.PATCH_GENERATED,
                JobCheckpoint.PATCH_GENERATED,
            ),
            JobCheckpoint.PATCH_GENERATED,
        )
        with self.assertRaisesRegex(ValueError, "cannot regress"):
            validate_checkpoint_advance(
                JobCheckpoint.PATCH_VALIDATED,
                JobCheckpoint.ANALYSIS_COMPLETED,
            )


if __name__ == "__main__":
    unittest.main()
