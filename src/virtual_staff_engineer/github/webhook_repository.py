import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from virtual_staff_engineer.database.connection import connect
from virtual_staff_engineer.github.app_client import GitHubPullRequestSnapshot
from virtual_staff_engineer.github.webhook import GitHubPullRequestDelivery
from virtual_staff_engineer.jobs.lifecycle import FailureDisposition, JobFailure


class GitHubDeliveryConflictError(ValueError):
    """A delivery ID was reused with different immutable webhook metadata."""


@dataclass(frozen=True)
class GitHubDeliveryRecordResult:
    delivery: GitHubPullRequestDelivery
    created: bool


@dataclass(frozen=True)
class GitHubWebhookClaim:
    delivery: GitHubPullRequestDelivery
    status: str
    attempt_count: int
    max_attempts: int
    lease_owner: str
    lease_token: str
    lease_expires_at: datetime


@dataclass(frozen=True)
class GitHubJobSummary:
    workflow_job_id: str
    source_path: str
    status: str
    checkpoint: str
    failure_code: Optional[str]
    created_pull_request_url: Optional[str]


@dataclass(frozen=True)
class GitHubPullRequestSummary:
    delivery_id: str
    repository_owner: str
    repository_name: str
    pull_request_number: int
    pull_request_title: Optional[str]
    pull_request_url: Optional[str]
    head_sha: str
    base_sha: Optional[str]
    status: str
    changed_file_count: Optional[int]
    analyzable_file_count: Optional[int]
    skipped_file_count: Optional[int]
    received_at: datetime
    completed_at: Optional[datetime]
    jobs: Tuple[GitHubJobSummary, ...]


@dataclass(frozen=True)
class GitHubJobContext:
    delivery_id: str
    repository_owner: str
    repository_name: str
    pull_request_number: int
    pull_request_title: Optional[str]
    pull_request_url: Optional[str]
    head_sha: str
    source_path: str
    created_pull_request_url: Optional[str]


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

    def list_pull_requests(self, limit=20):
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer.")
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100.")
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT delivery_id,
                           repository_owner,
                           repository_name,
                           pull_request_number,
                           pull_request_title,
                           pull_request_url,
                           head_sha,
                           base_sha,
                           status,
                           changed_file_count,
                           analyzable_file_count,
                           skipped_file_count,
                           received_at,
                           completed_at
                    FROM github_webhook_deliveries
                    ORDER BY received_at DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                deliveries = cur.fetchall()
                if not deliveries:
                    return ()
                delivery_ids = [row[0] for row in deliveries]
                cur.execute(
                    """
                    SELECT link.delivery_id,
                           link.workflow_job_id,
                           link.source_path,
                           job.status,
                           job.checkpoint,
                           job.failure_code,
                           operation.pr_url
                    FROM github_webhook_delivery_jobs AS link
                    JOIN workflow_jobs AS job
                      ON job.workflow_job_id = link.workflow_job_id
                    LEFT JOIN github_pr_operations AS operation
                      ON operation.workflow_job_id = link.workflow_job_id
                    WHERE link.delivery_id = ANY(%s::varchar[])
                    ORDER BY link.delivery_id, link.source_path;
                    """,
                    (delivery_ids,),
                )
                job_rows = cur.fetchall()
        jobs_by_delivery = {delivery_id: [] for delivery_id in delivery_ids}
        for row in job_rows:
            jobs_by_delivery[row[0]].append(
                GitHubJobSummary(
                    workflow_job_id=str(row[1]),
                    source_path=row[2],
                    status=row[3],
                    checkpoint=row[4],
                    failure_code=row[5],
                    created_pull_request_url=row[6],
                )
            )
        return tuple(
            GitHubPullRequestSummary(
                delivery_id=row[0],
                repository_owner=row[1],
                repository_name=row[2],
                pull_request_number=row[3],
                pull_request_title=row[4],
                pull_request_url=row[5],
                head_sha=row[6],
                base_sha=row[7],
                status=row[8],
                changed_file_count=row[9],
                analyzable_file_count=row[10],
                skipped_file_count=row[11],
                received_at=row[12],
                completed_at=row[13],
                jobs=tuple(jobs_by_delivery[row[0]]),
            )
            for row in deliveries
        )

    def get_job_context(self, workflow_job_id):
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT delivery.delivery_id,
                           delivery.repository_owner,
                           delivery.repository_name,
                           delivery.pull_request_number,
                           delivery.pull_request_title,
                           delivery.pull_request_url,
                           delivery.head_sha,
                           link.source_path,
                           operation.pr_url
                    FROM github_webhook_delivery_jobs AS link
                    JOIN github_webhook_deliveries AS delivery
                      ON delivery.delivery_id = link.delivery_id
                    LEFT JOIN github_pr_operations AS operation
                      ON operation.workflow_job_id = link.workflow_job_id
                    WHERE link.workflow_job_id = %s;
                    """,
                    (workflow_job_id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return GitHubJobContext(
            delivery_id=row[0],
            repository_owner=row[1],
            repository_name=row[2],
            pull_request_number=row[3],
            pull_request_title=row[4],
            pull_request_url=row[5],
            head_sha=row[6],
            source_path=row[7],
            created_pull_request_url=row[8],
        )

    def claim_next(self, worker_id, lease_seconds=300):
        if not isinstance(worker_id, str) or not worker_id.strip():
            raise ValueError("worker_id must be a non-empty string.")
        if (
            isinstance(lease_seconds, bool)
            or not isinstance(lease_seconds, int)
            or lease_seconds < 3
        ):
            raise ValueError("lease_seconds must be an integer of at least 3.")
        self.recover_expired_leases()
        lease_token = uuid.uuid4()
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    WITH candidate AS (
                        SELECT delivery_id
                        FROM github_webhook_deliveries
                        WHERE status IN ('received', 'retry_scheduled')
                          AND available_at <= CURRENT_TIMESTAMP
                          AND attempt_count < max_attempts
                        ORDER BY available_at, received_at, delivery_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE github_webhook_deliveries AS delivery
                    SET status = 'processing',
                        attempt_count = attempt_count + 1,
                        lease_owner = %s,
                        lease_token = %s,
                        lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
                        failure_code = NULL,
                        error_message = NULL
                    FROM candidate
                    WHERE delivery.delivery_id = candidate.delivery_id
                    RETURNING delivery.delivery_id,
                              delivery.event_name,
                              delivery.action,
                              delivery.repository_owner,
                              delivery.repository_name,
                              delivery.installation_id,
                              delivery.pull_request_number,
                              delivery.head_sha,
                              delivery.payload_sha256,
                              delivery.status,
                              delivery.attempt_count,
                              delivery.max_attempts,
                              delivery.lease_owner,
                              delivery.lease_token,
                              delivery.lease_expires_at;
                    """,
                    (worker_id.strip(), lease_token, lease_seconds),
                )
                row = cur.fetchone()
        return _row_to_claim(row) if row is not None else None

    def recover_expired_leases(self):
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE github_webhook_deliveries
                    SET status = CASE
                            WHEN attempt_count < max_attempts
                            THEN 'retry_scheduled'
                            ELSE 'failed'
                        END,
                        available_at = CURRENT_TIMESTAMP,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        failure_code = 'expired_lease',
                        error_message = 'GitHub ingestion worker lease expired.'
                    WHERE status = 'processing'
                      AND lease_expires_at <= CURRENT_TIMESTAMP
                    RETURNING delivery_id;
                    """
                )
                rows = cur.fetchall()
        return tuple(row[0] for row in rows)

    def heartbeat(self, delivery_id, lease_token, lease_seconds=300):
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE github_webhook_deliveries
                    SET lease_expires_at = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second')
                    WHERE delivery_id = %s
                      AND status = 'processing'
                      AND lease_token = %s
                      AND lease_expires_at > CURRENT_TIMESTAMP
                    RETURNING lease_expires_at;
                    """,
                    (lease_seconds, delivery_id, lease_token),
                )
                row = cur.fetchone()
        if row is None:
            raise RuntimeError("GitHub webhook ingestion lease was lost.")
        return row[0]

    def persist_snapshot(self, claim, snapshot):
        _matching_snapshot(claim, snapshot)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                self._require_owned(cur, claim)
                cur.execute(
                    """
                    INSERT INTO repositories (owner, name, github_url)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (owner, name) DO UPDATE
                    SET github_url = EXCLUDED.github_url
                    RETURNING repository_id;
                    """,
                    (
                        snapshot.repository_owner,
                        snapshot.repository_name,
                        snapshot.html_url.split("/pull/")[0],
                    ),
                )
                repository_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO commits (
                        repository_id, commit_sha, author, message
                    )
                    VALUES (%s, %s, 'github-app', %s)
                    ON CONFLICT (repository_id, commit_sha) DO UPDATE
                    SET commit_sha = EXCLUDED.commit_sha
                    RETURNING commit_id;
                    """,
                    (
                        repository_id,
                        snapshot.head_sha.lower(),
                        f"GitHub PR #{snapshot.pull_request_number} head snapshot",
                    ),
                )
                commit_id = cur.fetchone()[0]
                for item in snapshot.files:
                    if not item.analyzable:
                        continue
                    content_hash = hashlib.sha256(
                        item.source_content.encode("utf-8")
                    ).hexdigest()
                    cur.execute(
                        """
                        INSERT INTO github_pr_file_snapshots (
                            commit_id,
                            source_path,
                            blob_sha,
                            change_status,
                            source_content,
                            source_sha256,
                            unified_diff
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (commit_id, source_path) DO NOTHING;
                        """,
                        (
                            commit_id,
                            item.filename,
                            item.blob_sha.lower(),
                            item.status,
                            item.source_content,
                            content_hash,
                            item.unified_diff,
                        ),
                    )
                    cur.execute(
                        """
                        SELECT blob_sha, source_sha256, unified_diff
                        FROM github_pr_file_snapshots
                        WHERE commit_id = %s AND source_path = %s;
                        """,
                        (commit_id, item.filename),
                    )
                    existing = cur.fetchone()
                    if existing != (
                        item.blob_sha.lower(),
                        content_hash,
                        item.unified_diff,
                    ):
                        raise ValueError(
                            "GitHub source snapshot conflicts with persisted data."
                        )
        return str(commit_id)

    def link_job(self, claim, workflow_job_id, source_path):
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                self._require_owned(cur, claim)
                cur.execute(
                    """
                    INSERT INTO github_webhook_delivery_jobs (
                        delivery_id, workflow_job_id, source_path
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (delivery_id, workflow_job_id) DO NOTHING;
                    """,
                    (claim.delivery.delivery_id, workflow_job_id, source_path),
                )

    def complete(self, claim, snapshot):
        _matching_snapshot(claim, snapshot)
        analyzable_count = sum(item.analyzable for item in snapshot.files)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE github_webhook_deliveries
                    SET status = 'completed',
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        pull_request_title = %s,
                        pull_request_url = %s,
                        base_sha = %s,
                        changed_file_count = %s,
                        analyzable_file_count = %s,
                        skipped_file_count = %s,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE delivery_id = %s
                      AND status = 'processing'
                      AND lease_token = %s
                      AND lease_expires_at > CURRENT_TIMESTAMP
                    RETURNING delivery_id;
                    """,
                    (
                        snapshot.title,
                        snapshot.html_url,
                        snapshot.base_sha.lower(),
                        len(snapshot.files),
                        analyzable_count,
                        len(snapshot.files) - analyzable_count,
                        claim.delivery.delivery_id,
                        claim.lease_token,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise RuntimeError("GitHub webhook ingestion lease was lost.")
        return "completed"

    def schedule_failure(self, claim, failure, delay_seconds=0):
        if not isinstance(failure, JobFailure):
            raise TypeError("failure must be a JobFailure.")
        retryable = (
            failure.disposition is FailureDisposition.RETRYABLE
            and claim.attempt_count < claim.max_attempts
        )
        target = "retry_scheduled" if retryable else "failed"
        available_at = datetime.now(timezone.utc) + timedelta(
            seconds=max(0, delay_seconds)
        )
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE github_webhook_deliveries
                    SET status = %s,
                        available_at = %s,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        failure_code = %s,
                        error_message = %s
                    WHERE delivery_id = %s
                      AND status = 'processing'
                      AND lease_token = %s
                    RETURNING delivery_id;
                    """,
                    (
                        target,
                        available_at,
                        failure.code.value,
                        failure.message[:4000],
                        claim.delivery.delivery_id,
                        claim.lease_token,
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise RuntimeError("GitHub webhook ingestion lease was lost.")
        return target

    @staticmethod
    def _require_owned(cur, claim):
        cur.execute(
            """
            SELECT 1
            FROM github_webhook_deliveries
            WHERE delivery_id = %s
              AND status = 'processing'
              AND lease_token = %s
              AND lease_expires_at > CURRENT_TIMESTAMP
            FOR UPDATE;
            """,
            (claim.delivery.delivery_id, claim.lease_token),
        )
        if cur.fetchone() is None:
            raise RuntimeError("GitHub webhook ingestion lease was lost.")


def _row_to_claim(row):
    delivery = GitHubPullRequestDelivery(*row[:9])
    return GitHubWebhookClaim(
        delivery=delivery,
        status=row[9],
        attempt_count=row[10],
        max_attempts=row[11],
        lease_owner=row[12],
        lease_token=str(row[13]),
        lease_expires_at=row[14],
    )


def _matching_snapshot(claim, snapshot):
    if not isinstance(claim, GitHubWebhookClaim):
        raise TypeError("claim must be a GitHubWebhookClaim.")
    if not isinstance(snapshot, GitHubPullRequestSnapshot):
        raise TypeError("snapshot must be a GitHubPullRequestSnapshot.")
    delivery = claim.delivery
    if (
        snapshot.repository_owner != delivery.repository_owner
        or snapshot.repository_name != delivery.repository_name
        or snapshot.installation_id != delivery.installation_id
        or snapshot.pull_request_number != delivery.pull_request_number
        or snapshot.head_sha.lower() != delivery.head_sha.lower()
    ):
        raise ValueError("GitHub PR snapshot does not match claimed delivery.")
