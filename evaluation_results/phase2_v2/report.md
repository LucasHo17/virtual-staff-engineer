# Phase 2 Agent Evaluation

- Run status: **complete**
- Generated: `2026-08-07T16:48:39.139651+00:00`
- Dataset: `phase2-workflow-acceptance-v1` (20/20 cases)
- Model: `gemini-3.5-flash-lite`
- Thinking budget: model default
- Delay between cases: 15.0 seconds
- Corpus: `evaluation_playbook.md` version 1

## Quality

| Precision | Recall | F1 | Exact rules | Status accuracy |
|---|---|---|---|---|
| 0.833 | 1.000 | 0.909 | 0.950 | 1.000 |

| Violating detection | Clean FP | Irrelevant FP | Ambiguous inconclusive |
|---|---|---|---|
| 0.800 | 0.000 | 0.000 | 1.000 |

## Safety and workflow

- Deterministic rejection rate: 0.000 (0 proposals)
- Evaluator unsupported rate: 0.000 (0 decisions)
- Average queries: 1.80
- Average iterations: 1.00
- Latency p50/p95: 2781.87 / 4210.64 ms
- Model calls: 45
- Input/output/thinking tokens: 64678 / 3940 / 0
- Embedding requests: 36
- Estimated reasoning cost: $0.029253

The cost estimate uses the explicit per-million-token rates recorded in the report configuration. Embedding cost is not included.

## Results by case type

| Type | Cases | Status accuracy | Exact rules | FP rate | Inconclusive rate |
|---|---|---|---|---|---|
| ambiguous | 5 | 1.000 | 1.000 | 0.000 | 1.000 |
| clean | 5 | 1.000 | 1.000 | 0.000 | 0.000 |
| irrelevant | 5 | 1.000 | 1.000 | 0.000 | 0.000 |
| violating | 5 | 1.000 | 0.800 | 0.200 | 0.000 |
Overall case failures: **1**

## Case results

### violating-001 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `SEC-01`
- Actual status/rules: `review_required` / `SEC-01`
- Queries/iterations: 2 / 1
- Latency: 4297.58 ms

### violating-002 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `SEC-03`
- Actual status/rules: `review_required` / `SEC-03`
- Queries/iterations: 2 / 1
- Latency: 4102.18 ms

### violating-003 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `AUTH-01`
- Actual status/rules: `review_required` / `AUTH-01`
- Queries/iterations: 2 / 1
- Latency: 4210.64 ms

### violating-004 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `DB-01`
- Actual status/rules: `review_required` / `DB-01`
- Queries/iterations: 2 / 1
- Latency: 4063.57 ms

### violating-005 — FAIL

- Type: `violating`
- Expected status/rules: `review_required` / `API-02`
- Actual status/rules: `review_required` / `API-02, REL-01`
- Queries/iterations: 1 / 1
- Latency: 4052.46 ms

### clean-001 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2595.41 ms

### clean-002 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2933.37 ms

### clean-003 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2048.36 ms

### clean-004 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2772.30 ms

### clean-005 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2976.74 ms

### ambiguous-001 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 2944.52 ms
- Inconclusive reason: The provided input consists of a single function call line, which lacks the necessary implementation details to determine if authentication auditing, sensitive data handling, or token validation rules are violated.

### ambiguous-002 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 3022.04 ms
- Inconclusive reason: The submitted input consists of a single function call line 'run_report(requested_report)' without the underlying implementation details, report tier determination, input validation, or query execution logic. Therefore, it is impossible to verify compliance with the retrieved rules without making assumptions about unseen surrounding code.

### ambiguous-003 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 2781.87 ms
- Inconclusive reason: The input states that the shared identity library validates incoming access tokens, but it lacks required implementation details such as whether signature, issuer, audience, expiration time, and not-before time are all explicitly verified, or how the signing algorithm is configured.

### ambiguous-004 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 2807.94 ms
- Inconclusive reason: The submitted input only contains a function signature `save_order_and_items(order, items)` without any implementation details. It is impossible to determine whether database transactions, input validation, or other rules are violated without seeing the body of the function.

### ambiguous-005 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 1 / 1
- Latency: 2059.80 ms
- Inconclusive reason: The submitted input only contains a high-level statement that duplicate-request protection is included. It lacks the implementation details and specifications required to verify compliance with Rule API-02, such as how keys are bound to callers and request payloads, how responses are stored, and how payload mismatches are handled.

### irrelevant-001 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2519.00 ms

### irrelevant-002 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2404.88 ms

### irrelevant-003 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2560.59 ms

### irrelevant-004 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2549.07 ms

### irrelevant-005 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2512.70 ms
