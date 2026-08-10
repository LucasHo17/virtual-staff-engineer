-- Phase 3A durable workflow envelope, state-machine invariants, and audit log.

CREATE TABLE workflow_jobs (
    workflow_job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    analysis_run_id UUID NOT NULL,
    remediation_action_id UUID,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    idempotency_key VARCHAR(255) NOT NULL,
    priority SMALLINT NOT NULL DEFAULT 100,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checkpoint VARCHAR(50) NOT NULL DEFAULT 'submitted',
    lease_owner VARCHAR(255),
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    failure_code VARCHAR(100),
    failure_disposition VARCHAR(20),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT workflow_jobs_analysis_run_fk
        FOREIGN KEY (analysis_run_id)
        REFERENCES analysis_runs(analysis_run_id)
        ON DELETE RESTRICT,
    CONSTRAINT workflow_jobs_remediation_action_fk
        FOREIGN KEY (remediation_action_id)
        REFERENCES remediation_actions(remediation_action_id)
        ON DELETE RESTRICT,
    CONSTRAINT workflow_jobs_analysis_run_uq UNIQUE (analysis_run_id),
    CONSTRAINT workflow_jobs_remediation_action_uq
        UNIQUE (remediation_action_id),
    CONSTRAINT workflow_jobs_idempotency_key_uq UNIQUE (idempotency_key),
    CONSTRAINT workflow_jobs_status_ck
        CHECK (
            status IN (
                'queued',
                'analyzing',
                'generating_patch',
                'validating_patch',
                'awaiting_approval',
                'approved',
                'creating_pr',
                'retry_scheduled',
                'completed',
                'failed',
                'rejected',
                'cancelled'
            )
        ),
    CONSTRAINT workflow_jobs_idempotency_key_nonempty_ck
        CHECK (btrim(idempotency_key) <> ''),
    CONSTRAINT workflow_jobs_attempts_ck
        CHECK (
            attempt_count >= 0
            AND max_attempts > 0
            AND attempt_count <= max_attempts
        ),
    CONSTRAINT workflow_jobs_priority_ck
        CHECK (priority >= 0 AND priority <= 1000),
    CONSTRAINT workflow_jobs_checkpoint_ck
        CHECK (
            checkpoint IN (
                'submitted',
                'analysis_completed',
                'patch_generated',
                'patch_validated',
                'approval_recorded',
                'pr_created'
            )
        ),
    CONSTRAINT workflow_jobs_lease_ck
        CHECK (
            (
                status IN (
                    'analyzing',
                    'generating_patch',
                    'validating_patch',
                    'creating_pr'
                )
                AND lease_owner IS NOT NULL
                AND btrim(lease_owner) <> ''
                AND lease_token IS NOT NULL
                AND lease_expires_at IS NOT NULL
                AND heartbeat_at IS NOT NULL
                AND lease_expires_at > heartbeat_at
            )
            OR
            (
                status NOT IN (
                    'analyzing',
                    'generating_patch',
                    'validating_patch',
                    'creating_pr'
                )
                AND lease_owner IS NULL
                AND lease_token IS NULL
                AND lease_expires_at IS NULL
                AND heartbeat_at IS NULL
            )
        ),
    CONSTRAINT workflow_jobs_failure_ck
        CHECK (
            (
                status = 'retry_scheduled'
                AND failure_code IS NOT NULL
                AND btrim(failure_code) <> ''
                AND failure_disposition = 'retryable'
                AND error_message IS NOT NULL
                AND btrim(error_message) <> ''
            )
            OR
            (
                status = 'failed'
                AND failure_code IS NOT NULL
                AND btrim(failure_code) <> ''
                AND failure_disposition IN ('retryable', 'permanent')
                AND error_message IS NOT NULL
                AND btrim(error_message) <> ''
            )
            OR
            (
                status NOT IN ('retry_scheduled', 'failed')
                AND failure_code IS NULL
                AND failure_disposition IS NULL
                AND error_message IS NULL
            )
        ),
    CONSTRAINT workflow_jobs_terminal_time_ck
        CHECK (
            (
                status IN ('completed', 'failed', 'rejected', 'cancelled')
                AND completed_at IS NOT NULL
            )
            OR
            (
                status NOT IN ('completed', 'failed', 'rejected', 'cancelled')
                AND completed_at IS NULL
            )
        ),
    CONSTRAINT workflow_jobs_time_order_ck
        CHECK (
            (started_at IS NULL OR started_at >= created_at)
            AND (completed_at IS NULL OR completed_at >= created_at)
            AND (
                completed_at IS NULL
                OR started_at IS NULL
                OR completed_at >= started_at
            )
        )
);

CREATE TABLE workflow_job_transitions (
    workflow_transition_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_job_id UUID NOT NULL,
    transition_sequence INTEGER NOT NULL,
    from_status VARCHAR(50),
    to_status VARCHAR(50) NOT NULL,
    attempt_count INTEGER NOT NULL,
    checkpoint VARCHAR(50) NOT NULL,
    failure_code VARCHAR(100),
    failure_disposition VARCHAR(20),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT workflow_job_transitions_job_fk
        FOREIGN KEY (workflow_job_id)
        REFERENCES workflow_jobs(workflow_job_id)
        ON DELETE RESTRICT,
    CONSTRAINT workflow_job_transitions_sequence_uq
        UNIQUE (workflow_job_id, transition_sequence),
    CONSTRAINT workflow_job_transitions_sequence_positive_ck
        CHECK (transition_sequence > 0),
    CONSTRAINT workflow_job_transitions_attempt_nonnegative_ck
        CHECK (attempt_count >= 0)
);

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
            WHEN 'queued' THEN NEW.status IN ('analyzing', 'cancelled')
            WHEN 'analyzing' THEN NEW.status IN (
                'generating_patch', 'completed', 'retry_scheduled',
                'failed', 'cancelled'
            )
            WHEN 'generating_patch' THEN NEW.status IN (
                'validating_patch', 'retry_scheduled', 'failed', 'cancelled'
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

CREATE TRIGGER workflow_jobs_lifecycle_before_write
BEFORE INSERT OR UPDATE ON workflow_jobs
FOR EACH ROW
EXECUTE FUNCTION enforce_workflow_job_lifecycle();

CREATE OR REPLACE FUNCTION audit_workflow_job_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    next_sequence INTEGER;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.status IS NOT DISTINCT FROM OLD.status THEN
        RETURN NEW;
    END IF;
    SELECT COALESCE(MAX(transition_sequence), 0) + 1
    INTO next_sequence
    FROM workflow_job_transitions
    WHERE workflow_job_id = NEW.workflow_job_id;

    INSERT INTO workflow_job_transitions (
        workflow_job_id,
        transition_sequence,
        from_status,
        to_status,
        attempt_count,
        checkpoint,
        failure_code,
        failure_disposition,
        error_message
    )
    VALUES (
        NEW.workflow_job_id,
        next_sequence,
        CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.status END,
        NEW.status,
        NEW.attempt_count,
        NEW.checkpoint,
        NEW.failure_code,
        NEW.failure_disposition,
        NEW.error_message
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER workflow_jobs_transition_after_write
AFTER INSERT OR UPDATE ON workflow_jobs
FOR EACH ROW
EXECUTE FUNCTION audit_workflow_job_transition();

CREATE INDEX workflow_jobs_claim_idx
    ON workflow_jobs (priority DESC, available_at, created_at)
    WHERE status = 'queued';

CREATE INDEX workflow_jobs_retry_schedule_idx
    ON workflow_jobs (available_at, created_at)
    WHERE status = 'retry_scheduled';

CREATE INDEX workflow_jobs_expired_lease_idx
    ON workflow_jobs (lease_expires_at)
    WHERE status IN (
        'analyzing', 'generating_patch', 'validating_patch', 'creating_pr'
    );

CREATE INDEX workflow_job_transitions_job_created_idx
    ON workflow_job_transitions (workflow_job_id, created_at);
