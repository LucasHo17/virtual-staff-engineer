# Phase 4 Concurrent Load Test

- Run ID: `load-003`
- Configured levels: 10
- Completed levels: 10
- Safety abort triggered: no

## Wave comparison

| Concurrent jobs | Clean | Unexpected | Submit p95 ms | Health p95 ms | Queue p95 ms | Processing p95 ms | Throughput jobs/min | Retries |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 10 | 0 | 51.559 | 3.745 | 24240.131 | 80646.961 | 7.363 | 2 |

## Interpretation boundary

The test uses clean design inputs and never approves patches or calls GitHub. It measures the API/PostgreSQL queue/single-worker path. Provider quotas can become the measured bottleneck and must be reported separately from application defects.
