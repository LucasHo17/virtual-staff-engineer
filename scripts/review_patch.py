import argparse

from virtual_staff_engineer.jobs import WorkflowJobRepository
from virtual_staff_engineer.remediation import HumanDecision


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Review and explicitly approve or reject a validated patch."
    )
    parser.add_argument("workflow_job_id", help="Workflow job UUID to review.")
    parser.add_argument(
        "--decision",
        choices=("approved", "rejected"),
        help="Persist an explicit decision; omit to inspect only.",
    )
    parser.add_argument(
        "--actor",
        help="Authenticated reviewer identity required with --decision.",
    )
    parser.add_argument("--comment", help="Optional reviewer rationale.")
    arguments = parser.parse_args()
    if arguments.decision and not arguments.actor:
        parser.error("--actor is required with --decision")
    if arguments.actor and not arguments.decision:
        parser.error("--actor requires --decision")
    if arguments.comment and not arguments.decision:
        parser.error("--comment requires --decision")
    return arguments


def display_request(request):
    print(f"Job: {request.workflow_job_id}")
    print(f"Source: {request.source_path}")
    print(f"Original SHA-256: {request.original_sha256}")
    print(f"Result SHA-256: {request.resulting_sha256}")
    print("\nExplanation:")
    print(request.explanation)
    print("\nRules:")
    for rule in request.rules:
        print(f"- {rule.rule_key}: {rule.rule_snapshot}")
    print("\nValidation checks:")
    for check in request.checks:
        print(f"- [{check.status}] {check.name}: {check.details}")
    print("\nUnified diff:")
    print(request.unified_diff)


def main():
    arguments = parse_arguments()
    repository = WorkflowJobRepository()
    request = repository.get_approval_request(arguments.workflow_job_id)
    if request is not None:
        display_request(request)
    elif arguments.decision is None:
        raise SystemExit("No validated patch is awaiting approval for this job.")
    if arguments.decision is not None:
        outcome = repository.record_human_decision(
            arguments.workflow_job_id,
            HumanDecision(
                decision=arguments.decision,
                actor=arguments.actor,
                comment=arguments.comment,
            ),
        )
        action = "Recorded" if outcome.created else "Already recorded"
        print(f"\n{action}: {arguments.decision}")
        print(f"Workflow status: {outcome.job.status.value}")


if __name__ == "__main__":
    main()
