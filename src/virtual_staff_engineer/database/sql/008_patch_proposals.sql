-- Phase 3D immutable patch proposals and safe validation-stage handoff.

CREATE TABLE patch_proposals (
    patch_proposal_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    remediation_action_id UUID NOT NULL,
    source_path VARCHAR(512) NOT NULL,
    source_revision VARCHAR(255),
    original_content TEXT NOT NULL,
    original_sha256 VARCHAR(64) NOT NULL,
    unified_diff TEXT NOT NULL,
    explanation TEXT NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    prompt_version VARCHAR(100) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT patch_proposals_action_fk
        FOREIGN KEY (remediation_action_id)
        REFERENCES remediation_actions(remediation_action_id)
        ON DELETE RESTRICT,
    CONSTRAINT patch_proposals_action_uq UNIQUE (remediation_action_id),
    CONSTRAINT patch_proposals_source_path_nonempty_ck
        CHECK (btrim(source_path) <> ''),
    CONSTRAINT patch_proposals_original_sha256_ck
        CHECK (original_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT patch_proposals_diff_nonempty_ck
        CHECK (btrim(unified_diff) <> ''),
    CONSTRAINT patch_proposals_explanation_nonempty_ck
        CHECK (btrim(explanation) <> ''),
    CONSTRAINT patch_proposals_model_nonempty_ck
        CHECK (btrim(model_name) <> '' AND btrim(prompt_version) <> '')
);

CREATE TABLE patch_proposal_rules (
    patch_proposal_id UUID NOT NULL,
    playbook_chunk_id UUID NOT NULL,
    rule_key VARCHAR(100) NOT NULL,
    rule_snapshot TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT patch_proposal_rules_pk
        PRIMARY KEY (patch_proposal_id, playbook_chunk_id),
    CONSTRAINT patch_proposal_rules_proposal_fk
        FOREIGN KEY (patch_proposal_id)
        REFERENCES patch_proposals(patch_proposal_id)
        ON DELETE RESTRICT,
    CONSTRAINT patch_proposal_rules_chunk_fk
        FOREIGN KEY (playbook_chunk_id)
        REFERENCES playbook_chunks(playbook_chunk_id)
        ON DELETE RESTRICT,
    CONSTRAINT patch_proposal_rules_text_ck
        CHECK (btrim(rule_key) <> '' AND btrim(rule_snapshot) <> '')
);

CREATE INDEX patch_proposal_rules_chunk_idx
    ON patch_proposal_rules (playbook_chunk_id);

CREATE OR REPLACE FUNCTION enforce_workflow_job_lifecycle()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    transition_allowed BOOLEAN;
    old_checkpoint_order INTEGER;
    new_checkpoint_order INTEGER;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'queued' THEN
            RAISE EXCEPTION 'workflow jobs must be inserted in queued state'
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.resume_state <> 'analyzing' THEN
            RAISE EXCEPTION 'new workflow jobs must begin at analyzing'
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.analysis_run_id <> OLD.analysis_run_id
       OR NEW.idempotency_key <> OLD.idempotency_key THEN
        RAISE EXCEPTION 'workflow job identity is immutable'
            USING ERRCODE = 'check_violation';
    END IF;

    old_checkpoint_order := CASE OLD.checkpoint
        WHEN 'submitted' THEN 1
        WHEN 'analysis_completed' THEN 2
        WHEN 'patch_generated' THEN 3
        WHEN 'patch_validated' THEN 4
        WHEN 'approval_recorded' THEN 5
        WHEN 'pr_created' THEN 6
    END;
    new_checkpoint_order := CASE NEW.checkpoint
        WHEN 'submitted' THEN 1
        WHEN 'analysis_completed' THEN 2
        WHEN 'patch_generated' THEN 3
        WHEN 'patch_validated' THEN 4
        WHEN 'approval_recorded' THEN 5
        WHEN 'pr_created' THEN 6
    END;
    IF new_checkpoint_order < old_checkpoint_order THEN
        RAISE EXCEPTION 'workflow job checkpoint cannot regress'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status IS DISTINCT FROM OLD.status THEN
        transition_allowed := CASE OLD.status
            WHEN 'queued' THEN NEW.status IN (
                'analyzing', 'generating_patch', 'validating_patch',
                'creating_pr', 'cancelled'
            )
            WHEN 'analyzing' THEN NEW.status IN (
                'queued', 'generating_patch', 'completed', 'retry_scheduled',
                'failed', 'cancelled'
            )
            WHEN 'generating_patch' THEN NEW.status IN (
                'queued', 'validating_patch', 'retry_scheduled', 'failed',
                'cancelled'
            )
            WHEN 'validating_patch' THEN NEW.status IN (
                'awaiting_approval', 'retry_scheduled', 'failed', 'cancelled'
            )
            WHEN 'awaiting_approval' THEN NEW.status IN (
                'approved', 'rejected', 'cancelled'
            )
            WHEN 'approved' THEN NEW.status IN ('creating_pr', 'cancelled')
            WHEN 'creating_pr' THEN NEW.status IN (
                'completed', 'retry_scheduled', 'failed'
            )
            WHEN 'retry_scheduled' THEN NEW.status IN (
                'queued', 'failed', 'cancelled'
            )
            ELSE FALSE
        END;
        IF NOT transition_allowed THEN
            RAISE EXCEPTION 'illegal workflow job transition: % -> %',
                OLD.status, NEW.status
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.status = 'queued'
           AND NEW.status IN (
               'analyzing', 'generating_patch', 'validating_patch', 'creating_pr'
           )
           AND NEW.status <> OLD.resume_state THEN
            RAISE EXCEPTION 'claimed workflow job must enter its resume state'
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.status = 'analyzing' AND NEW.status = 'queued' THEN
            IF NEW.checkpoint <> 'analysis_completed'
               OR NEW.resume_state <> 'generating_patch' THEN
                RAISE EXCEPTION 'analysis handoff must queue generating_patch'
                    USING ERRCODE = 'check_violation';
            END IF;
        ELSIF OLD.status = 'generating_patch' AND NEW.status = 'queued' THEN
            IF NEW.checkpoint <> 'patch_generated'
               OR NEW.resume_state <> 'validating_patch' THEN
                RAISE EXCEPTION 'patch handoff must queue validating_patch'
                    USING ERRCODE = 'check_violation';
            END IF;
        ELSIF OLD.status IN (
            'analyzing', 'generating_patch', 'validating_patch', 'creating_pr'
        ) AND NEW.status = 'retry_scheduled' THEN
            NEW.resume_state := OLD.status;
        ELSIF NEW.status IN (
            'analyzing', 'generating_patch', 'validating_patch', 'creating_pr'
        ) THEN
            NEW.resume_state := NEW.status;
        END IF;
    END IF;

    NEW.updated_at := CURRENT_TIMESTAMP;
    IF OLD.started_at IS NULL
       AND NEW.status IN (
           'analyzing', 'generating_patch', 'validating_patch', 'creating_pr'
       ) THEN
        NEW.started_at := CURRENT_TIMESTAMP;
    END IF;
    IF NEW.status IN ('completed', 'failed', 'rejected', 'cancelled')
       AND OLD.status IS DISTINCT FROM NEW.status THEN
        NEW.completed_at := CURRENT_TIMESTAMP;
    END IF;
    RETURN NEW;
END;
$$;
