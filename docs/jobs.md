# Durable workflow jobs

Phase 3 wraps the Phase 2 analysis and future remediation flow in a durable
PostgreSQL job. `analysis_runs` remains the immutable analysis audit record,
and `remediation_actions` remains the approval and GitHub mutation record. A
`workflow_job` is the outer execution envelope that owns queueing, attempts,
leases, retry timing, checkpoints, and terminal failure.

## Lifecycle

```text
queued
  └─→ analyzing
        ├─→ completed                         no supported violations
        └─→ queued [resume: generating_patch]
              └─→ generating_patch
              └─→ validating_patch
                    └─→ awaiting_approval
                          ├─→ rejected
                          └─→ approved
                                └─→ creating_pr
                                      └─→ completed

active work ─→ retry_scheduled ─→ queued      temporary failure
active work ─→ failed                         permanent/exhausted failure
safe pre-mutation states ─→ cancelled         operator cancellation
```

Terminal states are `completed`, `failed`, `rejected`, and `cancelled`. They
cannot transition again. `creating_pr` cannot be cancelled because an
interrupted GitHub mutation has an uncertain external outcome; recovery must
reconcile the idempotency key with GitHub before deciding what to do.

## State responsibilities

| State | Purpose |
|---|---|
| `queued` | Ready for an atomic worker claim. |
| `analyzing` | Running the Phase 2 evidence-grounded analysis. |
| `generating_patch` | Producing a proposed remediation for supported findings. |
| `validating_patch` | Applying deterministic patch and test safety checks. |
| `awaiting_approval` | Persisted patch is immutable and waiting for a person. |
| `approved` | The exact patch has human authorization but no GitHub mutation yet. |
| `creating_pr` | Performing the externally visible GitHub operation. |
| `retry_scheduled` | Temporary failure is recorded until `available_at`. |
| `completed` | Clean analysis or successfully created remediation PR. |
| `failed` | Permanent failure or exhausted temporary failure. |
| `rejected` | Human declined the proposed patch. |
| `cancelled` | Operator stopped work before an uncertain external mutation. |

## Failure taxonomy

Retryability is explicit rather than inferred from an exception string.

| Retryable | Permanent |
|---|---|
| Provider timeout | Invalid input |
| Rate limit | Invalid model contract |
| Network error | Evidence validation failure |
| Database unavailable | Invalid patch |
| GitHub unavailable | Stale source revision |
| Expired worker lease | Unsupported repository state |

A retryable failure may enter `retry_scheduled`. A permanent failure goes to
`failed`. A retryable failure also goes to `failed` after its attempt budget is
exhausted. Human rejection is a domain decision, not a failure.

## Checkpoints

Checkpoints are monotonic and idempotent:

```text
submitted
→ analysis_completed
→ patch_generated
→ patch_validated
→ approval_recorded
→ pr_created
```

They describe durable completed work, not the operation currently executing.
After a retry, a worker reads the checkpoint and resumes at the next boundary
instead of repeating every model or external call.

`resume_state` records the active stage that must be reclaimed. A new job starts
with `analyzing`. When a lease expires or active work schedules a retry, the
database preserves that active state. The next claim can therefore enter
`generating_patch`, `validating_patch`, or `creating_pr` directly instead of
replaying completed stages.

## Database invariants

Migration `005_workflow_jobs.sql` creates `workflow_jobs` and the append-only
`workflow_job_transitions` audit history. PostgreSQL triggers and constraints
enforce:

- insertion only in `queued`;
- the legal transition graph and immutable job identity;
- one job per analysis run and one globally unique idempotency key;
- attempt counts within a configured positive budget;
- monotonic checkpoints;
- a complete, unexpired lease shape for active worker states and no lease for
  waiting or terminal states;
- retryable failure details for `retry_scheduled` and classified failure
  details for `failed`;
- completion timestamps only on terminal states; and
- automatic transition-history rows even when SQL bypasses application code.

Historical foreign keys use `ON DELETE RESTRICT`.

Migration `006_workflow_resume_state.sql` adds the durable resume target and
updates the transition trigger so a queued retry may enter only its recorded
active stage.

## Phase 3B repository operations

`WorkflowJobRepository` provides the queue's transactional boundary:

- `submit` creates the queued analysis record and job in one transaction. A
  repeated idempotency key returns the original job only when the full logical
  request identity matches; reusing the key for different content fails.
- `claim_next` promotes due retries and atomically claims the highest-priority
  ready job with `FOR UPDATE SKIP LOCKED`. The claim increments the attempt and
  issues a unique lease token.
- `heartbeat` renews only an active, unexpired lease with the exact token.
- `recover_expired_leases` moves abandoned active work to an immediate retry,
  preserving its resume state, or to terminal failure when no attempt remains.
- `promote_due_retries` clears the previous transient failure and returns due
  work to `queued`.

The lease token is the ownership credential. A stale worker cannot renew or,
in later steps, commit stage output after recovery assigns a new token.

```python
repository = WorkflowJobRepository()
submission = repository.submit(
    analysis_input,
    idempotency_key="repo:commit:playbook-version",
    model_name="gemini-3.5-flash-lite",
    workflow_version="phase3-v1",
    prompt_version="phase2-v1",
)
job = repository.claim_next("worker-01", lease_seconds=60)
job = repository.heartbeat(job.workflow_job_id, job.lease_token)
```

## Phase 3C retry and analysis execution

Temporary failures use bounded exponential backoff with jitter. With the
default policy, attempts wait approximately 5, 10, 20, 40, and 80 seconds,
up to a five-minute cap. The ±20% jitter prevents many failed jobs from
retrying at the same instant. The attempt budget remains authoritative: a
retryable failure becomes terminal when no attempt remains.

`AnalysisWorker.run_once` performs one safe polling cycle:

```text
claim analyzing job
→ load immutable analysis input
→ renew lease in the background
→ execute bounded Phase 2 orchestrator
→ atomically persist result + analysis_completed checkpoint
→ completed (clean/inconclusive) OR queued for generating_patch (violations)
```

The worker claims only jobs whose `resume_state` is `analyzing`, so this first
worker cannot accidentally consume patch or GitHub work before those stage
handlers exist. A background heartbeat keeps ownership alive during model and
retrieval calls.

Analysis completion is idempotent and transactional. The result audit rows,
violations, terminal `analysis_runs` status, workflow checkpoint, and next job
state commit together. If any write fails, all writes roll back. A repeated
completion after a lost response observes the durable checkpoint and does not
insert duplicate audit rows.

Every failure is converted to a `JobFailure` before persistence. Provider
timeouts, rate limits, and network failures are retryable; malformed model
contracts are permanent. `schedule_failure` requires the current unexpired
lease token, clears the lease, preserves the active resume stage, and either
schedules the calculated delay or terminates an exhausted job. A stale worker
cannot commit output or schedule a failure after another worker owns the job.

## Trade-offs

PostgreSQL is the initial queue because it already owns the workflow's durable
state and can atomically coordinate claims, audit records, and idempotency. This
avoids introducing Redis, Kafka, or a second consistency boundary before
throughput measurements require one.

The lifecycle is custom Python plus SQL rather than LangGraph. At this size,
the explicit transition graph is easier to test and gives direct control over
leases and transactions. LangGraph remains an option if checkpoint/resume and
human-interrupt branching become a measured maintenance bottleneck.

## Phase 3A acceptance criteria

- Every intended happy, clean, retry, rejection, cancellation, and failure path
  is explicit.
- Python rejects illegal transitions before persistence.
- PostgreSQL independently rejects illegal direct updates.
- Checkpoints cannot regress.
- Active states cannot exist without a lease.
- Retry scheduling cannot exist without a retryable classified failure.
- Every status change creates an ordered audit row.
- Existing Phase 1 and Phase 2 tests remain green.

Phase 3B acceptance additionally requires concurrent duplicate submissions to
produce one job and one analysis record, concurrent workers to claim each job
at most once, priority ordering, token-guarded heartbeat renewal, same-stage
recovery, and terminal failure after attempt exhaustion.

Phase 3C acceptance additionally requires bounded exponential backoff and
jitter, explicit retryable/permanent failure behavior, background lease
renewal, analysis-only claims, and atomic idempotent analysis completion.
Migration `007_workflow_stage_handoff.sql` additionally guarantees that an
analysis-to-patch handoff advances the checkpoint, records
`resume_state=generating_patch`, and releases the analysis worker's lease.
