-- Durable, minimal webhook receipt metadata for restart-safe delivery deduplication.

CREATE TABLE github_webhook_deliveries (
    delivery_id VARCHAR(100) PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL,
    action VARCHAR(100) NOT NULL,
    repository_owner VARCHAR(255) NOT NULL,
    repository_name VARCHAR(255) NOT NULL,
    installation_id BIGINT NOT NULL,
    pull_request_number INTEGER NOT NULL,
    head_sha VARCHAR(64) NOT NULL,
    payload_sha256 VARCHAR(64) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT github_webhook_deliveries_delivery_id_text_ck
        CHECK (btrim(delivery_id) <> ''),
    CONSTRAINT github_webhook_deliveries_event_ck
        CHECK (event_name = 'pull_request'),
    CONSTRAINT github_webhook_deliveries_action_ck
        CHECK (action IN ('opened', 'reopened', 'synchronize', 'ready_for_review')),
    CONSTRAINT github_webhook_deliveries_owner_text_ck
        CHECK (btrim(repository_owner) <> ''),
    CONSTRAINT github_webhook_deliveries_repository_text_ck
        CHECK (btrim(repository_name) <> ''),
    CONSTRAINT github_webhook_deliveries_installation_positive_ck
        CHECK (installation_id > 0),
    CONSTRAINT github_webhook_deliveries_pr_positive_ck
        CHECK (pull_request_number > 0),
    CONSTRAINT github_webhook_deliveries_head_sha_ck
        CHECK (
            length(head_sha) IN (40, 64)
            AND head_sha ~ '^[0-9A-Fa-f]+$'
        ),
    CONSTRAINT github_webhook_deliveries_payload_sha_ck
        CHECK (
            length(payload_sha256) = 64
            AND payload_sha256 ~ '^[0-9A-Fa-f]+$'
        )
);

CREATE INDEX github_webhook_deliveries_repository_pr_idx
    ON github_webhook_deliveries (
        repository_owner,
        repository_name,
        pull_request_number,
        received_at DESC
    );
