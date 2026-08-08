# Phase 2 Agent Evaluation

- Run status: **partial**
- Generated: `2026-08-07T13:57:37.522315+00:00`
- Dataset: `phase2-workflow-acceptance-v1` (4/20 cases)
- Model: `gemini-3.5-flash-lite`
- Thinking budget: model default
- Corpus: `evaluation_playbook.md` version 1

## Quality

| Precision | Recall | F1 | Exact rules | Status accuracy |
|---|---|---|---|---|
| 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

| Violating detection | Clean FP | Irrelevant FP | Ambiguous inconclusive |
|---|---|---|---|
| 1.000 | 0.000 | 0.000 | 1.000 |

## Safety and workflow

- Deterministic rejection rate: 0.000 (0 proposals)
- Evaluator unsupported rate: 0.000 (0 decisions)
- Average queries: 1.75
- Average iterations: 1.00
- Latency p50/p95: 2549.68 / 4351.57 ms
- Model calls: 9
- Input/output/thinking tokens: 11246 / 769 / 0
- Embedding requests: 7
- Estimated reasoning cost: $0.005296

The cost estimate uses the explicit per-million-token rates recorded in the report configuration. Embedding cost is not included.

## Results by case type

| Type | Cases | Status accuracy | Exact rules | FP rate | Inconclusive rate |
|---|---|---|---|---|---|
| ambiguous | 1 | 1.000 | 1.000 | 0.000 | 1.000 |
| clean | 1 | 1.000 | 1.000 | 0.000 | 0.000 |
| irrelevant | 1 | 1.000 | 1.000 | 0.000 | 0.000 |
| violating | 1 | 1.000 | 1.000 | 0.000 | 0.000 |
Overall case failures: **0**

## Case results

### violating-001 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `SEC-01`
- Actual status/rules: `review_required` / `SEC-01`
- Queries/iterations: 2 / 1
- Latency: 4351.57 ms

### clean-001 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2250.20 ms

### ambiguous-001 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 3216.79 ms
- Inconclusive reason: The provided code snippet only shows a single function call 'audit_authentication(authentication_result)' but lacks implementation details such as the contents of the audit payload, handling of sensitive data fields, and where the authentication result comes from. Therefore, it is impossible to determine whether sensitive information like passwords or tokens are improperly logged or if the audit record complies with rules OBS-04 and SEC-01.

### irrelevant-001 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2549.68 ms
