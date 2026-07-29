-- One-time baseline migration from the disposable prototype schema.
-- db_init/init_db.py records this migration, so these DROP statements are not
-- executed again after the migration succeeds.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP TABLE IF EXISTS remediation_action_violations;
DROP TABLE IF EXISTS remediation_actions;
DROP TABLE IF EXISTS violation_evidence;
DROP TABLE IF EXISTS violations;
DROP TABLE IF EXISTS analysis_run_playbook_versions;
DROP TABLE IF EXISTS analysis_runs;
DROP TABLE IF EXISTS commits;
DROP TABLE IF EXISTS repositories;
DROP TABLE IF EXISTS rule_violations;
DROP TABLE IF EXISTS scanned_commits;
DROP TABLE IF EXISTS engineering_playbooks;
DROP TABLE IF EXISTS playbook_chunks;
DROP TABLE IF EXISTS playbook_versions;
DROP TABLE IF EXISTS playbook_documents;

CREATE TABLE repositories (
    repository_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    github_url TEXT NOT NULL,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT repositories_owner_name_uq UNIQUE (owner, name)
);

CREATE TABLE commits (
    commit_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repository_id UUID NOT NULL,
    commit_sha VARCHAR(64) NOT NULL,
    author VARCHAR(255) NOT NULL,
    message TEXT,
    committed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT commits_repository_fk
        FOREIGN KEY (repository_id)
        REFERENCES repositories(repository_id)
        ON DELETE RESTRICT,
    CONSTRAINT commits_repository_sha_uq
        UNIQUE (repository_id, commit_sha),
    CONSTRAINT commits_sha_format_ck
        CHECK (commit_sha ~ '^[0-9a-fA-F]{40}([0-9a-fA-F]{24})?$')
);

CREATE TABLE playbook_documents (
    document_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    archived_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT playbook_documents_filename_uq UNIQUE (filename)
);

CREATE TABLE playbook_versions (
    playbook_version_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL,
    version INTEGER NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    embedding_model VARCHAR(255) NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT playbook_versions_document_fk
        FOREIGN KEY (document_id)
        REFERENCES playbook_documents(document_id)
        ON DELETE RESTRICT,
    CONSTRAINT playbook_versions_document_version_uq
        UNIQUE (document_id, version),
    CONSTRAINT playbook_versions_document_checksum_uq
        UNIQUE (document_id, checksum),
    CONSTRAINT playbook_versions_version_positive_ck
        CHECK (version > 0),
    CONSTRAINT playbook_versions_checksum_format_ck
        CHECK (checksum ~ '^[0-9a-f]{64}$'),
    CONSTRAINT playbook_versions_embedding_dimension_positive_ck
        CHECK (embedding_dimension > 0)
);

CREATE TABLE playbook_chunks (
    playbook_chunk_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    playbook_version_id UUID NOT NULL,
    rule_key VARCHAR(100) NOT NULL,
    chunk_index INTEGER NOT NULL,
    section VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT playbook_chunks_version_fk
        FOREIGN KEY (playbook_version_id)
        REFERENCES playbook_versions(playbook_version_id)
        ON DELETE RESTRICT,
    CONSTRAINT playbook_chunks_version_rule_index_uq
        UNIQUE (playbook_version_id, rule_key, chunk_index),
    CONSTRAINT playbook_chunks_index_nonnegative_ck
        CHECK (chunk_index >= 0),
    CONSTRAINT playbook_chunks_rule_key_nonempty_ck
        CHECK (btrim(rule_key) <> ''),
    CONSTRAINT playbook_chunks_section_nonempty_ck
        CHECK (btrim(section) <> ''),
    CONSTRAINT playbook_chunks_content_nonempty_ck
        CHECK (btrim(content) <> '')
);

CREATE TABLE analysis_runs (
    analysis_run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    commit_id UUID NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    model_name VARCHAR(255) NOT NULL,
    workflow_version VARCHAR(100) NOT NULL,
    prompt_version VARCHAR(100) NOT NULL,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    tool_call_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analysis_runs_commit_fk
        FOREIGN KEY (commit_id)
        REFERENCES commits(commit_id)
        ON DELETE RESTRICT,
    CONSTRAINT analysis_runs_status_ck
        CHECK (
            status IN (
                'queued',
                'analyzing',
                'completed_clean',
                'review_required',
                'failed'
            )
        ),
    CONSTRAINT analysis_runs_token_counts_ck
        CHECK (
            input_tokens >= 0
            AND output_tokens >= 0
            AND tool_call_count >= 0
        ),
    CONSTRAINT analysis_runs_time_order_ck
        CHECK (
            completed_at IS NULL
            OR started_at IS NULL
            OR completed_at >= started_at
        )
);

CREATE TABLE analysis_run_playbook_versions (
    analysis_run_id UUID NOT NULL,
    playbook_version_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analysis_run_playbook_versions_pk
        PRIMARY KEY (analysis_run_id, playbook_version_id),
    CONSTRAINT analysis_run_playbook_versions_run_fk
        FOREIGN KEY (analysis_run_id)
        REFERENCES analysis_runs(analysis_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT analysis_run_playbook_versions_version_fk
        FOREIGN KEY (playbook_version_id)
        REFERENCES playbook_versions(playbook_version_id)
        ON DELETE RESTRICT
);

CREATE TABLE violations (
    violation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_run_id UUID NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    severity VARCHAR(20) NOT NULL,
    explanation TEXT NOT NULL,
    confidence NUMERIC(5, 4) NOT NULL,
    suggested_patch TEXT,
    validation_status VARCHAR(30) NOT NULL DEFAULT 'not_validated',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT violations_analysis_run_fk
        FOREIGN KEY (analysis_run_id)
        REFERENCES analysis_runs(analysis_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT violations_line_range_ck
        CHECK (start_line > 0 AND end_line >= start_line),
    CONSTRAINT violations_severity_ck
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT violations_confidence_ck
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT violations_validation_status_ck
        CHECK (
            validation_status IN (
                'not_validated',
                'validating',
                'valid',
                'invalid',
                'failed'
            )
        ),
    CONSTRAINT violations_explanation_nonempty_ck
        CHECK (btrim(explanation) <> '')
);

CREATE TABLE violation_evidence (
    evidence_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    violation_id UUID NOT NULL,
    playbook_chunk_id UUID NOT NULL,
    rule_snapshot TEXT NOT NULL,
    retrieval_score NUMERIC,
    rank_position INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT violation_evidence_violation_fk
        FOREIGN KEY (violation_id)
        REFERENCES violations(violation_id)
        ON DELETE RESTRICT,
    CONSTRAINT violation_evidence_chunk_fk
        FOREIGN KEY (playbook_chunk_id)
        REFERENCES playbook_chunks(playbook_chunk_id)
        ON DELETE RESTRICT,
    CONSTRAINT violation_evidence_violation_chunk_uq
        UNIQUE (violation_id, playbook_chunk_id),
    CONSTRAINT violation_evidence_rank_positive_ck
        CHECK (rank_position IS NULL OR rank_position > 0),
    CONSTRAINT violation_evidence_snapshot_nonempty_ck
        CHECK (btrim(rule_snapshot) <> '')
);

CREATE TABLE remediation_actions (
    remediation_action_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_run_id UUID NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'proposed',
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    branch_name VARCHAR(255),
    pr_number INTEGER,
    pr_url TEXT,
    idempotency_key VARCHAR(255) NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT remediation_actions_analysis_run_fk
        FOREIGN KEY (analysis_run_id)
        REFERENCES analysis_runs(analysis_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT remediation_actions_idempotency_key_uq
        UNIQUE (idempotency_key),
    CONSTRAINT remediation_actions_status_ck
        CHECK (
            status IN (
                'proposed',
                'approved',
                'rejected',
                'validating',
                'applying',
                'pr_created',
                'failed'
            )
        ),
    CONSTRAINT remediation_actions_pr_number_positive_ck
        CHECK (pr_number IS NULL OR pr_number > 0),
    CONSTRAINT remediation_actions_approval_ck
        CHECK (
            (approved_at IS NULL AND approved_by IS NULL)
            OR (approved_at IS NOT NULL AND approved_by IS NOT NULL)
        ),
    CONSTRAINT remediation_actions_decision_ck
        CHECK (approved_at IS NULL OR rejected_at IS NULL)
);

CREATE TABLE remediation_action_violations (
    remediation_action_id UUID NOT NULL,
    violation_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT remediation_action_violations_pk
        PRIMARY KEY (remediation_action_id, violation_id),
    CONSTRAINT remediation_action_violations_action_fk
        FOREIGN KEY (remediation_action_id)
        REFERENCES remediation_actions(remediation_action_id)
        ON DELETE RESTRICT,
    CONSTRAINT remediation_action_violations_violation_fk
        FOREIGN KEY (violation_id)
        REFERENCES violations(violation_id)
        ON DELETE RESTRICT
);

CREATE INDEX playbook_chunks_hnsw_cos_idx
    ON playbook_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX playbook_chunks_content_fts_idx
    ON playbook_chunks
    USING gin (
        to_tsvector(
            'english',
            rule_key || ' ' || section || ' ' || content
        )
    );

CREATE INDEX playbook_chunks_content_trgm_idx
    ON playbook_chunks
    USING gin (content gin_trgm_ops);

CREATE INDEX commits_repository_id_idx
    ON commits (repository_id);

CREATE INDEX playbook_versions_document_id_idx
    ON playbook_versions (document_id);

CREATE INDEX playbook_chunks_version_id_idx
    ON playbook_chunks (playbook_version_id);

CREATE INDEX analysis_runs_commit_status_idx
    ON analysis_runs (commit_id, status);

CREATE INDEX analysis_run_playbook_versions_version_idx
    ON analysis_run_playbook_versions (playbook_version_id);

CREATE INDEX violations_analysis_run_id_idx
    ON violations (analysis_run_id);

CREATE INDEX violation_evidence_chunk_id_idx
    ON violation_evidence (playbook_chunk_id);

CREATE INDEX remediation_actions_analysis_run_status_idx
    ON remediation_actions (analysis_run_id, status);

CREATE INDEX remediation_action_violations_violation_idx
    ON remediation_action_violations (violation_id);

CREATE INDEX repositories_active_idx
    ON repositories (owner, name)
    WHERE archived_at IS NULL;

CREATE INDEX playbook_documents_active_idx
    ON playbook_documents (category, filename)
    WHERE archived_at IS NULL;
