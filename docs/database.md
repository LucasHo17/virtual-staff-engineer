# Database setup

Run all pending migrations from the project root:

```bash
python scripts/migrate.py
```

The initializer records each migration filename and SHA-256 checksum in
`schema_migrations`. Applied migrations are skipped on later runs. Never edit an
applied migration; add a new numbered SQL file under
`src/virtual_staff_engineer/database/sql/` instead.

## Baseline migration

`001_complete_schema.sql` is a one-time reset of the disposable prototype
schema. It removes the original four prototype tables and creates the complete
versioned, auditable schema. Because the migration is recorded atomically, its
reset statements do not run again after a successful application.

## Deletion policy

Historical records use restrictive foreign keys. Repositories and playbook
documents are archived by setting `archived_at`; they are not normally deleted.
Playbook versions and chunks are immutable after insertion.

## Ingestion

After migrations are applied:

```bash
python scripts/ingest_playbook.py playbooks/sample_playbook.md \
    --category standards
```

An unchanged checksum embedded by the same model and dimension is skipped.
Changed content or an embedding-model change creates the next immutable
`playbook_versions.version` and a new set of `playbook_chunks`.

## Phase 2 analysis audit trail

`003_analysis_audit_trail.sql` allows analysis runs to originate from a raw
code diff or design document as well as a stored commit. It adds
`inconclusive` as a terminal status and creates:

- `analysis_run_queries` for ordered tool calls;
- `analysis_retrieval_evidence` for query-to-chunk provenance;
- `analysis_finding_reviews` for supported, unsupported, and undecided
  evaluator outcomes; and
- `analysis_finding_rejections` for proposals blocked by deterministic checks.

Supported reviews create `violations` linked back to the reviewed proposal.
Unsupported and malformed proposals remain auditable but never become
violations. All historical foreign keys continue to use `ON DELETE RESTRICT`.

## Phase 3 durable workflow jobs

`005_workflow_jobs.sql` adds a durable execution envelope around analysis and
remediation records:

- `workflow_jobs` stores queue priority, idempotency identity, attempts,
  availability, checkpoint, lease, classified failure, and terminal timing;
- `workflow_job_transitions` stores the ordered status history; and
- database triggers independently enforce legal transitions, immutable job
  identity, and monotonic checkpoints.

Active worker states require a complete lease. Waiting and terminal states
must not retain one. `retry_scheduled` requires a retryable failure, while
`failed` accepts a permanent failure or an exhausted retryable failure. See
[jobs.md](jobs.md) for the complete lifecycle and trade-offs.

`006_workflow_resume_state.sql` adds the active stage a retried job must resume.
`007_workflow_stage_handoff.sql` lets completed analysis release its lease and
queue patch generation without pretending that the handoff is a retry.
`008_patch_proposals.sql` stores immutable patch content and rule provenance,
then permits a lease-free handoff from generation to validation.
The queue repository uses this value with `FOR UPDATE SKIP LOCKED`, preventing
recovery from replaying already completed analysis, patch, or approval work.
