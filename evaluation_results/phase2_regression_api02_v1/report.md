# Phase 2 Agent Evaluation

- Run status: **partial**
- Generated: `2026-08-07T16:35:49.378354+00:00`
- Dataset: `phase2-workflow-acceptance-v1` (1/20 cases)
- Model: `gemini-3.5-flash-lite`
- Thinking budget: model default
- Delay between cases: 0.0 seconds
- Corpus: `evaluation_playbook.md` version 1

## Quality

| Precision | Recall | F1 | Exact rules | Status accuracy |
|---|---|---|---|---|
| 0.500 | 1.000 | 0.667 | 0.000 | 1.000 |

| Violating detection | Clean FP | Irrelevant FP | Ambiguous inconclusive |
|---|---|---|---|
| 0.000 | 0.000 | 0.000 | 0.000 |

## Safety and workflow

- Deterministic rejection rate: 0.000 (0 proposals)
- Evaluator unsupported rate: 0.000 (0 decisions)
- Average queries: 1.00
- Average iterations: 1.00
- Latency p50/p95: 4448.26 / 4448.26 ms
- Model calls: 3
- Input/output/thinking tokens: 4100 / 573 / 0
- Embedding requests: 1
- Estimated reasoning cost: $0.002662

The cost estimate uses the explicit per-million-token rates recorded in the report configuration. Embedding cost is not included.

## Results by case type

| Type | Cases | Status accuracy | Exact rules | FP rate | Inconclusive rate |
|---|---|---|---|---|---|
| violating | 1 | 1.000 | 0.000 | 1.000 | 0.000 |
Overall case failures: **1**

## Case results

### violating-005 — FAIL

- Type: `violating`
- Expected status/rules: `review_required` / `API-02`
- Actual status/rules: `review_required` / `API-02, REL-01`
- Queries/iterations: 1 / 1
- Latency: 4448.26 ms
