from dataclasses import dataclass
from typing import Optional, Tuple


def _require_text(value, field_name, maximum=None):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    normalized = value.strip()
    if maximum is not None and len(normalized) > maximum:
        raise ValueError(
            f"{field_name} must contain at most {maximum} characters."
        )
    return normalized


@dataclass(frozen=True)
class HumanDecision:
    decision: str
    actor: str
    comment: Optional[str] = None
    authentication_method: str = "development_cli"
    authenticated_subject: Optional[str] = None
    authentication_issuer: Optional[str] = None

    def __post_init__(self):
        if self.decision not in {"approved", "rejected"}:
            raise ValueError("decision must be approved or rejected.")
        object.__setattr__(self, "actor", _require_text(self.actor, "actor", 255))
        if self.comment is not None:
            object.__setattr__(
                self,
                "comment",
                _require_text(self.comment, "comment", 4000),
            )
        method = _require_text(
            self.authentication_method, "authentication_method", 100
        )
        object.__setattr__(self, "authentication_method", method)
        authenticated = method != "development_cli"
        if authenticated:
            if self.authenticated_subject is None or self.authentication_issuer is None:
                raise ValueError(
                    "Authenticated decisions require a subject and issuer."
                )
            object.__setattr__(
                self,
                "authenticated_subject",
                _require_text(
                    self.authenticated_subject, "authenticated_subject", 255
                ),
            )
            object.__setattr__(
                self,
                "authentication_issuer",
                _require_text(
                    self.authentication_issuer, "authentication_issuer", 255
                ),
            )
        elif self.authenticated_subject is not None or self.authentication_issuer is not None:
            raise ValueError(
                "Development CLI decisions cannot claim authenticated identity."
            )


@dataclass(frozen=True)
class ApprovalRule:
    rule_key: str
    rule_snapshot: str

    def __post_init__(self):
        _require_text(self.rule_key, "rule_key")
        _require_text(self.rule_snapshot, "rule_snapshot")


@dataclass(frozen=True)
class ApprovalCheck:
    name: str
    status: str
    details: str

    def __post_init__(self):
        _require_text(self.name, "name")
        _require_text(self.details, "details")
        if self.status not in {"passed", "failed", "skipped"}:
            raise ValueError("Unknown approval check status.")


@dataclass(frozen=True)
class ApprovalRequest:
    workflow_job_id: str
    remediation_action_id: str
    patch_proposal_id: str
    source_path: str
    source_revision: Optional[str]
    original_sha256: str
    unified_diff: str
    explanation: str
    rules: Tuple[ApprovalRule, ...]
    validation_status: str
    resulting_sha256: str
    checks: Tuple[ApprovalCheck, ...]

    def __post_init__(self):
        for field_name in (
            "workflow_job_id",
            "remediation_action_id",
            "patch_proposal_id",
            "source_path",
            "original_sha256",
            "unified_diff",
            "explanation",
            "resulting_sha256",
        ):
            _require_text(getattr(self, field_name), field_name)
        if self.source_revision is not None:
            _require_text(self.source_revision, "source_revision")
        if self.validation_status != "valid":
            raise ValueError("Only valid patches can request approval.")
        if not self.rules or not all(
            isinstance(item, ApprovalRule) for item in self.rules
        ):
            raise ValueError("rules must contain ApprovalRule values.")
        if not self.checks or not all(
            isinstance(item, ApprovalCheck) for item in self.checks
        ):
            raise ValueError("checks must contain ApprovalCheck values.")


@dataclass(frozen=True)
class HumanDecisionResult:
    job: object
    created: bool
