import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone


SUPPORTED_PULL_REQUEST_ACTIONS = frozenset(
    {"opened", "reopened", "synchronize", "ready_for_review"}
)
LIFECYCLE_PULL_REQUEST_ACTIONS = SUPPORTED_PULL_REQUEST_ACTIONS | {"closed"}


class GitHubWebhookSignatureError(ValueError):
    """The request was not signed with the configured webhook secret."""


@dataclass(frozen=True)
class GitHubPullRequestDelivery:
    delivery_id: str
    event_name: str
    action: str
    repository_owner: str
    repository_name: str
    installation_id: int
    pull_request_number: int
    head_sha: str
    payload_sha256: str

    def __post_init__(self):
        for name in (
            "delivery_id",
            "event_name",
            "action",
            "repository_owner",
            "repository_name",
            "payload_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if self.event_name != "pull_request":
            raise ValueError("event_name must be pull_request.")
        if self.action not in SUPPORTED_PULL_REQUEST_ACTIONS:
            raise ValueError("action is not a supported pull-request action.")
        for name in ("installation_id", "pull_request_number"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if not _is_hex_sha(self.head_sha):
            raise ValueError("head_sha must be a 40- or 64-character hex SHA.")
        if len(self.payload_sha256) != 64 or not _is_hex(self.payload_sha256):
            raise ValueError("payload_sha256 must be a SHA-256 hex digest.")


@dataclass(frozen=True)
class GitHubPullRequestLifecycleUpdate:
    delivery_id: str
    repository_owner: str
    repository_name: str
    pull_request_number: int
    action: str
    lifecycle_state: str
    title: str
    pull_request_url: str
    head_sha: str
    github_updated_at: datetime
    payload_sha256: str

    def __post_init__(self):
        for name in (
            "delivery_id", "repository_owner", "repository_name", "action",
            "lifecycle_state", "title", "pull_request_url", "payload_sha256",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if self.action not in LIFECYCLE_PULL_REQUEST_ACTIONS:
            raise ValueError("action is not a tracked pull-request action.")
        if self.lifecycle_state not in {"open", "closed", "merged"}:
            raise ValueError("lifecycle_state is invalid.")
        if self.pull_request_number < 1:
            raise ValueError("pull_request_number must be positive.")
        if not _is_hex_sha(self.head_sha):
            raise ValueError("head_sha must be a 40- or 64-character hex SHA.")
        if self.github_updated_at.tzinfo is None:
            raise ValueError("github_updated_at must be timezone-aware.")


def verify_webhook_signature(raw_body, signature, secret):
    if not isinstance(raw_body, bytes):
        raise TypeError("raw_body must be bytes.")
    if not isinstance(secret, str) or not secret:
        raise RuntimeError("GitHub webhook secret is not configured.")
    if not isinstance(signature, str) or not signature.startswith("sha256="):
        raise GitHubWebhookSignatureError("Invalid GitHub webhook signature.")
    supplied = signature[len("sha256=") :]
    if len(supplied) != 64 or not _is_hex(supplied):
        raise GitHubWebhookSignatureError("Invalid GitHub webhook signature.")
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, supplied.lower()):
        raise GitHubWebhookSignatureError("Invalid GitHub webhook signature.")


def decode_webhook_payload(raw_body):
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("GitHub webhook body must be valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError("GitHub webhook JSON must be an object.")
    return payload


def parse_pull_request_delivery(delivery_id, event_name, payload, raw_body):
    if event_name != "pull_request":
        return None
    action = payload.get("action")
    if action not in SUPPORTED_PULL_REQUEST_ACTIONS:
        return None
    try:
        repository = payload["repository"]
        owner = repository["owner"]["login"]
        repository_name = repository["name"]
        installation_id = payload["installation"]["id"]
        pull_request = payload["pull_request"]
        pull_request_number = pull_request["number"]
        head_sha = pull_request["head"]["sha"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "Supported pull_request payload lacks required repository, "
            "installation, PR, or head fields."
        ) from exc
    return GitHubPullRequestDelivery(
        delivery_id=delivery_id,
        event_name=event_name,
        action=action,
        repository_owner=owner,
        repository_name=repository_name,
        installation_id=installation_id,
        pull_request_number=pull_request_number,
        head_sha=head_sha,
        payload_sha256=hashlib.sha256(raw_body).hexdigest(),
    )


def parse_pull_request_lifecycle_update(
    delivery_id, event_name, payload, raw_body
):
    if event_name != "pull_request":
        return None
    action = payload.get("action")
    if action not in LIFECYCLE_PULL_REQUEST_ACTIONS:
        return None
    try:
        repository = payload["repository"]
        pull_request = payload["pull_request"]
        updated_at = pull_request["updated_at"]
        parsed_updated_at = datetime.fromisoformat(
            updated_at.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        state = (
            "merged" if action == "closed" and pull_request["merged"]
            else "closed" if action == "closed"
            else "open"
        )
        return GitHubPullRequestLifecycleUpdate(
            delivery_id=delivery_id,
            repository_owner=repository["owner"]["login"],
            repository_name=repository["name"],
            pull_request_number=pull_request["number"],
            action=action,
            lifecycle_state=state,
            title=pull_request["title"],
            pull_request_url=pull_request["html_url"],
            head_sha=pull_request["head"]["sha"],
            github_updated_at=parsed_updated_at,
            payload_sha256=hashlib.sha256(raw_body).hexdigest(),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(
            "Tracked pull_request payload lacks valid lifecycle fields."
        ) from exc


def _is_hex_sha(value):
    return (
        isinstance(value, str)
        and len(value) in {40, 64}
        and _is_hex(value)
    )


def _is_hex(value):
    return all(character in "0123456789abcdefABCDEF" for character in value)
