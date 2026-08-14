-- Leased webhook ingestion plus immutable GitHub source snapshots and job links.

ALTER TABLE github_webhook_deliveries
    ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'received',
    ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5,
    ADD COLUMN available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN lease_owner VARCHAR(255),
    ADD COLUMN lease_token UUID,
    ADD COLUMN lease_expires_at TIMESTAMPTZ,
    ADD COLUMN failure_code VARCHAR(100),
    ADD COLUMN error_message TEXT,
    ADD COLUMN pull_request_title TEXT,
    ADD COLUMN pull_request_url TEXT,
    ADD COLUMN base_sha VARCHAR(64),
    ADD COLUMN changed_file_count INTEGER,
    ADD COLUMN analyzable_file_count INTEGER,
    ADD COLUMN skipped_file_count INTEGER,
    ADD COLUMN completed_at TIMESTAMPTZ,
    ADD CONSTRAINT github_webhook_deliveries_status_ck CHECK (
        status IN ('received', 'processing', 'retry_scheduled', 'completed', 'failed')
    ),
    ADD CONSTRAINT github_webhook_deliveries_attempt_ck CHECK (
        attempt_count >= 0 AND max_attempts > 0 AND attempt_count <= max_attempts
    ),
    ADD CONSTRAINT github_webhook_deliveries_lease_ck CHECK (
        (
            status = 'processing'
            AND lease_owner IS NOT NULL
            AND lease_token IS NOT NULL
            AND lease_expires_at IS NOT NULL
        )
        OR (
            status <> 'processing'
            AND lease_owner IS NULL
            AND lease_token IS NULL
            AND lease_expires_at IS NULL
        )
    ),
    ADD CONSTRAINT github_webhook_deliveries_completion_ck CHECK (
        (status = 'completed' AND completed_at IS NOT NULL)
        OR (status <> 'completed' AND completed_at IS NULL)
    ),
    ADD CONSTRAINT github_webhook_deliveries_snapshot_counts_ck CHECK (
        changed_file_count IS NULL
        OR (
            changed_file_count >= 0
            AND analyzable_file_count >= 0
            AND skipped_file_count >= 0
            AND changed_file_count = analyzable_file_count + skipped_file_count
        )
    );

CREATE INDEX github_webhook_deliveries_queue_idx
    ON github_webhook_deliveries(status, available_at, received_at);

CREATE TABLE github_pr_file_snapshots (
    commit_id UUID NOT NULL,
    source_path VARCHAR(1024) NOT NULL,
    blob_sha VARCHAR(64) NOT NULL,
    change_status VARCHAR(30) NOT NULL,
    source_content TEXT NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    unified_diff TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT github_pr_file_snapshots_pk PRIMARY KEY (commit_id, source_path),
    CONSTRAINT github_pr_file_snapshots_commit_fk FOREIGN KEY (commit_id)
        REFERENCES commits(commit_id) ON DELETE RESTRICT,
    CONSTRAINT github_pr_file_snapshots_path_ck CHECK (btrim(source_path) <> ''),
    CONSTRAINT github_pr_file_snapshots_blob_sha_ck CHECK (
        length(blob_sha) IN (40, 64) AND blob_sha ~ '^[0-9A-Fa-f]+$'
    ),
    CONSTRAINT github_pr_file_snapshots_status_ck CHECK (
        change_status IN ('added', 'modified', 'renamed', 'copied', 'changed', 'unchanged')
    ),
    CONSTRAINT github_pr_file_snapshots_source_sha_ck CHECK (
        length(source_sha256) = 64 AND source_sha256 ~ '^[0-9a-f]+$'
    ),
    CONSTRAINT github_pr_file_snapshots_diff_ck CHECK (btrim(unified_diff) <> '')
);

CREATE TABLE github_webhook_delivery_jobs (
    delivery_id VARCHAR(100) NOT NULL,
    workflow_job_id UUID NOT NULL,
    source_path VARCHAR(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT github_webhook_delivery_jobs_pk
        PRIMARY KEY (delivery_id, workflow_job_id),
    CONSTRAINT github_webhook_delivery_jobs_delivery_fk FOREIGN KEY (delivery_id)
        REFERENCES github_webhook_deliveries(delivery_id) ON DELETE RESTRICT,
    CONSTRAINT github_webhook_delivery_jobs_job_fk FOREIGN KEY (workflow_job_id)
        REFERENCES workflow_jobs(workflow_job_id) ON DELETE RESTRICT,
    CONSTRAINT github_webhook_delivery_jobs_path_uq UNIQUE (delivery_id, source_path),
    CONSTRAINT github_webhook_delivery_jobs_path_ck CHECK (btrim(source_path) <> '')
);
