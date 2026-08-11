-- Ensure the validation evidence pinned by human approval cannot be rewritten.

CREATE OR REPLACE FUNCTION prevent_patch_proposal_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'persisted remediation evidence is immutable'
        USING ERRCODE = 'check_violation';
END;
$$;

CREATE TRIGGER patch_validation_runs_immutable_update
BEFORE UPDATE ON patch_validation_runs
FOR EACH ROW
EXECUTE FUNCTION prevent_patch_proposal_update();

CREATE TRIGGER patch_validation_checks_immutable_update
BEFORE UPDATE ON patch_validation_checks
FOR EACH ROW
EXECUTE FUNCTION prevent_patch_proposal_update();
