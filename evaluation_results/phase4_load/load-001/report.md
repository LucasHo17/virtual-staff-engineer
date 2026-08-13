# Phase 4 Concurrent Load Test

- Run ID: `load-001`
- Configured levels: 1, 5
- Completed levels: 1, 5
- Safety abort triggered: no

## Wave comparison

| Concurrent jobs | Clean | Unexpected | Submit p95 ms | Health p95 ms | Queue p95 ms | Processing p95 ms | Throughput jobs/min | Retries |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 0 | 39.387 | 5.2 | 19.173 | 3304.124 | 14.121 | 0 |
| 5 | 5 | 0 | 29.783 | 3.858 | 12045.326 | 17895.881 | 16.046 | 0 |

## Interpretation boundary

The test uses clean design inputs and never approves patches or calls GitHub. It measures the API/PostgreSQL queue/single-worker path. Provider quotas can become the measured bottleneck and must be reported separately from application defects.
