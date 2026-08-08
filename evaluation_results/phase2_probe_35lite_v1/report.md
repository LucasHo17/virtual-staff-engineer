# Phase 2 Agent Evaluation

- Run status: **partial**
- Generated: `2026-08-07T13:57:03.859009+00:00`
- Dataset: `phase2-workflow-acceptance-v1` (1/20 cases)
- Model: `gemini-3.5-flash-lite`
- Thinking budget: model default
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
- Latency p50/p95: 4612.56 / 4612.56 ms
- Model calls: 3
- Input/output/thinking tokens: 4469 / 384 / 0
- Embedding requests: 2
- Estimated reasoning cost: $0.002301

The cost estimate uses the explicit per-million-token rates recorded in the report configuration. Embedding cost is not included.

## Results by case type

| Type | Cases | Status accuracy | Exact rules | FP rate | Inconclusive rate |
|---|---|---|---|---|---|
| violating | 1 | 1.000 | 1.000 | 0.000 | 0.000 |
Overall case failures: **0**

## Case results

### violating-001 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `SEC-01`
- Actual status/rules: `review_required` / `SEC-01`
- Queries/iterations: 2 / 1
- Latency: 4612.56 ms
