# Phase 3 closeout

Phase 3 is functionally complete. The implementation now carries a supported
finding through durable execution, patch generation, deterministic validation,
human approval, and idempotent GitHub pull-request creation.

## Acceptance result

| Capability | Result | Evidence |
|---|---|---|
| Async durable jobs | Pass | PostgreSQL queue, priority claims, `SKIP LOCKED`, leases, and heartbeats |
| Retry and recovery | Pass | Classified failures, bounded backoff, attempt limits, same-stage resume |
| Idempotency | Pass | Request identity constraints, idempotent completion, GitHub reconciliation |
| Persistent checkpoints | Pass | Monotonic checkpoints from `submitted` through `pr_created` |
| Patch safety | Pass for current scope | One-file diff, hashes, in-memory apply, change budget, Python/JSON syntax |
| Human approval | Pass | Immutable decision pinned to the proposal and validation result |
| Authenticated mutation | Pass | Only GitHub-token-authenticated approvals enter the PR worker |
| Audit trail | Pass | Evidence, transitions, proposals, checks, decisions, and PR operation state |
| Historical protection | Pass | Restrictive foreign keys and immutable evidence records |

The full regression suite passed **150 tests** after migration `012` was
applied. GitHub behavior is tested through a stateful fake transport; tests do
not mutate a real repository.

## Metric status

The Phase 3 metric names are defined, but production rates have not been
measured yet:

| Metric | Current status | Next measurement |
|---|---|---|
| Job success rate | Not measured | Run a representative batch through every worker |
| Retry recovery rate | Behavior tested, rate not measured | Inject temporary failures in a batch run |
| Duplicate PR rate | Retry convergence tested, live rate not measured | Run fault-injected GitHub sandbox trials |
| Invalid patch rate | Rejection behavior tested, model rate not measured | Generate patches for a labeled remediation set |
| Mean processing time | Not measured end to end | Instrument stage and total durations |

Test pass rate is intentionally not reported as job success rate. The former
proves expected behavior for known cases; the latter requires workload data.

## Known boundaries

- The deterministic validator parses Python and JSON but does not run arbitrary
  repository build or test commands.
- GitHub authentication proves token ownership; reviewer authorization policy
  such as team membership or required approvers is not implemented.
- Real GitHub API permissions and failure modes still need a sandbox-repository
  acceptance run before production use.
- Worker processes currently run as CLI polling cycles rather than a deployed
  continuously supervised service.

These are inputs to Phase 4 measurement and hardening, not reasons to add Go,
Redis, Kafka, Kubernetes, or LangGraph without a demonstrated bottleneck.

## Phase 4 entry condition

Phase 4 starts by adding observability and a reproducible end-to-end workload.
That baseline should measure throughput, stage latency, error/retry outcomes,
token usage, and duplicate external mutations before any architecture change.
