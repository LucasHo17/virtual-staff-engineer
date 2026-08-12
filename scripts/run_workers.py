import argparse
import json
import os
import socket
import time
from pathlib import Path

from virtual_staff_engineer.analysis.gemini import GeminiReasoner
from virtual_staff_engineer.analysis.orchestrator import BoundedAnalysisOrchestrator
from virtual_staff_engineer.analysis.retrieval_tool import HybridRetrievalTool
from virtual_staff_engineer.github import GitHubClient
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
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run the asynchronous workflow stage workers."
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--lease-seconds", type=int, default=60)
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
    reasoner = GeminiReasoner()
    retrieval = HybridRetrievalTool(
        category=os.getenv("VSE_PLAYBOOK_CATEGORY", "evaluation"),
        ai_client=reasoner.client,
    )
    source = FilesystemSourceProvider(Path(arguments.repository_root))
    prefix = "vse-" + socket.gethostname()
    common = {
        "repository": repository,
        "lease_seconds": arguments.lease_seconds,
    }
    workers = [
        (
            "analysis",
            AnalysisWorker(
                prefix + "-analysis",
                BoundedAnalysisOrchestrator(reasoner, retrieval),
                **common,
            ),
        ),
        (
            "patch_generation",
            PatchGenerationWorker(
                prefix + "-patch",
                GeminiPatchGenerator(),
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
    if os.getenv("GITHUB_TOKEN"):
        workers.append(
            (
                "github_pr",
                GitHubPullRequestWorker(
                    prefix + "-github", GitHubClient(), **common
                ),
            )
        )
    return WorkerRuntime(workers)


def main():
    arguments = parse_arguments()
    runtime = build_runtime(arguments)
    while True:
        executions = runtime.run_cycle()
        for item in executions:
            job = item.execution.job
            print(
                json.dumps(
                    {
                        "event": "worker_cycle_completed",
                        "stage": item.stage,
                        "workflow_job_id": job.workflow_job_id,
                        "status": job.status.value,
                        "failure_code": job.failure_code,
                    }
                ),
                flush=True,
            )
        if arguments.once:
            return
        if not executions:
            time.sleep(arguments.poll_seconds)


if __name__ == "__main__":
    main()
