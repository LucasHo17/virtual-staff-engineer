import argparse
import os
import time
from pathlib import Path

import virtual_staff_engineer.config  # Load the project-root .env file.
from virtual_staff_engineer.evaluation.http_client import Phase4ApiClient
from virtual_staff_engineer.evaluation.load_test import (
    run_phase4_load_test,
    validate_concurrency_levels,
    write_load_test_report,
)


def parse_levels(value):
    try:
        levels = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "levels must be comma-separated integers"
        ) from exc
    try:
        return validate_concurrency_levels(levels)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run controlled concurrent Phase 4 API/worker load waves."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("VSE_API_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--levels", type=parse_levels, default=(1, 5, 10, 25))
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--poll-seconds", type=float, default=1)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--max-failure-rate", type=float, default=0.2)
    parser.add_argument(
        "--run-id", default=time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    )
    parser.add_argument(
        "--output-dir", default="evaluation_results/phase4_load/v1"
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Required acknowledgement that live model-backed jobs may run.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    total_jobs = sum(arguments.levels)
    output_dir = Path(arguments.output_dir)
    existing = [
        path for path in (output_dir / "results.json", output_dir / "report.md")
        if path.exists()
    ]
    if existing and not arguments.overwrite:
        raise SystemExit(
            "❌ Refusing to overwrite existing load-test files: "
            + ", ".join(str(path) for path in existing)
        )
    print(f"Load waves: {' → '.join(map(str, arguments.levels))}")
    print(f"Maximum live jobs: {total_jobs}")
    print("GitHub mutation: disabled by workload design")
    if not arguments.execute:
        print("Dry preflight only. Add --execute to submit live model-backed jobs.")
        return

    viewer_key = os.getenv("VSE_VIEWER_API_KEY")
    if not viewer_key:
        raise SystemExit("❌ Set VSE_VIEWER_API_KEY before running live load.")
    client = Phase4ApiClient(arguments.base_url, viewer_key)
    if client.health().get("status") != "ok":
        raise SystemExit("❌ API health check did not return status=ok.")
    result = run_phase4_load_test(
        client,
        arguments.run_id,
        concurrency_levels=arguments.levels,
        timeout_seconds=arguments.timeout_seconds,
        poll_seconds=arguments.poll_seconds,
        max_failure_rate=arguments.max_failure_rate,
        max_attempts=arguments.max_attempts,
        progress_callback=lambda level, complete, total, status: print(
            f"   wave {level}: {complete}/{total} settled ({status})",
            flush=True,
        ),
    )
    paths = write_load_test_report(
        result, output_dir, overwrite=arguments.overwrite
    )
    print(f"✅ Completed waves: {result['completed_levels']}")
    print(f"   JSON: {paths['json']}")
    print(f"   Markdown: {paths['markdown']}")
    if result["aborted"]:
        print("   ⚠️  Higher waves skipped after the failure-rate safety limit.")


if __name__ == "__main__":
    main()
