# Phase 4 Baseline

- Workload: `phase4-workload-v1`
- Runs: 1
- Jobs: 3
- Workload acceptance: 100.00%
- Unexpected failures: 0
- Expected safety blocks: 1

> This is an exploratory smoke baseline with fewer than 20 jobs. Its p95 values are directional, not statistically stable.

## Latency

| Metric | Samples | Mean ms | p50 ms | p95 ms |
|---|---:|---:|---:|---:|
| Queue wait | 3 | 741.406 | 985.031 | 1037.359 |
| Automated processing | 3 | 4863.125 | 5110.026 | 6444.367 |
| Human wait | 1 | 1008.132 | 1008.132 | 1008.132 |
| End to end | 3 | 5199.169 | 5110.026 | 7452.499 |

## Throughput, retries, and usage

- Jobs/minute: 11.262
- Jobs with retry: 0
- Retry recovery rate: N/A
- Input tokens: 13936
- Output tokens: 796
- Retrieval tool calls: 6
- Estimated analysis cost: N/A

`attempt_count` is not reported as retries because it counts worker stage claims. Retry metrics use explicit `retry_scheduled` transitions.
