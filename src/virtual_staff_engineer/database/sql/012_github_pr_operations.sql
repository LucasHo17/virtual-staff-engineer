-- Authenticated approval provenance and durable, retry-safe PR operations.

ALTER TABLE remediation_approval_decisions
    ADD COLUMN authentication_method VARCHAR(100) NOT NULL
        DEFAULT 'development_cli',
    ADD COLUMN authenticated_subject VARCHAR(255),
    ADD COLUMN authentication_issuer VARCHAR(255),
    ADD CONSTRAINT remediation_approval_decisions_auth_ck CHECK (
        (
            authentication_method = 'development_cli'
            AND authenticated_subject IS NULL
            AND authentication_issuer IS NULL
        )
        OR (
            authentication_method <> 'development_cli'
            AND authenticated_subject IS NOT NULL
            AND authentication_issuer IS NOT NULL
            AND btrim(authenticated_subject) <> ''
            AND btrim(authentication_issuer) <> ''
        )
    );

CREATE TABLE github_pr_operations (
    github_pr_operation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_job_id UUID NOT NULL UNIQUE,
    remediation_action_id UUID NOT NULL UNIQUE,
    repository_owner VARCHAR(255) NOT NULL,
    repository_name VARCHAR(255) NOT NULL,
    base_commit_sha VARCHAR(64) NOT NULL,
    head_branch VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    commit_sha VARCHAR(64),
    pr_number INTEGER,
    pr_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT github_pr_operations_job_fk FOREIGN KEY (workflow_job_id)
        REFERENCES workflow_jobs(workflow_job_id) ON DELETE RESTRICT,
    CONSTRAINT github_pr_operations_action_fk FOREIGN KEY (remediation_action_id)
        REFERENCES remediation_actions(remediation_action_id) ON DELETE RESTRICT,
    CONSTRAINT github_pr_operations_status_ck
        CHECK (status IN ('pending', 'completed')),
    CONSTRAINT github_pr_operations_attempt_positive_ck CHECK (attempt_count >= 0),
    CONSTRAINT github_pr_operations_pr_positive_ck CHECK (pr_number IS NULL OR pr_number > 0),
    CONSTRAINT github_pr_operations_complete_ck CHECK (
        status <> 'completed'
        OR (commit_sha IS NOT NULL AND pr_number IS NOT NULL AND pr_url IS NOT NULL)
    )
);

CREATE INDEX github_pr_operations_status_idx
    ON github_pr_operations(status, updated_at);
