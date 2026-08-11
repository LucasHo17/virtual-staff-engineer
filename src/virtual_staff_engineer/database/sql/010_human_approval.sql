-- Immutable human decision over one exact validated patch proposal.

CREATE TABLE remediation_approval_decisions (
    approval_decision_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workflow_job_id UUID NOT NULL,
    remediation_action_id UUID NOT NULL,
    patch_proposal_id UUID NOT NULL,
    patch_validation_id UUID NOT NULL,
    decision VARCHAR(20) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    comment TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT remediation_approval_decisions_job_fk
        FOREIGN KEY (workflow_job_id)
        REFERENCES workflow_jobs(workflow_job_id)
        ON DELETE RESTRICT,
    CONSTRAINT remediation_approval_decisions_action_fk
        FOREIGN KEY (remediation_action_id)
        REFERENCES remediation_actions(remediation_action_id)
        ON DELETE RESTRICT,
    CONSTRAINT remediation_approval_decisions_proposal_fk
        FOREIGN KEY (patch_proposal_id)
        REFERENCES patch_proposals(patch_proposal_id)
        ON DELETE RESTRICT,
    CONSTRAINT remediation_approval_decisions_validation_fk
        FOREIGN KEY (patch_validation_id)
        REFERENCES patch_validation_runs(patch_validation_id)
        ON DELETE RESTRICT,
    CONSTRAINT remediation_approval_decisions_job_uq
        UNIQUE (workflow_job_id),
    CONSTRAINT remediation_approval_decisions_action_uq
        UNIQUE (remediation_action_id),
    CONSTRAINT remediation_approval_decisions_decision_ck
        CHECK (decision IN ('approved', 'rejected')),
    CONSTRAINT remediation_approval_decisions_actor_nonempty_ck
        CHECK (btrim(actor) <> ''),
    CONSTRAINT remediation_approval_decisions_comment_ck
        CHECK (comment IS NULL OR btrim(comment) <> '')
);

CREATE TRIGGER remediation_approval_decisions_immutable_update
BEFORE UPDATE ON remediation_approval_decisions
FOR EACH ROW
EXECUTE FUNCTION prevent_patch_proposal_update();
