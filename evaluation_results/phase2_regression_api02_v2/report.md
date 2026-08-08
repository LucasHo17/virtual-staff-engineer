# Phase 2 Agent Evaluation

- Run status: **partial**
- Generated: `2026-08-07T16:41:23.632169+00:00`
- Dataset: `phase2-workflow-acceptance-v1` (1/20 cases)
- Model: `gemini-3.5-flash-lite`
- Thinking budget: model default
- Delay between cases: 0.0 seconds
- Corpus: `evaluation_playbook.md` version 1

## Quality

| Precision | Recall | F1 | Exact rules | Status accuracy |
|---|---|---|---|---|
| 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

| Violating detection | Clean FP | Irrelevant FP | Ambiguous inconclusive |
|---|---|---|---|
| 1.000 | 0.000 | 0.000 | 0.000 |

## Safety and workflow

- Deterministic rejection rate: 0.000 (0 proposals)
- Evaluator unsupported rate: 0.000 (0 decisions)
- Average queries: 2.00
- Average iterations: 1.00
- Latency p50/p95: 4604.01 / 4604.01 ms
- Model calls: 3
- Input/output/thinking tokens: 4728 / 388 / 0
- Embedding requests: 2
- Estimated reasoning cost: $0.002388

The cost estimate uses the explicit per-million-token rates recorded in the report configuration. Embedding cost is not included.

## Results by case type

| Type | Cases | Status accuracy | Exact rules | FP rate | Inconclusive rate |
|---|---|---|---|---|---|
| violating | 1 | 1.000 | 1.000 | 0.000 | 0.000 |
Overall case failures: **0**

## Case results

### violating-005 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `API-02`
- Actual status/rules: `review_required` / `API-02`
- Queries/iterations: 2 / 1
- Latency: 4604.01 ms
