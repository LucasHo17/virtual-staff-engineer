-- Phase 3B resume target for retrying work from its last active stage.

ALTER TABLE workflow_jobs
    ADD COLUMN resume_state VARCHAR(50) NOT NULL DEFAULT 'analyzing',
    ADD CONSTRAINT workflow_jobs_resume_state_ck
        CHECK (
            resume_state IN (
                'analyzing',
                'generating_patch',
                'validating_patch',
                'creating_pr'
            )
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
        IF OLD.status = 'queued'
           AND NEW.status IN (
               'analyzing', 'generating_patch', 'validating_patch', 'creating_pr'
           )
           AND NEW.status <> OLD.resume_state THEN
            RAISE EXCEPTION 'claimed workflow job must enter its resume state'
                USING ERRCODE = 'check_violation';
        END IF;
        IF OLD.status IN (
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
