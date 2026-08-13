import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


FAILURE_TEST_MODULES = (
    "tests.unit.test_job_retry",
    "tests.unit.test_patch_worker",
    "tests.unit.test_patch_validation_worker",
    "tests.unit.test_github_pr_worker",
    "tests.unit.test_github_client",
    "tests.integration.test_workflow_jobs",
)


def main():
    suite = unittest.defaultTestLoader.loadTestsFromNames(FAILURE_TEST_MODULES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("✅ Phase 4 deterministic failure suite passed.")


if __name__ == "__main__":
    main()
