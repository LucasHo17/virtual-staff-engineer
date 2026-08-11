import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from virtual_staff_engineer.analysis.contracts import AnalysisInput
from virtual_staff_engineer.analysis.orchestrator import AnalysisResult
from virtual_staff_engineer.analysis.repository import AnalysisRepository
from virtual_staff_engineer.database.connection import connect
from virtual_staff_engineer.jobs.lifecycle import (
    ACTIVE_JOB_STATES,
    FailureDisposition,
    JobCheckpoint,
    JobFailure,
    JobState,
)
from virtual_staff_engineer.remediation.contracts import (
    PatchGenerationSeed,
    PatchValidationResult,
    PatchRuleEvidence,
    PatchViolation,
    PersistedPatchProposal,
    validate_generated_patch,
)
from virtual_staff_engineer.remediation.approval import (
    ApprovalCheck,
    ApprovalRequest,
    ApprovalRule,
    HumanDecision,
    HumanDecisionResult,
)


ACTIVE_STATUS_VALUES = tuple(
    state.value
    for state in (
        JobState.ANALYZING,
        JobState.GENERATING_PATCH,
        JobState.VALIDATING_PATCH,
        JobState.CREATING_PR,
    )
)

JOB_COLUMNS = """
    workflow_job_id,
    analysis_run_id,
    remediation_action_id,
    status,
    idempotency_key,
    priority,
    attempt_count,
    max_attempts,
    available_at,
    checkpoint,
    resume_state,
    lease_owner,
    lease_token,
    lease_expires_at,
    heartbeat_at,
    failure_code,
    failure_disposition,
    error_message,
    started_at,
    completed_at,
    created_at,
    updated_at
"""


class IdempotencyConflictError(ValueError):
    """One idempotency key was reused for a different logical request."""


class LeaseLostError(RuntimeError):
    """A worker attempted to renew a lease it no longer owns."""


class ApprovalConflictError(ValueError):
    """A completed human decision was repeated with different details."""


@dataclass(frozen=True)
class WorkflowJobRecord:
    workflow_job_id: str
    analysis_run_id: str
    remediation_action_id: Optional[str]
    status: JobState
    idempotency_key: str
    priority: int
    attempt_count: int
    max_attempts: int
    available_at: datetime
    checkpoint: JobCheckpoint
    resume_state: JobState
    lease_owner: Optional[str]
    lease_token: Optional[str]
    lease_expires_at: Optional[datetime]
    heartbeat_at: Optional[datetime]
    failure_code: Optional[str]
    failure_disposition: Optional[str]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SubmissionResult:
    job: WorkflowJobRecord
    created: bool


class WorkflowJobRepository:
    """Atomic PostgreSQL queue and lease operations for Phase 3 workers."""

    def __init__(self, database_url=None):
        self.database_url = database_url

    def submit(
        self,
        analysis_input,
        idempotency_key,
        model_name,
        workflow_version,
        prompt_version,
        priority=100,
        max_attempts=3,
        available_at=None,
    ):
        if not isinstance(analysis_input, AnalysisInput):
            raise TypeError("analysis_input must be an AnalysisInput.")
        key = _require_text(idempotency_key, "idempotency_key")
        model = _require_text(model_name, "model_name")
        workflow = _require_text(workflow_version, "workflow_version")
        prompt = _require_text(prompt_version, "prompt_version")
        _require_integer(priority, "priority", 0, 1000)
        _require_integer(max_attempts, "max_attempts", 1, 100)
        if available_at is not None and not isinstance(available_at, datetime):
            raise TypeError("available_at must be a datetime or None.")

        checksum = hashlib.sha256(
            analysis_input.content.encode("utf-8")
        ).hexdigest()
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO analysis_runs (
                        commit_id,
                        status,
                        model_name,
                        workflow_version,
                        prompt_version,
                        input_type,
                        source_path,
                        input_content,
                        input_checksum
                    )
                    VALUES (%s, 'queued', %s, %s, %s, %s, %s, %s, %s)
                    RETURNING analysis_run_id;
                    """,
                    (
                        analysis_input.commit_id,
                        model,
                        workflow,
                        prompt,
                        analysis_input.input_type,
                        analysis_input.source_path,
                        analysis_input.content,
                        checksum,
                    ),
                )
                candidate_analysis_run_id = cur.fetchone()[0]
                cur.execute(
                    f"""
                    INSERT INTO workflow_jobs (
                        analysis_run_id,
                        idempotency_key,
                        priority,
                        max_attempts,
                        available_at
                    )
                    VALUES (%s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP))
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING {JOB_COLUMNS};
                    """,
                    (
                        candidate_analysis_run_id,
                        key,
                        priority,
                        max_attempts,
                        available_at,
                    ),
                )
                inserted = cur.fetchone()
                if inserted is not None:
                    return SubmissionResult(_row_to_job(inserted), True)

                cur.execute(
                    "DELETE FROM analysis_runs WHERE analysis_run_id = %s;",
                    (candidate_analysis_run_id,),
                )
                cur.execute(
                    f"""
                    SELECT {', '.join('j.' + column.strip() for column in JOB_COLUMNS.split(','))},
                           ar.commit_id,
                           ar.model_name,
                           ar.workflow_version,
                           ar.prompt_version,
                           ar.input_type,
                           ar.source_path,
                           ar.input_content,
                           ar.input_checksum
                    FROM workflow_jobs AS j
                    JOIN analysis_runs AS ar
                      ON ar.analysis_run_id = j.analysis_run_id
                    WHERE j.idempotency_key = %s;
                    """,
                    (key,),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise RuntimeError(
                        "Idempotent workflow job disappeared during submit."
                    )
                job_column_count = len(_job_column_names())
                job_row = existing[:job_column_count]
                identity_row = existing[job_column_count:]
                expected_identity = (
                    _normalize_uuid(analysis_input.commit_id),
                    model,
                    workflow,
                    prompt,
                    analysis_input.input_type,
                    analysis_input.source_path,
                    analysis_input.content,
                    checksum,
                )
                actual_identity = (
                    _normalize_uuid(identity_row[0]),
                    *identity_row[1:],
                )
                if actual_identity != expected_identity:
                    raise IdempotencyConflictError(
                        "idempotency_key already belongs to a different "
                        "analysis request."
                    )
                return SubmissionResult(_row_to_job(job_row), False)

    def get(self, workflow_job_id):
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {JOB_COLUMNS}
                    FROM workflow_jobs
                    WHERE workflow_job_id = %s;
                    """,
                    (workflow_job_id,),
                )
                row = cur.fetchone()
        return None if row is None else _row_to_job(row)

    def claim_next(self, worker_id, lease_seconds=60, resume_states=None):
        worker = _require_text(worker_id, "worker_id")
        if len(worker) > 255:
            raise ValueError("worker_id must contain at most 255 characters.")
        _require_integer(lease_seconds, "lease_seconds", 1, 86400)
        normalized_states = _normalize_resume_states(resume_states)
        lease_token = uuid.uuid4()

        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                self._promote_due_retries(cur, limit=100)
                cur.execute(
                    f"""
                    WITH candidate AS (
                        SELECT workflow_job_id
                        FROM workflow_jobs
                        WHERE status = 'queued'
                          AND available_at <= CURRENT_TIMESTAMP
                          AND attempt_count < max_attempts
                          AND resume_state = ANY(%s::varchar[])
                        ORDER BY priority DESC, available_at, created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE workflow_jobs AS job
                    SET status = job.resume_state,
                        attempt_count = job.attempt_count + 1,
                        lease_owner = %s,
                        lease_token = %s,
                        heartbeat_at = CURRENT_TIMESTAMP,
                        lease_expires_at = (
                            CURRENT_TIMESTAMP + %s * INTERVAL '1 second'
                        )
                    FROM candidate
                    WHERE job.workflow_job_id = candidate.workflow_job_id
                    RETURNING {', '.join('job.' + name for name in _job_column_names())};
                    """,
                    (
                        list(normalized_states),
                        worker,
                        lease_token,
                        lease_seconds,
                    ),
                )
                row = cur.fetchone()
        return None if row is None else _row_to_job(row)

    def heartbeat(self, workflow_job_id, lease_token, lease_seconds=60):
        _require_integer(lease_seconds, "lease_seconds", 1, 86400)
        try:
            normalized_token = uuid.UUID(str(lease_token))
        except (TypeError, ValueError) as exc:
            raise ValueError("lease_token must be a UUID.") from exc

        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE workflow_jobs
                    SET heartbeat_at = CURRENT_TIMESTAMP,
                        lease_expires_at = (
                            CURRENT_TIMESTAMP + %s * INTERVAL '1 second'
                        )
                    WHERE workflow_job_id = %s
                      AND lease_token = %s
                      AND status = ANY(%s::varchar[])
                      AND lease_expires_at > CURRENT_TIMESTAMP
                    RETURNING {JOB_COLUMNS};
                    """,
                    (
                        lease_seconds,
                        workflow_job_id,
                        normalized_token,
                        list(ACTIVE_STATUS_VALUES),
                    ),
                )
                row = cur.fetchone()
        if row is None:
            raise LeaseLostError(
                "Workflow job lease is missing, expired, or owned by another "
                "worker."
            )
        return _row_to_job(row)

    def begin_analysis(self, workflow_job_id, lease_token):
        """Load a claimed input and mark its audit run as analyzing."""
        normalized_token = _normalize_lease_token(lease_token)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                job = self._lock_owned_active_job(
                    cur,
                    workflow_job_id,
                    normalized_token,
                    expected_state=JobState.ANALYZING,
                )
                cur.execute(
                    """
                    UPDATE analysis_runs
                    SET status = 'analyzing',
                        started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
                        completed_at = NULL,
                        error_message = NULL
                    WHERE analysis_run_id = %s
                      AND status IN ('queued', 'analyzing')
                    RETURNING input_type, input_content, source_path, commit_id;
                    """,
                    (job.analysis_run_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ValueError(
                        "Analysis run is missing or already terminal."
                    )
        return AnalysisInput(
            input_type=row[0],
            content=row[1],
            source_path=row[2],
            commit_id=_normalize_uuid(row[3]),
        )

    def complete_analysis(
        self,
        workflow_job_id,
        lease_token,
        result,
        input_tokens=0,
        output_tokens=0,
    ):
        """Atomically persist analysis output and advance its workflow job."""
        if not isinstance(result, AnalysisResult):
            raise TypeError("result must be an AnalysisResult.")
        normalized_token = _normalize_lease_token(lease_token)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {JOB_COLUMNS}
                    FROM workflow_jobs
                    WHERE workflow_job_id = %s
                    FOR UPDATE;
                    """,
                    (workflow_job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise LeaseLostError("Workflow job does not exist.")
                job = _row_to_job(row)
                if job.checkpoint is not JobCheckpoint.SUBMITTED:
                    return job
                self._require_owned_active_job(
                    job,
                    normalized_token,
                    expected_state=JobState.ANALYZING,
                )
                AnalysisRepository(self.database_url).persist_result(
                    cur,
                    job.analysis_run_id,
                    result,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                target = (
                    JobState.QUEUED
                    if result.status == "review_required"
                    else JobState.COMPLETED
                )
                cur.execute(
                    f"""
                    UPDATE workflow_jobs
                    SET status = %s,
                        checkpoint = 'analysis_completed',
                        resume_state = CASE
                            WHEN %s THEN 'generating_patch' ELSE resume_state
                        END,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL
                    WHERE workflow_job_id = %s
                    RETURNING {JOB_COLUMNS};
                    """,
                    (
                        target.value,
                        result.status == "review_required",
                        workflow_job_id,
                    ),
                )
                return _row_to_job(cur.fetchone())

    def schedule_failure(
        self,
        workflow_job_id,
        lease_token,
        failure,
        delay_seconds=0,
    ):
        """Persist an explicit failure, retrying only within the budget."""
        if not isinstance(failure, JobFailure):
            raise TypeError("failure must be a JobFailure.")
        if (
            isinstance(delay_seconds, bool)
            or not isinstance(delay_seconds, (int, float))
            or delay_seconds < 0
            or delay_seconds > 86400
        ):
            raise ValueError("delay_seconds must be from 0 to 86400.")
        normalized_token = _normalize_lease_token(lease_token)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                job = self._lock_owned_active_job(
                    cur, workflow_job_id, normalized_token
                )
                retry = (
                    failure.disposition is FailureDisposition.RETRYABLE
                    and job.attempt_count < job.max_attempts
                )
                target = (
                    JobState.RETRY_SCHEDULED if retry else JobState.FAILED
                )
                cur.execute(
                    f"""
                    UPDATE workflow_jobs
                    SET status = %s,
                        available_at = CASE
                            WHEN %s THEN (
                                CURRENT_TIMESTAMP + %s * INTERVAL '1 second'
                            )
                            ELSE available_at
                        END,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL,
                        failure_code = %s,
                        failure_disposition = %s,
                        error_message = %s
                    WHERE workflow_job_id = %s
                    RETURNING {JOB_COLUMNS};
                    """,
                    (
                        target.value,
                        retry,
                        float(delay_seconds),
                        failure.code.value,
                        failure.disposition.value,
                        failure.message[:4000],
                        workflow_job_id,
                    ),
                )
                updated = _row_to_job(cur.fetchone())
                if target is JobState.FAILED and job.status is JobState.ANALYZING:
                    cur.execute(
                        """
                        UPDATE analysis_runs
                        SET status = 'failed',
                            completed_at = CURRENT_TIMESTAMP,
                            error_message = %s
                        WHERE analysis_run_id = %s
                          AND status IN ('queued', 'analyzing');
                        """,
                        (failure.message[:4000], job.analysis_run_id),
                    )
                return updated

    def begin_patch_generation(self, workflow_job_id, lease_token):
        """Load persisted validated violations for an owned patch stage."""
        normalized_token = _normalize_lease_token(lease_token)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                job = self._lock_owned_active_job(
                    cur,
                    workflow_job_id,
                    normalized_token,
                    expected_state=JobState.GENERATING_PATCH,
                )
                if job.checkpoint is not JobCheckpoint.ANALYSIS_COMPLETED:
                    raise ValueError(
                        "Patch generation requires analysis_completed."
                    )
                cur.execute(
                    """
                    SELECT ar.source_path, c.commit_sha
                    FROM analysis_runs AS ar
                    LEFT JOIN commits AS c ON c.commit_id = ar.commit_id
                    WHERE ar.analysis_run_id = %s
                      AND ar.status = 'review_required';
                    """,
                    (job.analysis_run_id,),
                )
                run = cur.fetchone()
                if run is None:
                    raise ValueError(
                        "Patch generation requires a review_required analysis."
                    )
                source_path, source_revision = run
                if not source_path or source_path == "<input>":
                    raise ValueError(
                        "Patch generation requires an exact source path."
                    )
                cur.execute(
                    """
                    SELECT v.violation_id,
                           v.file_path,
                           v.start_line,
                           v.end_line,
                           v.input_excerpt,
                           v.explanation,
                           ve.playbook_chunk_id,
                           pc.rule_key,
                           ve.rule_snapshot
                    FROM violations AS v
                    JOIN violation_evidence AS ve
                      ON ve.violation_id = v.violation_id
                    JOIN playbook_chunks AS pc
                      ON pc.playbook_chunk_id = ve.playbook_chunk_id
                    WHERE v.analysis_run_id = %s
                      AND v.validation_status = 'valid'
                    ORDER BY v.file_path, v.start_line, v.violation_id,
                             pc.rule_key;
                    """,
                    (job.analysis_run_id,),
                )
                rows = cur.fetchall()
        if not rows:
            raise ValueError(
                "Patch generation requires at least one validated violation."
            )
        violations = _rows_to_patch_violations(rows)
        return PatchGenerationSeed(
            source_path=source_path,
            source_revision=source_revision,
            violations=violations,
        )

    def complete_patch_generation(
        self,
        workflow_job_id,
        lease_token,
        context,
        patch,
        model_name,
        prompt_version,
    ):
        """Persist a proposal and hand the job to validation atomically."""
        validate_generated_patch(context, patch)
        model = _require_text(model_name, "model_name")
        prompt = _require_text(prompt_version, "prompt_version")
        normalized_token = _normalize_lease_token(lease_token)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {JOB_COLUMNS}
                    FROM workflow_jobs
                    WHERE workflow_job_id = %s
                    FOR UPDATE;
                    """,
                    (workflow_job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise LeaseLostError("Workflow job does not exist.")
                job = _row_to_job(row)
                if job.checkpoint is not JobCheckpoint.ANALYSIS_COMPLETED:
                    if job.checkpoint is JobCheckpoint.PATCH_GENERATED:
                        return job
                    raise ValueError(
                        "Patch generation requires analysis_completed."
                    )
                self._require_owned_active_job(
                    job,
                    normalized_token,
                    expected_state=JobState.GENERATING_PATCH,
                )
                violation_ids = tuple(
                    item.violation_id for item in context.violations
                )
                cur.execute(
                    """
                    SELECT violation_id::text, file_path
                    FROM violations
                    WHERE analysis_run_id = %s
                      AND validation_status = 'valid'
                    ORDER BY violation_id;
                    """,
                    (job.analysis_run_id,),
                )
                persisted = cur.fetchall()
                if {row[0] for row in persisted} != set(violation_ids):
                    raise ValueError(
                        "Patch context does not match persisted violations."
                    )
                if any(row[1] != context.source.source_path for row in persisted):
                    raise ValueError(
                        "Patch context source path does not match violations."
                    )
                cur.execute(
                    """
                    SELECT ar.source_path, c.commit_sha
                    FROM analysis_runs AS ar
                    LEFT JOIN commits AS c ON c.commit_id = ar.commit_id
                    WHERE ar.analysis_run_id = %s;
                    """,
                    (job.analysis_run_id,),
                )
                source_identity = cur.fetchone()
                normalized_source_identity = (
                    source_identity[0],
                    source_identity[1].lower()
                    if source_identity[1] is not None
                    else None,
                )
                if normalized_source_identity != (
                    context.source.source_path,
                    context.source.revision,
                ):
                    raise ValueError(
                        "Patch source identity does not match the analysis."
                    )
                cur.execute(
                    """
                    SELECT ve.playbook_chunk_id::text,
                           pc.rule_key,
                           ve.rule_snapshot
                    FROM violation_evidence AS ve
                    JOIN violations AS v
                      ON v.violation_id = ve.violation_id
                    JOIN playbook_chunks AS pc
                      ON pc.playbook_chunk_id = ve.playbook_chunk_id
                    WHERE v.analysis_run_id = %s
                    ORDER BY ve.playbook_chunk_id;
                    """,
                    (job.analysis_run_id,),
                )
                persisted_evidence = set(cur.fetchall())
                context_evidence = {
                    (
                        evidence.playbook_chunk_id,
                        evidence.rule_key,
                        evidence.rule_snapshot,
                    )
                    for violation in context.violations
                    for evidence in violation.evidence
                }
                if context_evidence != persisted_evidence:
                    raise ValueError(
                        "Patch rule evidence does not match persisted evidence."
                    )
                cur.execute(
                    """
                    INSERT INTO remediation_actions (
                        analysis_run_id,
                        status,
                        idempotency_key
                    )
                    VALUES (%s, 'proposed', %s)
                    RETURNING remediation_action_id;
                    """,
                    (job.analysis_run_id, f"patch:{workflow_job_id}"),
                )
                remediation_action_id = cur.fetchone()[0]
                for violation_id in sorted(violation_ids):
                    cur.execute(
                        """
                        INSERT INTO remediation_action_violations (
                            remediation_action_id, violation_id
                        )
                        VALUES (%s, %s);
                        """,
                        (remediation_action_id, violation_id),
                    )
                cur.execute(
                    """
                    INSERT INTO patch_proposals (
                        remediation_action_id,
                        source_path,
                        source_revision,
                        original_content,
                        original_sha256,
                        unified_diff,
                        explanation,
                        model_name,
                        prompt_version
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING patch_proposal_id;
                    """,
                    (
                        remediation_action_id,
                        context.source.source_path,
                        context.source.revision,
                        context.source.content,
                        context.source.content_sha256,
                        patch.unified_diff,
                        patch.explanation,
                        model,
                        prompt,
                    ),
                )
                patch_proposal_id = cur.fetchone()[0]
                evidence_by_chunk = {
                    evidence.playbook_chunk_id: evidence
                    for violation in context.violations
                    for evidence in violation.evidence
                }
                for chunk_id in sorted(evidence_by_chunk):
                    evidence = evidence_by_chunk[chunk_id]
                    cur.execute(
                        """
                        INSERT INTO patch_proposal_rules (
                            patch_proposal_id,
                            playbook_chunk_id,
                            rule_key,
                            rule_snapshot
                        )
                        VALUES (%s, %s, %s, %s);
                        """,
                        (
                            patch_proposal_id,
                            evidence.playbook_chunk_id,
                            evidence.rule_key,
                            evidence.rule_snapshot,
                        ),
                    )
                cur.execute(
                    f"""
                    UPDATE workflow_jobs
                    SET remediation_action_id = %s,
                        status = 'queued',
                        checkpoint = 'patch_generated',
                        resume_state = 'validating_patch',
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL
                    WHERE workflow_job_id = %s
                    RETURNING {JOB_COLUMNS};
                    """,
                    (remediation_action_id, workflow_job_id),
                )
                return _row_to_job(cur.fetchone())

    def promote_due_retries(self, limit=100):
        _require_integer(limit, "limit", 1, 10000)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                rows = self._promote_due_retries(cur, limit)
        return tuple(_row_to_job(row) for row in rows)

    def begin_patch_validation(self, workflow_job_id, lease_token):
        """Load an immutable proposal for an owned validation stage."""
        normalized_token = _normalize_lease_token(lease_token)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                job = self._lock_owned_active_job(
                    cur,
                    workflow_job_id,
                    normalized_token,
                    expected_state=JobState.VALIDATING_PATCH,
                )
                if job.checkpoint is not JobCheckpoint.PATCH_GENERATED:
                    raise ValueError(
                        "Patch validation requires patch_generated."
                    )
                cur.execute(
                    """
                    SELECT pp.patch_proposal_id,
                           pp.remediation_action_id,
                           pp.source_path,
                           pp.source_revision,
                           pp.original_content,
                           pp.original_sha256,
                           pp.unified_diff
                    FROM patch_proposals AS pp
                    WHERE pp.remediation_action_id = %s;
                    """,
                    (job.remediation_action_id,),
                )
                row = cur.fetchone()
        if row is None:
            raise ValueError("Workflow job has no persisted patch proposal.")
        return PersistedPatchProposal(
            patch_proposal_id=str(row[0]),
            remediation_action_id=str(row[1]),
            source_path=row[2],
            source_revision=row[3],
            original_content=row[4],
            original_sha256=row[5],
            unified_diff=row[6],
        )

    def complete_patch_validation(
        self,
        workflow_job_id,
        lease_token,
        proposal,
        result,
        validator_version,
    ):
        """Persist validation checks and advance or fail atomically."""
        if not isinstance(proposal, PersistedPatchProposal):
            raise TypeError("proposal must be a PersistedPatchProposal.")
        if not isinstance(result, PatchValidationResult):
            raise TypeError("result must be a PatchValidationResult.")
        version = _require_text(validator_version, "validator_version")
        normalized_token = _normalize_lease_token(lease_token)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {JOB_COLUMNS}
                    FROM workflow_jobs
                    WHERE workflow_job_id = %s
                    FOR UPDATE;
                    """,
                    (workflow_job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise LeaseLostError("Workflow job does not exist.")
                job = _row_to_job(row)
                if job.checkpoint is not JobCheckpoint.PATCH_GENERATED:
                    if job.checkpoint is JobCheckpoint.PATCH_VALIDATED:
                        return job
                    raise ValueError(
                        "Patch validation requires patch_generated."
                    )
                self._require_owned_active_job(
                    job,
                    normalized_token,
                    expected_state=JobState.VALIDATING_PATCH,
                )
                if (
                    proposal.remediation_action_id
                    != job.remediation_action_id
                ):
                    raise ValueError(
                        "Patch proposal does not belong to the workflow job."
                    )
                cur.execute(
                    """
                    SELECT 1
                    FROM patch_proposals
                    WHERE patch_proposal_id = %s
                      AND remediation_action_id = %s;
                    """,
                    (
                        proposal.patch_proposal_id,
                        job.remediation_action_id,
                    ),
                )
                if cur.fetchone() is None:
                    raise ValueError("Persisted patch proposal identity changed.")
                cur.execute(
                    """
                    INSERT INTO patch_validation_runs (
                        patch_proposal_id,
                        status,
                        validator_version,
                        changed_lines,
                        resulting_sha256
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING patch_validation_id;
                    """,
                    (
                        proposal.patch_proposal_id,
                        result.status,
                        version,
                        result.changed_lines,
                        result.resulting_sha256,
                    ),
                )
                validation_id = cur.fetchone()[0]
                for sequence, check in enumerate(result.checks, start=1):
                    cur.execute(
                        """
                        INSERT INTO patch_validation_checks (
                            patch_validation_id,
                            check_sequence,
                            check_name,
                            status,
                            details
                        )
                        VALUES (%s, %s, %s, %s, %s);
                        """,
                        (
                            validation_id,
                            sequence,
                            check.name,
                            check.status,
                            check.details,
                        ),
                    )
                valid = result.status == "valid"
                error_message = None
                if not valid:
                    error_message = "; ".join(
                        check.details
                        for check in result.checks
                        if check.status == "failed"
                    )[:4000]
                    cur.execute(
                        """
                        UPDATE remediation_actions
                        SET status = 'failed',
                            error_message = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE remediation_action_id = %s;
                        """,
                        (error_message, job.remediation_action_id),
                    )
                cur.execute(
                    f"""
                    UPDATE workflow_jobs
                    SET status = %s,
                        checkpoint = 'patch_validated',
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL,
                        failure_code = %s,
                        failure_disposition = %s,
                        error_message = %s
                    WHERE workflow_job_id = %s
                    RETURNING {JOB_COLUMNS};
                    """,
                    (
                        (
                            JobState.AWAITING_APPROVAL.value
                            if valid
                            else JobState.FAILED.value
                        ),
                        None if valid else "patch_invalid",
                        None if valid else "permanent",
                        error_message,
                        workflow_job_id,
                    ),
                )
                return _row_to_job(cur.fetchone())

    def recover_expired_leases(self, limit=100):
        _require_integer(limit, "limit", 1, 10000)
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    WITH expired AS (
                        SELECT workflow_job_id
                        FROM workflow_jobs
                        WHERE status = ANY(%s::varchar[])
                          AND lease_expires_at <= CURRENT_TIMESTAMP
                        ORDER BY lease_expires_at, created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE workflow_jobs AS job
                    SET status = CASE
                            WHEN job.attempt_count >= job.max_attempts
                                THEN 'failed'
                            ELSE 'retry_scheduled'
                        END,
                        available_at = CURRENT_TIMESTAMP,
                        lease_owner = NULL,
                        lease_token = NULL,
                        lease_expires_at = NULL,
                        heartbeat_at = NULL,
                        failure_code = 'lease_expired',
                        failure_disposition = 'retryable',
                        error_message = 'Worker lease expired before completion.'
                    FROM expired
                    WHERE job.workflow_job_id = expired.workflow_job_id
                    RETURNING {', '.join('job.' + name for name in _job_column_names())};
                    """,
                    (list(ACTIVE_STATUS_VALUES), limit),
                )
                rows = cur.fetchall()
                failed_analysis_run_ids = tuple(
                    str(row[1])
                    for row in rows
                    if row[3] == JobState.FAILED.value
                    and row[10] == JobState.ANALYZING.value
                )
                if failed_analysis_run_ids:
                    cur.execute(
                        """
                        UPDATE analysis_runs
                        SET status = 'failed',
                            completed_at = CURRENT_TIMESTAMP,
                            error_message = (
                                'Worker lease expired and the attempt budget '
                                'was exhausted.'
                            )
                        WHERE analysis_run_id = ANY(%s::uuid[])
                          AND status IN ('queued', 'analyzing');
                        """,
                        (list(failed_analysis_run_ids),),
                    )
        return tuple(_row_to_job(row) for row in rows)

    def get_approval_request(self, workflow_job_id):
        """Return the exact validated proposal a human must review."""
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT j.workflow_job_id,
                           j.remediation_action_id,
                           pp.patch_proposal_id,
                           pp.source_path,
                           pp.source_revision,
                           pp.original_sha256,
                           pp.unified_diff,
                           pp.explanation,
                           pvr.patch_validation_id,
                           pvr.status,
                           pvr.resulting_sha256
                    FROM workflow_jobs AS j
                    JOIN patch_proposals AS pp
                      ON pp.remediation_action_id = j.remediation_action_id
                    JOIN patch_validation_runs AS pvr
                      ON pvr.patch_proposal_id = pp.patch_proposal_id
                    WHERE j.workflow_job_id = %s
                      AND j.status = 'awaiting_approval'
                      AND j.checkpoint = 'patch_validated'
                      AND pvr.status = 'valid';
                    """,
                    (workflow_job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cur.execute(
                    """
                    SELECT rule_key, rule_snapshot
                    FROM patch_proposal_rules
                    WHERE patch_proposal_id = %s
                    ORDER BY rule_key, playbook_chunk_id;
                    """,
                    (row[2],),
                )
                rules = tuple(
                    ApprovalRule(rule_key=item[0], rule_snapshot=item[1])
                    for item in cur.fetchall()
                )
                cur.execute(
                    """
                    SELECT check_name, status, details
                    FROM patch_validation_checks
                    WHERE patch_validation_id = %s
                    ORDER BY check_sequence;
                    """,
                    (row[8],),
                )
                checks = tuple(
                    ApprovalCheck(name=item[0], status=item[1], details=item[2])
                    for item in cur.fetchall()
                )
        return ApprovalRequest(
            workflow_job_id=str(row[0]),
            remediation_action_id=str(row[1]),
            patch_proposal_id=str(row[2]),
            source_path=row[3],
            source_revision=row[4],
            original_sha256=row[5],
            unified_diff=row[6],
            explanation=row[7],
            rules=rules,
            validation_status=row[9],
            resulting_sha256=row[10],
            checks=checks,
        )

    def record_human_decision(self, workflow_job_id, decision):
        """Audit an idempotent decision over the exact validated proposal."""
        if not isinstance(decision, HumanDecision):
            raise TypeError("decision must be a HumanDecision.")
        with connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {JOB_COLUMNS}
                    FROM workflow_jobs
                    WHERE workflow_job_id = %s
                    FOR UPDATE;
                    """,
                    (workflow_job_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise ValueError("Workflow job does not exist.")
                job = _row_to_job(row)
                if job.checkpoint is JobCheckpoint.APPROVAL_RECORDED:
                    cur.execute(
                        """
                        SELECT decision, actor, comment
                        FROM remediation_approval_decisions
                        WHERE workflow_job_id = %s;
                        """,
                        (workflow_job_id,),
                    )
                    existing = cur.fetchone()
                    requested = (
                        decision.decision,
                        decision.actor,
                        decision.comment,
                    )
                    if existing == requested:
                        return HumanDecisionResult(job=job, created=False)
                    raise ApprovalConflictError(
                        "Workflow job already has a different human decision."
                    )
                if (
                    job.status is not JobState.AWAITING_APPROVAL
                    or job.checkpoint is not JobCheckpoint.PATCH_VALIDATED
                ):
                    raise ValueError(
                        "Workflow job is not awaiting patch approval."
                    )
                cur.execute(
                    """
                    SELECT pp.patch_proposal_id,
                           pvr.patch_validation_id
                    FROM patch_proposals AS pp
                    JOIN patch_validation_runs AS pvr
                      ON pvr.patch_proposal_id = pp.patch_proposal_id
                    WHERE pp.remediation_action_id = %s
                      AND pvr.status = 'valid';
                    """,
                    (job.remediation_action_id,),
                )
                artifact = cur.fetchone()
                if artifact is None:
                    raise ValueError(
                        "Approval requires one successfully validated proposal."
                    )
                cur.execute(
                    """
                    INSERT INTO remediation_approval_decisions (
                        workflow_job_id,
                        remediation_action_id,
                        patch_proposal_id,
                        patch_validation_id,
                        decision,
                        actor,
                        comment
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        workflow_job_id,
                        job.remediation_action_id,
                        artifact[0],
                        artifact[1],
                        decision.decision,
                        decision.actor,
                        decision.comment,
                    ),
                )
                approved = decision.decision == "approved"
                cur.execute(
                    """
                    UPDATE remediation_actions
                    SET status = %s,
                        approved_by = CASE WHEN %s THEN %s ELSE NULL END,
                        approved_at = CASE
                            WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL
                        END,
                        rejected_at = CASE
                            WHEN %s THEN NULL ELSE CURRENT_TIMESTAMP
                        END,
                        error_message = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE remediation_action_id = %s
                      AND status = 'proposed';
                    """,
                    (
                        decision.decision,
                        approved,
                        decision.actor,
                        approved,
                        approved,
                        job.remediation_action_id,
                    ),
                )
                if cur.rowcount != 1:
                    raise ValueError(
                        "Remediation action is no longer awaiting a decision."
                    )
                cur.execute(
                    f"""
                    UPDATE workflow_jobs
                    SET status = %s,
                        checkpoint = 'approval_recorded'
                    WHERE workflow_job_id = %s
                    RETURNING {JOB_COLUMNS};
                    """,
                    (decision.decision, workflow_job_id),
                )
                updated = _row_to_job(cur.fetchone())
                return HumanDecisionResult(job=updated, created=True)

    def _lock_owned_active_job(
        self,
        cur,
        workflow_job_id,
        lease_token,
        expected_state=None,
    ):
        cur.execute(
            f"""
            SELECT {JOB_COLUMNS}
            FROM workflow_jobs
            WHERE workflow_job_id = %s
            FOR UPDATE;
            """,
            (workflow_job_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise LeaseLostError("Workflow job does not exist.")
        job = _row_to_job(row)
        self._require_owned_active_job(job, lease_token, expected_state)
        return job

    @staticmethod
    def _require_owned_active_job(job, lease_token, expected_state=None):
        now = (
            datetime.now(job.lease_expires_at.tzinfo)
            if job.lease_expires_at
            else None
        )
        if (
            job.status not in ACTIVE_JOB_STATES
            or (expected_state is not None and job.status is not expected_state)
            or job.lease_token != str(lease_token)
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
        ):
            raise LeaseLostError(
                "Workflow job lease is missing, expired, in the wrong stage, "
                "or owned by another worker."
            )

    @staticmethod
    def _promote_due_retries(cur, limit):
        cur.execute(
            f"""
            WITH due AS (
                SELECT workflow_job_id
                FROM workflow_jobs
                WHERE status = 'retry_scheduled'
                  AND available_at <= CURRENT_TIMESTAMP
                  AND attempt_count < max_attempts
                ORDER BY available_at, created_at
                FOR UPDATE SKIP LOCKED
                LIMIT %s
            )
            UPDATE workflow_jobs AS job
            SET status = 'queued',
                failure_code = NULL,
                failure_disposition = NULL,
                error_message = NULL
            FROM due
            WHERE job.workflow_job_id = due.workflow_job_id
            RETURNING {', '.join('job.' + name for name in _job_column_names())};
            """,
            (limit,),
        )
        return cur.fetchall()


def _job_column_names():
    return tuple(
        column.strip()
        for column in JOB_COLUMNS.split(",")
        if column.strip()
    )


def _row_to_job(row):
    values = dict(zip(_job_column_names(), row))
    return WorkflowJobRecord(
        workflow_job_id=str(values["workflow_job_id"]),
        analysis_run_id=str(values["analysis_run_id"]),
        remediation_action_id=_normalize_uuid(values["remediation_action_id"]),
        status=JobState(values["status"]),
        idempotency_key=values["idempotency_key"],
        priority=values["priority"],
        attempt_count=values["attempt_count"],
        max_attempts=values["max_attempts"],
        available_at=values["available_at"],
        checkpoint=JobCheckpoint(values["checkpoint"]),
        resume_state=JobState(values["resume_state"]),
        lease_owner=values["lease_owner"],
        lease_token=_normalize_uuid(values["lease_token"]),
        lease_expires_at=values["lease_expires_at"],
        heartbeat_at=values["heartbeat_at"],
        failure_code=values["failure_code"],
        failure_disposition=values["failure_disposition"],
        error_message=values["error_message"],
        started_at=values["started_at"],
        completed_at=values["completed_at"],
        created_at=values["created_at"],
        updated_at=values["updated_at"],
    )


def _normalize_uuid(value):
    return None if value is None else str(value)


def _require_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _require_integer(value, field_name, minimum, maximum):
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(
            f"{field_name} must be an integer from {minimum} to {maximum}."
        )


def _normalize_lease_token(lease_token):
    try:
        return uuid.UUID(str(lease_token))
    except (TypeError, ValueError) as exc:
        raise ValueError("lease_token must be a UUID.") from exc


def _normalize_resume_states(resume_states):
    if resume_states is None:
        return ACTIVE_STATUS_VALUES
    try:
        states = tuple(JobState(value) for value in resume_states)
    except (TypeError, ValueError) as exc:
        raise ValueError("resume_states contains an unknown job state.") from exc
    if not states or any(state not in ACTIVE_JOB_STATES for state in states):
        raise ValueError("resume_states must contain active job states.")
    return tuple(state.value for state in states)


def _rows_to_patch_violations(rows):
    grouped = {}
    order = []
    for row in rows:
        violation_id = str(row[0])
        if violation_id not in grouped:
            grouped[violation_id] = {
                "source_path": row[1],
                "start_line": row[2],
                "end_line": row[3],
                "input_excerpt": row[4],
                "explanation": row[5],
                "evidence": [],
            }
            order.append(violation_id)
        grouped[violation_id]["evidence"].append(
            PatchRuleEvidence(
                playbook_chunk_id=str(row[6]),
                rule_key=row[7],
                rule_snapshot=row[8],
            )
        )
    return tuple(
        PatchViolation(
            violation_id=violation_id,
            source_path=grouped[violation_id]["source_path"],
            start_line=grouped[violation_id]["start_line"],
            end_line=grouped[violation_id]["end_line"],
            input_excerpt=grouped[violation_id]["input_excerpt"],
            explanation=grouped[violation_id]["explanation"],
            evidence=tuple(grouped[violation_id]["evidence"]),
        )
        for violation_id in order
    )
