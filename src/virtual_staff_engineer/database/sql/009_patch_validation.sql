-- Durable deterministic patch-validation results.

CREATE TABLE patch_validation_runs (
    patch_validation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    patch_proposal_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    validator_version VARCHAR(100) NOT NULL,
    changed_lines INTEGER NOT NULL,
    resulting_sha256 VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT patch_validation_runs_proposal_fk
        FOREIGN KEY (patch_proposal_id)
        REFERENCES patch_proposals(patch_proposal_id)
        ON DELETE RESTRICT,
    CONSTRAINT patch_validation_runs_proposal_uq UNIQUE (patch_proposal_id),
    CONSTRAINT patch_validation_runs_status_ck
        CHECK (status IN ('valid', 'invalid')),
    CONSTRAINT patch_validation_runs_version_nonempty_ck
        CHECK (btrim(validator_version) <> ''),
    CONSTRAINT patch_validation_runs_changed_lines_ck
        CHECK (changed_lines >= 0),
    CONSTRAINT patch_validation_runs_result_hash_ck
        CHECK (
            resulting_sha256 IS NULL
            OR resulting_sha256 ~ '^[0-9a-f]{64}$'
        ),
    CONSTRAINT patch_validation_runs_valid_result_ck
        CHECK (status <> 'valid' OR resulting_sha256 IS NOT NULL)
);

CREATE TABLE patch_validation_checks (
    patch_validation_id UUID NOT NULL,
    check_sequence INTEGER NOT NULL,
    check_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    details TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT patch_validation_checks_pk
        PRIMARY KEY (patch_validation_id, check_sequence),
    CONSTRAINT patch_validation_checks_name_uq
        UNIQUE (patch_validation_id, check_name),
    CONSTRAINT patch_validation_checks_run_fk
        FOREIGN KEY (patch_validation_id)
        REFERENCES patch_validation_runs(patch_validation_id)
        ON DELETE RESTRICT,
    CONSTRAINT patch_validation_checks_sequence_ck
        CHECK (check_sequence > 0),
    CONSTRAINT patch_validation_checks_status_ck
        CHECK (status IN ('passed', 'failed', 'skipped')),
    CONSTRAINT patch_validation_checks_text_ck
        CHECK (btrim(check_name) <> '' AND btrim(details) <> '')
);

CREATE OR REPLACE FUNCTION prevent_patch_proposal_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'persisted patch proposal provenance is immutable'
        USING ERRCODE = 'check_violation';
END;
$$;

CREATE TRIGGER patch_proposals_immutable_update
BEFORE UPDATE ON patch_proposals
FOR EACH ROW
EXECUTE FUNCTION prevent_patch_proposal_update();

CREATE TRIGGER patch_proposal_rules_immutable_update
BEFORE UPDATE ON patch_proposal_rules
FOR EACH ROW
EXECUTE FUNCTION prevent_patch_proposal_update();
