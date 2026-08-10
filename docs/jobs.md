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

Phase 3B will add the repository operations that atomically enqueue and claim
jobs using `FOR UPDATE SKIP LOCKED`, renew leases, and recover expired claims.
