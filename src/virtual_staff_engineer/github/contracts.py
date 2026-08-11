from dataclasses import dataclass
from typing import Tuple


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value.strip()


@dataclass(frozen=True)
class GitHubPullRequestContext:
    workflow_job_id: str
    remediation_action_id: str
    operation_id: str
    owner: str
    repository: str
    base_commit_sha: str
    head_branch: str
    source_path: str
    original_content: str
    original_sha256: str
    resulting_sha256: str
    unified_diff: str
    explanation: str
    rule_keys: Tuple[str, ...]
    approved_by: str

    def __post_init__(self):
        for name in (
            "workflow_job_id", "remediation_action_id", "operation_id",
            "owner", "repository", "base_commit_sha", "head_branch",
            "source_path", "original_sha256", "resulting_sha256",
            "unified_diff", "explanation", "approved_by",
        ):
            _text(getattr(self, name), name)
        if not isinstance(self.original_content, str):
            raise TypeError("original_content must be a string.")
        if not self.rule_keys or not all(
            isinstance(value, str) and value.strip() for value in self.rule_keys
        ):
            raise ValueError("rule_keys must contain non-empty strings.")

    @property
    def title(self):
        return "[VSE] Remediate " + ", ".join(self.rule_keys)

    @property
    def body(self):
        rules = ", ".join(self.rule_keys)
        return (
            f"{self.explanation}\n\n"
            f"Rules addressed: {rules}\n\n"
            f"Approved by: {self.approved_by}\n"
            f"Workflow job: {self.workflow_job_id}"
        )
