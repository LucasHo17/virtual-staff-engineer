import argparse
import json
import os
import time
from pathlib import Path

import virtual_staff_engineer.config  # Load the project-root .env file.
from virtual_staff_engineer.evaluation.http_client import Phase4ApiClient
from virtual_staff_engineer.evaluation.workload import (
    load_phase4_workload,
    run_phase4_workload,
    verify_workload_source,
)

def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run the reproducible Phase 4 live workflow workload."
    )
    parser.add_argument(
        "--dataset", default="evaluation_data/phase4_workload_v1.json"
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("VSE_API_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--repository-root", default=os.getenv("VSE_REPOSITORY_ROOT")
    )
    parser.add_argument("--timeout-seconds", type=float, default=300)
    parser.add_argument("--poll-seconds", type=float, default=1)
    parser.add_argument(
        "--run-id",
        default=time.strftime("%Y%m%dT%H%M%S", time.gmtime()),
        help="Unique label used in idempotency keys.",
    )
    parser.add_argument("--output", help="Optional JSON result path.")
    parser.add_argument(
        "--overwrite", action="store_true", help="Replace --output if it exists."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate workload and source fixture without API calls.",
    )
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    workload = load_phase4_workload(arguments.dataset)
    if not arguments.repository_root:
        raise SystemExit("❌ Set VSE_REPOSITORY_ROOT or pass --repository-root.")
    root = verify_workload_source(workload, arguments.repository_root)
    output = Path(arguments.output) if arguments.output else None
    if output and output.exists() and not arguments.overwrite:
        raise SystemExit(
            f"❌ Output already exists: {output}. Pass --overwrite intentionally."
        )

    print(f"✅ Workload: {workload.workload_id} ({len(workload.cases)} cases)")
    print(f"   Source root: {root}")
    print(
        "   Deterministic fault scenarios: "
        + ", ".join(sorted(workload.deterministic_coverage))
    )
    if arguments.dry_run:
        print("   No API requests, model calls, decisions, or files were written.")
        return

    viewer_key = os.getenv("VSE_VIEWER_API_KEY")
    reviewer_key = os.getenv("VSE_REVIEWER_API_KEY")
    if not viewer_key:
        raise SystemExit("❌ Set VSE_VIEWER_API_KEY before running live cases.")
    client = Phase4ApiClient(
        arguments.base_url, viewer_key, reviewer_key=reviewer_key
    )
    if client.health().get("status") != "ok":
        raise SystemExit("❌ API health check did not return status=ok.")

    result = run_phase4_workload(
        workload,
        client,
        arguments.run_id,
        timeout_seconds=arguments.timeout_seconds,
        poll_seconds=arguments.poll_seconds,
        status_callback=lambda case_id, job_id, status: print(
            f"   {case_id} [{job_id[:8]}]: {status}", flush=True
        ),
        progress_callback=lambda case, completed, total: print(
            f"   [{completed}/{total}] {case['case_id']}: "
            f"{case['final_status']} ✅",
            flush=True,
        ),
    )
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"   JSON: {output}")
    print(f"✅ Passed {result['passed_count']}/{result['case_count']} live cases.")


if __name__ == "__main__":
    main()
