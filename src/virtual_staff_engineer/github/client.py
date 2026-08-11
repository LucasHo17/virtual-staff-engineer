import base64
import hashlib
import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from virtual_staff_engineer.github.contracts import GitHubPullRequestContext
from virtual_staff_engineer.remediation.validation import apply_unified_diff


class GitHubApiError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class GitHubStaleSourceError(ValueError):
    """The approved source no longer matches the GitHub branch baseline."""


@dataclass(frozen=True)
class GitHubIdentity:
    login: str
    subject: str
    issuer: str = "https://github.com"
    authentication_method: str = "github_token"

    def __post_init__(self):
        if not isinstance(self.login, str) or not self.login.strip():
            raise ValueError("login must be a non-empty string.")
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise ValueError("subject must be a non-empty string.")


@dataclass(frozen=True)
class GitHubPullRequestResult:
    branch_name: str
    commit_sha: str
    pr_number: int
    pr_url: str

    def __post_init__(self):
        if (
            not isinstance(self.branch_name, str)
            or not self.branch_name.strip()
        ):
            raise ValueError("branch_name must be a non-empty string.")
        if (
            not isinstance(self.commit_sha, str)
            or len(self.commit_sha) not in {40, 64}
            or any(
                character not in "0123456789abcdefABCDEF"
                for character in self.commit_sha
            )
        ):
            raise ValueError("commit_sha must be a 40- or 64-character hex SHA.")
        if (
            isinstance(self.pr_number, bool)
            or not isinstance(self.pr_number, int)
            or self.pr_number < 1
        ):
            raise ValueError("pr_number must be a positive integer.")
        if not isinstance(self.pr_url, str) or not self.pr_url.strip():
            raise ValueError("pr_url must be a non-empty string.")


class GitHubClient:
    """Small REST adapter that reconciles remote state before every mutation."""

    def __init__(self, token=None, api_url="https://api.github.com", transport=None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if transport is None and not self.token:
            raise RuntimeError("GITHUB_TOKEN is not configured.")
        self.api_url = api_url.rstrip("/")
        self.transport = transport or self._request

    def authenticate(self):
        user = self.transport("GET", "/user", None)
        login = str(user.get("login", "")).strip()
        subject = str(user.get("id", "")).strip()
        if not login or not subject:
            raise GitHubApiError("GitHub /user response lacks login or id.")
        return GitHubIdentity(login=login, subject=subject)

    def ensure_pull_request(self, context):
        if not isinstance(context, GitHubPullRequestContext):
            raise TypeError("context must be a GitHubPullRequestContext.")
        prefix = f"/repos/{quote(context.owner)}/{quote(context.repository)}"
        repository = self.transport("GET", prefix, None)
        base_branch = repository.get("default_branch")
        if not isinstance(base_branch, str) or not base_branch:
            raise GitHubApiError("Repository response lacks a default branch.")

        existing = self._find_pr(prefix, context)

        ref_path = prefix + "/git/ref/heads/" + quote(context.head_branch, safe="")
        try:
            ref = self.transport("GET", ref_path, None)
        except GitHubApiError as exc:
            if exc.status_code != 404:
                raise
            ref = self.transport(
                "POST",
                prefix + "/git/refs",
                {"ref": "refs/heads/" + context.head_branch, "sha": context.base_commit_sha},
            )
        branch_sha = ref.get("object", {}).get("sha") or ref.get("sha")

        file_path = prefix + "/contents/" + quote(context.source_path, safe="/")
        remote = self.transport(
            "GET", file_path + "?ref=" + quote(context.head_branch, safe=""), None
        )
        try:
            current = base64.b64decode(remote["content"]).decode("utf-8")
        except (KeyError, ValueError, UnicodeDecodeError) as exc:
            raise GitHubApiError("GitHub file response has invalid content.") from exc
        current_hash = hashlib.sha256(current.encode("utf-8")).hexdigest()
        if current_hash == context.resulting_sha256:
            commit_sha = (
                existing.get("head", {}).get("sha")
                if existing is not None
                else branch_sha or remote.get("sha")
            )
        else:
            if current_hash != context.original_sha256:
                raise GitHubStaleSourceError(
                    "GitHub branch source differs from the approved baseline."
                )
            patched, _ = apply_unified_diff(
                context.original_content, context.unified_diff, context.source_path
            )
            patched_hash = hashlib.sha256(patched.encode("utf-8")).hexdigest()
            if patched_hash != context.resulting_sha256:
                raise GitHubStaleSourceError(
                    "Approved diff no longer matches its validated result hash."
                )
            updated = self.transport(
                "PUT",
                file_path,
                {
                    "message": context.title,
                    "content": base64.b64encode(patched.encode("utf-8")).decode("ascii"),
                    "sha": remote.get("sha"),
                    "branch": context.head_branch,
                },
            )
            commit_sha = updated.get("commit", {}).get("sha")

        existing = existing or self._find_pr(prefix, context)
        if existing is None:
            existing = self.transport(
                "POST",
                prefix + "/pulls",
                {
                    "title": context.title,
                    "body": context.body,
                    "head": context.head_branch,
                    "base": base_branch,
                },
            )
        result = self._result(context, existing, commit_sha=commit_sha)
        if not result.commit_sha:
            raise GitHubApiError("Unable to determine the remediation commit SHA.")
        return result

    def _find_pr(self, prefix, context):
        path = (
            prefix + "/pulls?state=all&head="
            + quote(context.owner + ":" + context.head_branch, safe="")
        )
        pulls = self.transport("GET", path, None)
        if not isinstance(pulls, list):
            raise GitHubApiError("GitHub pull request search returned invalid data.")
        return pulls[0] if pulls else None

    @staticmethod
    def _result(context, pull, commit_sha=None):
        number = pull.get("number")
        url = pull.get("html_url")
        sha = commit_sha or pull.get("head", {}).get("sha")
        if not isinstance(number, int) or number < 1 or not url:
            raise GitHubApiError("GitHub pull request response is incomplete.")
        return GitHubPullRequestResult(context.head_branch, sha, number, url)

    def _request(self, method, path, payload):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            self.api_url + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer " + self.token,
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "virtual-staff-engineer",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GitHubApiError(
                f"GitHub API returned HTTP {exc.code} for {method} {path}.",
                status_code=exc.code,
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise ConnectionError(f"GitHub API request failed: {exc}") from exc
