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
    GitHubPullRequestLifecycleUpdate,
    GitHubPullRequestDelivery,
    GitHubWebhookSignatureError,
    SUPPORTED_PULL_REQUEST_ACTIONS,
    decode_webhook_payload,
    parse_pull_request_delivery,
    parse_pull_request_lifecycle_update,
    verify_webhook_signature,
)
from virtual_staff_engineer.github.webhook_repository import (
    GitHubDeliveryConflictError,
    GitHubDeliveryRecordResult,
    GitHubLifecycleRecordResult,
    GitHubJobContext,
    GitHubJobSummary,
    GitHubPullRequestSummary,
    GitHubPullRequestPage,
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
    "GitHubPullRequestLifecycleUpdate",
    "GitHubWebhookSignatureError",
    "SUPPORTED_PULL_REQUEST_ACTIONS",
    "decode_webhook_payload",
    "parse_pull_request_delivery",
    "parse_pull_request_lifecycle_update",
    "verify_webhook_signature",
    "GitHubDeliveryConflictError",
    "GitHubDeliveryRecordResult",
    "GitHubLifecycleRecordResult",
    "GitHubJobContext",
    "GitHubJobSummary",
    "GitHubPullRequestSummary",
    "GitHubPullRequestPage",
    "GitHubWebhookDeliveryRepository",
    "GitHubWebhookClaim",
    "GitHubIngestionExecution",
    "GitHubWebhookIngestionWorker",
    "classify_ingestion_failure",
]
