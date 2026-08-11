"""Authenticated, idempotent GitHub mutation boundary."""

from virtual_staff_engineer.github.client import (
    GitHubApiError,
    GitHubClient,
    GitHubIdentity,
    GitHubPullRequestResult,
    GitHubStaleSourceError,
)
from virtual_staff_engineer.github.contracts import GitHubPullRequestContext

__all__ = [
    "GitHubApiError",
    "GitHubClient",
    "GitHubIdentity",
    "GitHubPullRequestContext",
    "GitHubPullRequestResult",
    "GitHubStaleSourceError",
]
