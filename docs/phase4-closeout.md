# Phase 4 closeout

## Outcome

The planned Phase 4 scope is complete. The local product accepts a code diff or
design document through FastAPI and Next.js, persists a durable asynchronous
job, streams safe progress, retrieves cited playbook evidence, runs the bounded
analysis workflow, creates and validates a patch when supported violations are
found, and pauses for an authenticated human decision. An approved job can use
the Phase 3 idempotent GitHub adapter to reconcile a branch, commit, and pull
request without writing directly to the default branch.

## Acceptance evidence

| Requirement | Evidence |
|---|---|
| Responsive asynchronous API | Model calls execute in workers; final health p95 was 3.931 ms. |
| Observable workflow | Durable transitions, safe SSE events, stage timings, queue time, retries, tokens, and estimated analysis cost are exposed. |
| Human safety boundary | A validated immutable patch must receive an authenticated reviewer decision before GitHub mutation. |
| Reproducible workload | Frozen clean, violating, and stale-source cases plus deterministic failure scenarios are available. |
| Concurrent baseline | The level-10 `load-004` run completed 10/10 jobs with no unexpected failures. |
| Failure recovery | Provider 429s are classified, respect retry hints, persist retry state, and reconcile completed external mutations. |
| Measured optimization | Two analysis workers plus a 15-request/minute limiter eliminated retries and improved throughput by 4.9%, with the documented queue-latency trade-off. |

Detailed before/after data is in
[`phase4-optimization.md`](phase4-optimization.md). Raw results are stored under
`evaluation_results/phase4_load/`.

## Engineering conclusion

The final experiment did not justify Redis, Kafka, Kubernetes, a Go gateway, or
additional service boundaries. API responsiveness remained stable while the
Gemini free-tier generation quota controlled throughput. Increasing local
worker count without increasing that quota shifts time between queued and active
states rather than creating meaningful capacity.

This is the intended system-first result: the architecture was changed only
after measurement, the change was rerun against the same workload, and both the
improvement and regression were recorded.

## Completion boundary

“Phase 4 complete” means the planned local implementation, deterministic tests,
live model workload, and measured optimization are complete. It does not claim
production readiness or public deployment. The following remain optional,
separately authorized follow-up work:

1. Run one end-to-end acceptance case against a disposable real GitHub
   repository and verify the created PR manually.
2. Add CI and deploy the existing modular monolith if a hosted demo is needed.
3. Replace MVP API keys with an external identity provider before multi-user
   production use.
4. Upgrade from Python 3.9 and LibreSSL, then rerun the complete suite.
5. Repeat the identical level-10 benchmark after any provider-quota change.
