# Phase 4 optimization evidence

## Decision under test

The level-10 baseline showed responsive FastAPI health checks but model quota
failures and long end-to-end latency. The measured change added two independently
leased analysis workers and a shared in-process limit of 15 Gemini generation
requests per minute. Patch generation and validation remained single-worker
stages.

The identical clean, ten-job workload was used before and after the change:

- before: `evaluation_results/phase4_load/load-003/results.json`;
- after: `evaluation_results/phase4_load/v1/results.json` (`run_id=load-004`).

## Before and after

| Metric | load-003 | load-004 | Change |
|---|---:|---:|---:|
| Completed jobs | 10/10 | 10/10 | unchanged |
| Unexpected failures | 0 | 0 | unchanged |
| Provider retries | 2 | 0 | eliminated |
| Submission p95 | 51.559 ms | 39.062 ms | 24.2% lower |
| Health p95 | 3.745 ms | 3.931 ms | 5.0% higher |
| Queue p50 | 12.198 s | 29.642 s | 143.0% higher |
| Queue p95 | 24.240 s | 61.440 s | 153.5% higher |
| Automated processing p50 | 15.102 s | 41.282 s | 173.4% higher |
| Automated processing p95 | 80.647 s | 77.314 s | 4.1% lower |
| Throughput | 7.363 jobs/min | 7.724 jobs/min | 4.9% higher |

## Interpretation

The proactive limiter removed quota retries and modestly improved throughput
and tail processing latency. It also converted burst-and-retry behavior into
intentional waiting: with only 15 model requests per minute and roughly two
generation calls per clean job, additional analysis workers could not materially
increase total capacity. Later jobs remained queued while the two claimed jobs
waited for model request slots, increasing queue and median processing latency.

The measured bottleneck is the upstream Gemini free-tier request quota, not the
FastAPI request path or PostgreSQL queue. Increasing worker concurrency further,
adding Redis, or introducing a Go gateway would not address that constraint.

## Decision

Keep configurable worker concurrency and the shared limiter because they provide
a reliable operating mode and reusable controls for a future higher quota. Use
two analysis workers and 15 requests per minute for the current reliability-first
demo, and record the latency trade-off. Do not add more infrastructure without a
new benchmark showing a different bottleneck. If provider quota increases, rerun
the identical level-10 workload before changing architecture.
