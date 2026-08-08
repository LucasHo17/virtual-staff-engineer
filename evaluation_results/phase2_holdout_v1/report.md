# Phase 2 Agent Evaluation

- Run status: **complete**
- Generated: `2026-08-07T17:38:54.686979+00:00`
- Dataset: `phase2-agent-holdout-v1` (20/20 cases)
- Model: `gemini-3.5-flash-lite`
- Thinking budget: model default
- Delay between cases: 15.0 seconds
- Corpus: `evaluation_playbook.md` version 1

## Quality

| Precision | Recall | F1 | Exact rules | Status accuracy |
|---|---|---|---|---|
| 0.833 | 1.000 | 0.909 | 0.950 | 0.950 |

| Violating detection | Clean FP | Irrelevant FP | Ambiguous inconclusive |
|---|---|---|---|
| 1.000 | 0.200 | 0.000 | 1.000 |

## Safety and workflow

- Deterministic rejection rate: 0.000 (0 proposals)
- Evaluator unsupported rate: 0.000 (0 decisions)
- Average queries: 1.80
- Average iterations: 1.00
- Latency p50/p95: 2615.86 / 4224.65 ms
- Model calls: 46
- Input/output/thinking tokens: 69659 / 3880 / 0
- Embedding requests: 36
- Estimated reasoning cost: $0.030598

The cost estimate uses the explicit per-million-token rates recorded in the report configuration. Embedding cost is not included.

## Results by case type

| Type | Cases | Status accuracy | Exact rules | FP rate | Inconclusive rate |
|---|---|---|---|---|---|
| ambiguous | 5 | 1.000 | 1.000 | 0.000 | 1.000 |
| clean | 5 | 0.800 | 0.800 | 0.200 | 0.000 |
| irrelevant | 5 | 1.000 | 1.000 | 0.000 | 0.000 |
| violating | 5 | 1.000 | 1.000 | 0.000 | 0.000 |
Overall case failures: **1**

## Case results

### holdout-violating-001 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `DB-01`
- Actual status/rules: `review_required` / `DB-01`
- Queries/iterations: 2 / 1
- Latency: 4200.66 ms

### holdout-violating-002 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `API-02`
- Actual status/rules: `review_required` / `API-02`
- Queries/iterations: 2 / 1
- Latency: 4224.65 ms

### holdout-violating-003 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `SEC-02`
- Actual status/rules: `review_required` / `SEC-02`
- Queries/iterations: 2 / 1
- Latency: 4215.06 ms

### holdout-violating-004 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `AUTH-02`
- Actual status/rules: `review_required` / `AUTH-02`
- Queries/iterations: 2 / 1
- Latency: 4121.39 ms

### holdout-violating-005 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `OBS-02`
- Actual status/rules: `review_required` / `OBS-02`
- Queries/iterations: 2 / 1
- Latency: 4118.79 ms

### holdout-clean-001 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2555.51 ms

### holdout-clean-002 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2615.86 ms

### holdout-clean-003 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2158.10 ms

### holdout-clean-004 — FAIL

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `review_required` / `AUTH-02`
- Queries/iterations: 2 / 1
- Latency: 4711.02 ms

### holdout-clean-005 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2142.60 ms

### holdout-ambiguous-001 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 2949.92 ms
- Inconclusive reason: The submitted input consists only of a single-line function call 'persist_checkout(purchase, inventory, receipt)' without any internal implementation details. The code does not show whether database transactions, error handling, or atomicity are implemented. Therefore, required implementation details are absent and more input is needed to evaluate compliance with Rule DB-01.

### holdout-ambiguous-002 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 1 / 1
- Latency: 2073.18 ms
- Inconclusive reason: The submitted design document only contains a high-level statement that the transfer endpoint protects against duplicate submissions (line 1), but lacks required implementation details such as how idempotency keys are bound, stored, and verified according to Rule API-02.

### holdout-ambiguous-003 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 2842.87 ms
- Inconclusive reason: The input line calls load_database_password(), but the implementation details of how the password is obtained and loaded are absent, so it cannot be determined whether an approved secret manager or secure environment variable is used.

### holdout-ambiguous-004 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 2658.40 ms
- Inconclusive reason: The input only shows a function call to authorize_invoice_access, but lacks the necessary implementation details to verify if authorization is correctly enforced on the server for every protected operation according to Rule AUTH-02.

### holdout-ambiguous-005 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 2947.62 ms
- Inconclusive reason: The input only shows a function call to record_request_metrics without showing the implementation details, label sets, or metric definitions, making it impossible to determine if bounded sets are used or if any violations of Rule OBS-02 or other observability rules actually occur.

### holdout-irrelevant-001 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2532.82 ms

### holdout-irrelevant-002 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2491.04 ms

### holdout-irrelevant-003 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2565.90 ms

### holdout-irrelevant-004 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2550.50 ms

### holdout-irrelevant-005 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2115.64 ms
