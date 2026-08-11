import base64
import hashlib
import unittest

from virtual_staff_engineer.github import (
    GitHubApiError,
    GitHubClient,
    GitHubPullRequestContext,
    GitHubStaleSourceError,
)


ORIGINAL = "token = request.token\nlog(token)\n"
PATCHED = "token = request.token\nlog(\"request received\")\n"
DIFF = (
    "--- a/app.py\n"
    "+++ b/app.py\n"
    "@@ -1,2 +1,2 @@\n"
    " token = request.token\n"
    "-log(token)\n"
    "+log(\"request received\")"
)


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def context():
    return GitHubPullRequestContext(
        workflow_job_id="job-1",
        remediation_action_id="action-1",
        operation_id="operation-1",
        owner="acme",
        repository="service",
        base_commit_sha="a" * 40,
        head_branch="vse/remediation-action1",
        source_path="app.py",
        original_content=ORIGINAL,
        original_sha256=digest(ORIGINAL),
        resulting_sha256=digest(PATCHED),
        unified_diff=DIFF,
        explanation="Remove sensitive data from logs.",
        rule_keys=("SEC-01",),
        approved_by="reviewer",
    )


class FakeGitHub:
    def __init__(self, content=ORIGINAL):
        self.content = content
        self.branch = False
        self.pull = None
        self.calls = []

    def __call__(self, method, path, payload):
        self.calls.append((method, path, payload))
        if path == "/user":
            return {"login": "octocat", "id": 42}
        if path == "/repos/acme/service":
            return {"default_branch": "main"}
        if "/pulls?" in path:
            return [] if self.pull is None else [self.pull]
        if "/git/ref/heads/" in path:
            if not self.branch:
                raise GitHubApiError("missing", 404)
            return {"object": {"sha": "b" * 40}}
        if path.endswith("/git/refs"):
            self.branch = True
            return {"object": {"sha": "a" * 40}}
        if "/contents/app.py?" in path:
            return {
                "content": base64.b64encode(self.content.encode()).decode(),
                "sha": "f" * 40,
            }
        if path.endswith("/contents/app.py"):
            self.content = base64.b64decode(payload["content"]).decode()
            return {"commit": {"sha": "c" * 40}}
        if path.endswith("/pulls"):
            self.pull = {
                "number": 7,
                "html_url": "https://github.com/acme/service/pull/7",
                "head": {"sha": "c" * 40},
            }
            return self.pull
        raise AssertionError((method, path, payload))


class GitHubClientTests(unittest.TestCase):
    def test_authenticates_reviewer_from_github_identity(self):
        identity = GitHubClient(transport=FakeGitHub()).authenticate()
        self.assertEqual(identity.login, "octocat")
        self.assertEqual(identity.subject, "42")
        self.assertEqual(identity.authentication_method, "github_token")

    def test_creates_branch_exact_commit_and_one_pull_request(self):
        github = FakeGitHub()
        result = GitHubClient(transport=github).ensure_pull_request(context())
        self.assertEqual(github.content, PATCHED)
        self.assertEqual(result.pr_number, 7)
        create_ref = next(call for call in github.calls if call[1].endswith("/git/refs"))
        self.assertEqual(create_ref[2]["sha"], "a" * 40)

    def test_retry_reconciles_patched_branch_and_existing_pr(self):
        github = FakeGitHub()
        client = GitHubClient(transport=github)
        first = client.ensure_pull_request(context())
        puts_before = sum(call[0] == "PUT" for call in github.calls)
        posts_before = sum(call[1].endswith("/pulls") for call in github.calls)
        second = client.ensure_pull_request(context())
        self.assertEqual(first, second)
        self.assertEqual(sum(call[0] == "PUT" for call in github.calls), puts_before)
        self.assertEqual(
            sum(call[1].endswith("/pulls") for call in github.calls), posts_before
        )

    def test_rejects_source_that_is_neither_original_nor_validated_result(self):
        github = FakeGitHub("unexpected\n")
        with self.assertRaises(GitHubStaleSourceError):
            GitHubClient(transport=github).ensure_pull_request(context())
        self.assertFalse(any(call[0] == "PUT" for call in github.calls))


if __name__ == "__main__":
    unittest.main()
