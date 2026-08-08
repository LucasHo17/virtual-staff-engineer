-- Preserve why an analysis could not reach a supported or clean conclusion.

ALTER TABLE analysis_runs
    ADD COLUMN inconclusive_reason TEXT;

UPDATE analysis_runs
SET inconclusive_reason = '[legacy reason unavailable]'
WHERE status = 'inconclusive';

ALTER TABLE analysis_runs
    ADD CONSTRAINT analysis_runs_inconclusive_reason_ck
        CHECK (
            (
                status = 'inconclusive'
                AND inconclusive_reason IS NOT NULL
                AND btrim(inconclusive_reason) <> ''
            )
            OR
            (
                status <> 'inconclusive'
                AND inconclusive_reason IS NULL
            )
        );
