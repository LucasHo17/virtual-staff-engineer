import argparse
import socket

from virtual_staff_engineer.github import GitHubClient
from virtual_staff_engineer.jobs import GitHubPullRequestWorker, WorkflowJobRepository


def main():
    parser = argparse.ArgumentParser(
        description="Run one safe, retryable GitHub PR worker polling cycle."
    )
    parser.add_argument(
        "--worker-id", default=f"github-pr-{socket.gethostname()}"
    )
    parser.add_argument("--lease-seconds", type=int, default=60)
    arguments = parser.parse_args()
    execution = GitHubPullRequestWorker(
        worker_id=arguments.worker_id,
        github_client=GitHubClient(),
        repository=WorkflowJobRepository(),
        lease_seconds=arguments.lease_seconds,
    ).run_once()
    if not execution.claimed:
        print("No authenticated, approved PR work is available.")
        return
    print(f"Workflow job: {execution.job.workflow_job_id}")
    print(f"Status: {execution.job.status.value}")
    if execution.job.error_message:
        print(f"Error: {execution.job.error_message}")


if __name__ == "__main__":
    main()
