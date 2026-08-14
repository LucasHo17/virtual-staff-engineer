import argparse
import hashlib
import json

import virtual_staff_engineer.config  # Load the project-root .env file.
from virtual_staff_engineer.github import (
    GitHubAppClient,
    GitHubPullRequestDelivery,
)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Fetch and validate one read-only GitHub PR snapshot."
    )
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pull-request", type=int, required=True)
    parser.add_argument("--installation-id", type=int, required=True)
    parser.add_argument("--head-sha", required=True)
    return parser.parse_args()


def main():
    arguments = parse_arguments()
    identity = (
        f"{arguments.owner}/{arguments.repository}#"
        f"{arguments.pull_request}@{arguments.head_sha}"
    )
    delivery = GitHubPullRequestDelivery(
        delivery_id="manual-fetch-" + hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()[:32],
        event_name="pull_request",
        action="synchronize",
        repository_owner=arguments.owner,
        repository_name=arguments.repository,
        installation_id=arguments.installation_id,
        pull_request_number=arguments.pull_request,
        head_sha=arguments.head_sha,
        payload_sha256=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
    )
    snapshot = GitHubAppClient().fetch_pull_request(delivery)
    print(
        json.dumps(
            {
                "repository": (
                    snapshot.repository_owner + "/" + snapshot.repository_name
                ),
                "pull_request": snapshot.pull_request_number,
                "url": snapshot.html_url,
                "head_sha": snapshot.head_sha,
                "base_sha": snapshot.base_sha,
                "changed_files": len(snapshot.files),
                "analyzable_files": [
                    item.filename for item in snapshot.files if item.analyzable
                ],
                "skipped_files": [
                    {"path": item.filename, "reason": item.skip_reason}
                    for item in snapshot.skipped_files
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
