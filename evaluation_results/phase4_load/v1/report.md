# Phase 4 Concurrent Load Test

- Run ID: `load-004`
- Configured levels: 10
- Completed levels: 10
- Safety abort triggered: no

## Wave comparison

| Concurrent jobs | Clean | Unexpected | Submit p95 ms | Health p95 ms | Queue p95 ms | Processing p95 ms | Throughput jobs/min | Retries |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 10 | 0 | 39.062 | 3.931 | 61439.955 | 77314.155 | 7.724 | 0 |

## Interpretation boundary

The test uses clean design inputs and never approves patches or calls GitHub. It measures the API, PostgreSQL queue, configured worker concurrency, and model-provider path. Provider quotas can become the measured bottleneck and must be reported separately from application defects.
