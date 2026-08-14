"""Authenticated, idempotent GitHub mutation boundary."""

from virtual_staff_engineer.github.client import (
    GitHubApiError,
    GitHubClient,
    GitHubIdentity,
    GitHubPullRequestResult,
    GitHubStaleSourceError,
)
from virtual_staff_engineer.github.contracts import GitHubPullRequestContext
from virtual_staff_engineer.github.app_client import (
    GitHubAppClient,
    GitHubInstallationToken,
    GitHubPullRequestChangedError,
    GitHubPullRequestFile,
    GitHubPullRequestSnapshot,
    GitHubPullRequestTooLargeError,
)
from virtual_staff_engineer.github.webhook import (
    GitHubPullRequestDelivery,
    GitHubWebhookSignatureError,
    SUPPORTED_PULL_REQUEST_ACTIONS,
    decode_webhook_payload,
    parse_pull_request_delivery,
    verify_webhook_signature,
)
from virtual_staff_engineer.github.webhook_repository import (
    GitHubDeliveryConflictError,
    GitHubDeliveryRecordResult,
    GitHubJobContext,
    GitHubJobSummary,
    GitHubPullRequestSummary,
    GitHubWebhookDeliveryRepository,
    GitHubWebhookClaim,
)
from virtual_staff_engineer.github.ingestion_worker import (
    GitHubIngestionExecution,
    GitHubWebhookIngestionWorker,
    classify_ingestion_failure,
)

__all__ = [
    "GitHubApiError",
    "GitHubClient",
    "GitHubIdentity",
    "GitHubPullRequestContext",
    "GitHubPullRequestResult",
    "GitHubStaleSourceError",
    "GitHubAppClient",
    "GitHubInstallationToken",
    "GitHubPullRequestChangedError",
    "GitHubPullRequestFile",
    "GitHubPullRequestSnapshot",
    "GitHubPullRequestTooLargeError",
    "GitHubPullRequestDelivery",
    "GitHubWebhookSignatureError",
    "SUPPORTED_PULL_REQUEST_ACTIONS",
    "decode_webhook_payload",
    "parse_pull_request_delivery",
    "verify_webhook_signature",
    "GitHubDeliveryConflictError",
    "GitHubDeliveryRecordResult",
    "GitHubJobContext",
    "GitHubJobSummary",
    "GitHubPullRequestSummary",
    "GitHubWebhookDeliveryRepository",
    "GitHubWebhookClaim",
    "GitHubIngestionExecution",
    "GitHubWebhookIngestionWorker",
    "classify_ingestion_failure",
]
