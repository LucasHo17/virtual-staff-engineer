from dataclasses import dataclass

from virtual_staff_engineer.database.connection import connect
from virtual_staff_engineer.github.webhook import GitHubPullRequestDelivery


class GitHubDeliveryConflictError(ValueError):
    """A delivery ID was reused with different immutable webhook metadata."""


@dataclass(frozen=True)
class GitHubDeliveryRecordResult:
    delivery: GitHubPullRequestDelivery
    created: bool


class GitHubWebhookDeliveryRepository:
    def __init__(self, database_url=None):
        self.database_url = database_url

    def record(self, delivery):
        if not isinstance(delivery, GitHubPullRequestDelivery):
            raise TypeError("delivery must be a GitHubPullRequestDelivery.")
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO github_webhook_deliveries (
                        delivery_id,
                        event_name,
                        action,
                        repository_owner,
                        repository_name,
                        installation_id,
                        pull_request_number,
                        head_sha,
                        payload_sha256
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (delivery_id) DO NOTHING
                    RETURNING delivery_id;
                    """,
                    (
                        delivery.delivery_id,
                        delivery.event_name,
                        delivery.action,
                        delivery.repository_owner,
                        delivery.repository_name,
                        delivery.installation_id,
                        delivery.pull_request_number,
                        delivery.head_sha,
                        delivery.payload_sha256,
                    ),
                )
                created = cur.fetchone() is not None
                if not created:
                    cur.execute(
                        """
                        SELECT event_name,
                               action,
                               repository_owner,
                               repository_name,
                               installation_id,
                               pull_request_number,
                               head_sha,
                               payload_sha256
                        FROM github_webhook_deliveries
                        WHERE delivery_id = %s;
                        """,
                        (delivery.delivery_id,),
                    )
                    existing = cur.fetchone()
                    expected = (
                        delivery.event_name,
                        delivery.action,
                        delivery.repository_owner,
                        delivery.repository_name,
                        delivery.installation_id,
                        delivery.pull_request_number,
                        delivery.head_sha,
                        delivery.payload_sha256,
                    )
                    if existing != expected:
                        raise GitHubDeliveryConflictError(
                            "GitHub delivery ID was reused with different "
                            "immutable metadata."
                        )
            conn.commit()
        return GitHubDeliveryRecordResult(delivery, created)
