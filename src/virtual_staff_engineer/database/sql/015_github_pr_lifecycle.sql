-- Immutable PR lifecycle events plus one current-state projection per PR.

CREATE TABLE github_pull_request_lifecycle_events (
    delivery_id VARCHAR(100) PRIMARY KEY,
    repository_owner VARCHAR(255) NOT NULL,
    repository_name VARCHAR(255) NOT NULL,
    pull_request_number INTEGER NOT NULL,
    action VARCHAR(100) NOT NULL,
    lifecycle_state VARCHAR(20) NOT NULL,
    title TEXT NOT NULL,
    pull_request_url TEXT NOT NULL,
    head_sha VARCHAR(64) NOT NULL,
    github_updated_at TIMESTAMPTZ NOT NULL,
    payload_sha256 VARCHAR(64) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT github_pr_lifecycle_events_state_ck
        CHECK (lifecycle_state IN ('open', 'closed', 'merged')),
    CONSTRAINT github_pr_lifecycle_events_action_ck
        CHECK (action IN ('opened', 'reopened', 'synchronize', 'ready_for_review', 'closed')),
    CONSTRAINT github_pr_lifecycle_events_pr_ck CHECK (pull_request_number > 0),
    CONSTRAINT github_pr_lifecycle_events_head_ck CHECK (
        length(head_sha) IN (40, 64) AND head_sha ~ '^[0-9A-Fa-f]+$'
    ),
    CONSTRAINT github_pr_lifecycle_events_payload_ck CHECK (
        length(payload_sha256) = 64 AND payload_sha256 ~ '^[0-9A-Fa-f]+$'
    )
);

CREATE TABLE github_pull_requests (
    repository_owner VARCHAR(255) NOT NULL,
    repository_name VARCHAR(255) NOT NULL,
    pull_request_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    pull_request_url TEXT NOT NULL,
    lifecycle_state VARCHAR(20) NOT NULL,
    head_sha VARCHAR(64) NOT NULL,
    github_updated_at TIMESTAMPTZ NOT NULL,
    last_delivery_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT github_pull_requests_pk PRIMARY KEY (
        repository_owner, repository_name, pull_request_number
    ),
    CONSTRAINT github_pull_requests_last_delivery_fk FOREIGN KEY (last_delivery_id)
        REFERENCES github_pull_request_lifecycle_events(delivery_id) ON DELETE RESTRICT,
    CONSTRAINT github_pull_requests_state_ck
        CHECK (lifecycle_state IN ('open', 'closed', 'merged')),
    CONSTRAINT github_pull_requests_pr_ck CHECK (pull_request_number > 0),
    CONSTRAINT github_pull_requests_head_ck CHECK (
        length(head_sha) IN (40, 64) AND head_sha ~ '^[0-9A-Fa-f]+$'
    )
);

CREATE INDEX github_pull_requests_state_updated_idx
    ON github_pull_requests(lifecycle_state, github_updated_at DESC);

-- Existing analyzed deliveries predate lifecycle tracking and were necessarily
-- open when received. A later closed webhook will update this projection.
INSERT INTO github_pull_request_lifecycle_events (
    delivery_id, repository_owner, repository_name, pull_request_number,
    action, lifecycle_state, title, pull_request_url, head_sha,
    github_updated_at, payload_sha256, received_at
)
SELECT delivery_id,
       repository_owner,
       repository_name,
       pull_request_number,
       action,
       'open',
       COALESCE(pull_request_title, 'Pull request #' || pull_request_number),
       COALESCE(
           pull_request_url,
           'https://github.com/' || repository_owner || '/' || repository_name
               || '/pull/' || pull_request_number
       ),
       head_sha,
       received_at,
       payload_sha256,
       received_at
FROM github_webhook_deliveries;

INSERT INTO github_pull_requests (
    repository_owner, repository_name, pull_request_number, title,
    pull_request_url, lifecycle_state, head_sha, github_updated_at,
    last_delivery_id, created_at, updated_at
)
SELECT DISTINCT ON (repository_owner, repository_name, pull_request_number)
       repository_owner,
       repository_name,
       pull_request_number,
       title,
       pull_request_url,
       lifecycle_state,
       head_sha,
       github_updated_at,
       delivery_id,
       received_at,
       received_at
FROM github_pull_request_lifecycle_events
ORDER BY repository_owner, repository_name, pull_request_number,
         github_updated_at DESC, received_at DESC;
