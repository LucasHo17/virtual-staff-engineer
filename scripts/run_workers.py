import argparse
import json
import os
import socket
import time
from pathlib import Path

from virtual_staff_engineer.analysis.gemini import GeminiReasoner
from virtual_staff_engineer.analysis.orchestrator import BoundedAnalysisOrchestrator
from virtual_staff_engineer.analysis.retrieval_tool import HybridRetrievalTool
from virtual_staff_engineer.github import (
    GitHubAppClient,
    GitHubClient,
    GitHubWebhookDeliveryRepository,
    GitHubWebhookIngestionWorker,
)
from virtual_staff_engineer.jobs import (
    AnalysisWorker,
    GitHubPullRequestWorker,
    PatchGenerationWorker,
    PatchValidationWorker,
    WorkerRuntime,
    WorkflowJobRepository,
)
from virtual_staff_engineer.remediation import (
    DeterministicPatchValidator,
    FilesystemSourceProvider,
    GeminiPatchGenerator,
    GitHubSnapshotSourceProvider,
    RoutedSourceProvider,
)
from virtual_staff_engineer.providers import ModelRequestRateLimiter


def positive_int(value):
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def positive_float(value):
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run the asynchronous workflow stage workers."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument(
        "--analysis-concurrency",
        type=positive_int,
        default=positive_int(
            os.getenv("VSE_ANALYSIS_WORKER_CONCURRENCY", "1")
        ),
        help="Number of independently leased analysis workers.",
    )
    parser.add_argument(
        "--model-requests-per-minute",
        type=positive_float,
        default=(
            positive_float(os.environ["VSE_MODEL_REQUESTS_PER_MINUTE"])
            if os.getenv("VSE_MODEL_REQUESTS_PER_MINUTE")
            else None
        ),
        help=(
            "Shared in-process limit for Gemini generation requests; omitted "
            "means no proactive limit."
        ),
    )
    parser.add_argument(
        "--repository-root",
        default=os.getenv("VSE_REPOSITORY_ROOT", "."),
        help="Read-only source root used for patch generation and validation.",
    )
    arguments = parser.parse_args()
    if arguments.poll_seconds <= 0 or arguments.poll_seconds > 60:
        parser.error("--poll-seconds must be greater than 0 and at most 60")
    return arguments


def build_runtime(arguments):
    repository = WorkflowJobRepository()
    request_limiter = (
        ModelRequestRateLimiter(arguments.model_requests_per_minute)
        if arguments.model_requests_per_minute is not None
        else None
    )
    source = RoutedSourceProvider(
        FilesystemSourceProvider(Path(arguments.repository_root)),
        GitHubSnapshotSourceProvider(),
    )
    prefix = "vse-" + socket.gethostname()
    common = {
        "repository": repository,
        "lease_seconds": arguments.lease_seconds,
    }
    workers = []
    app_id = os.getenv("GITHUB_APP_ID")
    private_key_path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")
    if bool(app_id) != bool(private_key_path):
        raise RuntimeError(
            "Configure both GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_PATH."
        )
    if app_id and private_key_path:
        workers.append(
            (
                "github_ingestion",
                GitHubWebhookIngestionWorker(
                    prefix + "-github-ingestion",
                    GitHubAppClient(),
                    GitHubWebhookDeliveryRepository(),
                    repository,
                    model_name=os.getenv("GEMINI_REASONING_MODEL", ""),
                    lease_seconds=max(300, arguments.lease_seconds),
                ),
            )
        )
    for index in range(arguments.analysis_concurrency):
        reasoner = GeminiReasoner(request_limiter=request_limiter)
        retrieval = HybridRetrievalTool(
            category=os.getenv("VSE_PLAYBOOK_CATEGORY", "evaluation"),
            ai_client=reasoner.client,
        )
        workers.append(
            (
                "analysis-" + str(index + 1),
                AnalysisWorker(
                    prefix + "-analysis-" + str(index + 1),
                    BoundedAnalysisOrchestrator(reasoner, retrieval),
                    **common,
                ),
            )
        )
    workers.extend(
        [
            (
                "patch_generation",
                PatchGenerationWorker(
                    prefix + "-patch",
                    GeminiPatchGenerator(request_limiter=request_limiter),
                    source,
                    **common,
                ),
            ),
            (
                "patch_validation",
                PatchValidationWorker(
                    prefix + "-validation",
                    DeterministicPatchValidator(),
                    source,
                    **common,
                ),
            ),
        ]
    )
    if os.getenv("GITHUB_TOKEN"):
        workers.append(
            (
                "github_pr",
                GitHubPullRequestWorker(
                    prefix + "-github", GitHubClient(), **common
                ),
            )
        )
    return WorkerRuntime(
        workers,
        max_parallelism=len(workers),
    )


def main():
    arguments = parse_arguments()
    runtime = build_runtime(arguments)
    print(
        json.dumps(
            {
                "event": "worker_runtime_started",
                "analysis_concurrency": arguments.analysis_concurrency,
                "model_requests_per_minute": (
                    arguments.model_requests_per_minute
                ),
            }
        ),
        flush=True,
    )
    while True:
        executions = runtime.run_cycle()
        for item in executions:
            if item.stage == "github_ingestion":
                payload = {
                    "event": "worker_cycle_completed",
                    "stage": item.stage,
                    "delivery_id": item.execution.delivery_id,
                    "status": item.execution.status,
                    "workflow_job_ids": item.execution.workflow_job_ids,
                }
            else:
                job = item.execution.job
                payload = {
                    "event": "worker_cycle_completed",
                    "stage": item.stage,
                    "workflow_job_id": job.workflow_job_id,
                    "status": job.status.value,
                    "failure_code": job.failure_code,
                }
            print(json.dumps(payload), flush=True)
        if arguments.once:
            return
        if not executions:
            time.sleep(arguments.poll_seconds)


if __name__ == "__main__":
    main()
