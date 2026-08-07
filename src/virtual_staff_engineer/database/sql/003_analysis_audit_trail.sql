-- Phase 2 analysis inputs, retrieval provenance, and model-decision audit trail.

ALTER TABLE analysis_runs
    ALTER COLUMN commit_id DROP NOT NULL,
    ADD COLUMN input_type VARCHAR(30),
    ADD COLUMN source_path VARCHAR(512),
    ADD COLUMN input_content TEXT,
    ADD COLUMN input_checksum VARCHAR(64);

ALTER TABLE analysis_runs
    DROP CONSTRAINT analysis_runs_status_ck;

ALTER TABLE analysis_runs
    ADD CONSTRAINT analysis_runs_status_ck
        CHECK (
            status IN (
                'queued',
                'analyzing',
                'completed_clean',
                'review_required',
                'inconclusive',
                'failed'
            )
        ),
    ADD CONSTRAINT analysis_runs_input_ck
        CHECK (
            (
                input_type IS NULL
                AND input_content IS NULL
                AND input_checksum IS NULL
            )
            OR
            (
                input_type IN ('code_diff', 'design_document')
                AND input_content IS NOT NULL
                AND btrim(input_content) <> ''
                AND input_checksum ~ '^[0-9a-f]{64}$'
            )
        );

CREATE TABLE analysis_run_queries (
    analysis_query_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_run_id UUID NOT NULL,
    query_sequence INTEGER NOT NULL,
    query_text TEXT NOT NULL,
    purpose TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analysis_run_queries_run_fk
        FOREIGN KEY (analysis_run_id)
        REFERENCES analysis_runs(analysis_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT analysis_run_queries_sequence_uq
        UNIQUE (analysis_run_id, query_sequence),
    CONSTRAINT analysis_run_queries_text_uq
        UNIQUE (analysis_run_id, query_text),
    CONSTRAINT analysis_run_queries_sequence_positive_ck
        CHECK (query_sequence > 0),
    CONSTRAINT analysis_run_queries_text_nonempty_ck
        CHECK (btrim(query_text) <> ''),
    CONSTRAINT analysis_run_queries_purpose_nonempty_ck
        CHECK (btrim(purpose) <> '')
);

CREATE TABLE analysis_retrieval_evidence (
    analysis_query_id UUID NOT NULL,
    playbook_chunk_id UUID NOT NULL,
    rank_position INTEGER NOT NULL,
    retrieval_score NUMERIC NOT NULL,
    semantic_rank INTEGER,
    lexical_rank INTEGER,
    rule_snapshot TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analysis_retrieval_evidence_pk
        PRIMARY KEY (analysis_query_id, playbook_chunk_id),
    CONSTRAINT analysis_retrieval_evidence_query_fk
        FOREIGN KEY (analysis_query_id)
        REFERENCES analysis_run_queries(analysis_query_id)
        ON DELETE RESTRICT,
    CONSTRAINT analysis_retrieval_evidence_chunk_fk
        FOREIGN KEY (playbook_chunk_id)
        REFERENCES playbook_chunks(playbook_chunk_id)
        ON DELETE RESTRICT,
    CONSTRAINT analysis_retrieval_evidence_rank_ck
        CHECK (
            rank_position > 0
            AND (semantic_rank IS NULL OR semantic_rank > 0)
            AND (lexical_rank IS NULL OR lexical_rank > 0)
        ),
    CONSTRAINT analysis_retrieval_evidence_score_ck
        CHECK (retrieval_score >= 0),
    CONSTRAINT analysis_retrieval_evidence_snapshot_nonempty_ck
        CHECK (btrim(rule_snapshot) <> '')
);

CREATE TABLE analysis_finding_reviews (
    analysis_finding_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_run_id UUID NOT NULL,
    finding_index INTEGER NOT NULL,
    playbook_chunk_id UUID NOT NULL,
    rule_key VARCHAR(100) NOT NULL,
    source_path VARCHAR(512) NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    input_excerpt TEXT NOT NULL,
    explanation TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    confidence NUMERIC(5, 4) NOT NULL,
    verdict VARCHAR(30) NOT NULL,
    evaluator_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analysis_finding_reviews_run_fk
        FOREIGN KEY (analysis_run_id)
        REFERENCES analysis_runs(analysis_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT analysis_finding_reviews_chunk_fk
        FOREIGN KEY (playbook_chunk_id)
        REFERENCES playbook_chunks(playbook_chunk_id)
        ON DELETE RESTRICT,
    CONSTRAINT analysis_finding_reviews_run_index_uq
        UNIQUE (analysis_run_id, finding_index),
    CONSTRAINT analysis_finding_reviews_index_ck
        CHECK (finding_index >= 0),
    CONSTRAINT analysis_finding_reviews_line_range_ck
        CHECK (start_line > 0 AND end_line >= start_line),
    CONSTRAINT analysis_finding_reviews_severity_ck
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT analysis_finding_reviews_confidence_ck
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT analysis_finding_reviews_verdict_ck
        CHECK (verdict IN ('supported', 'unsupported', 'undecided')),
    CONSTRAINT analysis_finding_reviews_reason_ck
        CHECK (
            (verdict = 'undecided' AND evaluator_reason IS NULL)
            OR
            (
                verdict <> 'undecided'
                AND evaluator_reason IS NOT NULL
                AND btrim(evaluator_reason) <> ''
            )
        )
);

CREATE TABLE analysis_finding_rejections (
    rejection_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_run_id UUID NOT NULL,
    finding_index INTEGER NOT NULL,
    rejection_code VARCHAR(100) NOT NULL,
    rejection_reason TEXT NOT NULL,
    cited_playbook_chunk_id VARCHAR(255) NOT NULL,
    rule_key VARCHAR(100) NOT NULL,
    source_path VARCHAR(512) NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    input_excerpt TEXT NOT NULL,
    explanation TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    confidence NUMERIC(5, 4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT analysis_finding_rejections_run_fk
        FOREIGN KEY (analysis_run_id)
        REFERENCES analysis_runs(analysis_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT analysis_finding_rejections_index_ck
        CHECK (finding_index >= 0),
    CONSTRAINT analysis_finding_rejections_line_range_ck
        CHECK (start_line > 0 AND end_line >= start_line),
    CONSTRAINT analysis_finding_rejections_severity_ck
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    CONSTRAINT analysis_finding_rejections_confidence_ck
        CHECK (confidence >= 0 AND confidence <= 1),
    CONSTRAINT analysis_finding_rejections_text_ck
        CHECK (
            btrim(rejection_code) <> ''
            AND btrim(rejection_reason) <> ''
            AND btrim(cited_playbook_chunk_id) <> ''
        )
);

ALTER TABLE violations
    ADD COLUMN analysis_finding_id UUID,
    ADD COLUMN input_excerpt TEXT;

UPDATE violations
SET input_excerpt = '[legacy input unavailable]'
WHERE input_excerpt IS NULL;

ALTER TABLE violations
    ALTER COLUMN input_excerpt SET NOT NULL,
    ADD CONSTRAINT violations_analysis_finding_fk
        FOREIGN KEY (analysis_finding_id)
        REFERENCES analysis_finding_reviews(analysis_finding_id)
        ON DELETE RESTRICT,
    ADD CONSTRAINT violations_analysis_finding_uq
        UNIQUE (analysis_finding_id),
    ADD CONSTRAINT violations_input_excerpt_nonempty_ck
        CHECK (btrim(input_excerpt) <> '');

CREATE INDEX analysis_run_queries_run_id_idx
    ON analysis_run_queries (analysis_run_id);

CREATE INDEX analysis_retrieval_evidence_chunk_id_idx
    ON analysis_retrieval_evidence (playbook_chunk_id);

CREATE INDEX analysis_finding_reviews_run_verdict_idx
    ON analysis_finding_reviews (analysis_run_id, verdict);

CREATE INDEX analysis_finding_rejections_run_code_idx
    ON analysis_finding_rejections (analysis_run_id, rejection_code);
