# Phase 2 Agent Evaluation

- Run status: **complete**
- Generated: `2026-08-07T14:05:41.078695+00:00`
- Dataset: `phase2-workflow-acceptance-v1` (20/20 cases)
- Model: `gemini-3.5-flash-lite`
- Thinking budget: model default
- Delay between cases: 15.0 seconds
- Corpus: `evaluation_playbook.md` version 1

## Quality

| Precision | Recall | F1 | Exact rules | Status accuracy |
|---|---|---|---|---|
| 1.000 | 0.600 | 0.750 | 0.900 | 0.900 |

| Violating detection | Clean FP | Irrelevant FP | Ambiguous inconclusive |
|---|---|---|---|
| 0.600 | 0.000 | 0.000 | 1.000 |

## Safety and workflow

- Deterministic rejection rate: 0.400 (2 proposals)
- Evaluator unsupported rate: 0.000 (0 decisions)
- Average queries: 1.55
- Average iterations: 1.00
- Latency p50/p95: 2850.62 / 3930.55 ms
- Model calls: 43
- Input/output/thinking tokens: 53669 / 3486 / 0
- Embedding requests: 31
- Estimated reasoning cost: $0.024816

The cost estimate uses the explicit per-million-token rates recorded in the report configuration. Embedding cost is not included.

## Results by case type

| Type | Cases | Status accuracy | Exact rules | FP rate | Inconclusive rate |
|---|---|---|---|---|---|
| ambiguous | 5 | 1.000 | 1.000 | 0.000 | 1.000 |
| clean | 5 | 1.000 | 1.000 | 0.000 | 0.000 |
| irrelevant | 5 | 1.000 | 1.000 | 0.000 | 0.000 |
| violating | 5 | 0.600 | 0.600 | 0.000 | 0.200 |
Overall case failures: **2**

## Case results

### violating-001 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `SEC-01`
- Actual status/rules: `review_required` / `SEC-01`
- Queries/iterations: 1 / 1
- Latency: 3612.77 ms

### violating-002 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `SEC-03`
- Actual status/rules: `review_required` / `SEC-03`
- Queries/iterations: 1 / 1
- Latency: 4545.39 ms

### violating-003 — PASS

- Type: `violating`
- Expected status/rules: `review_required` / `AUTH-01`
- Actual status/rules: `review_required` / `AUTH-01`
- Queries/iterations: 1 / 1
- Latency: 3647.72 ms

### violating-004 — FAIL

- Type: `violating`
- Expected status/rules: `review_required` / `DB-01`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 2947.50 ms
- Inconclusive reason: The input snippet shows order saving and payment charging, but lacks necessary context regarding the application tier, error handling, transaction block setup, or idempotency keys to definitively determine a rule violation.

### violating-005 — FAIL

- Type: `violating`
- Expected status/rules: `review_required` / `API-02`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2693.48 ms

### clean-001 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2954.01 ms

### clean-002 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2666.73 ms

### clean-003 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2274.68 ms

### clean-004 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2850.62 ms

### clean-005 — PASS

- Type: `clean`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2216.27 ms

### ambiguous-001 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 3533.53 ms
- Inconclusive reason: The provided code snippet only shows a function call 'audit_authentication(authentication_result)', but lacks the surrounding implementation details necessary to verify compliance with rules such as OBS-04 (audit event structure, required fields, protection) and SEC-01 (sensitive data handling in logs/audits).

### ambiguous-002 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 3213.21 ms
- Inconclusive reason: The provided code snippet only contains a single line calling a report function with an input variable ('run_report(requested_report)'). Implementation details such as input validation, authorization checks, tier classification, and how 'requested_report' is handled are absent, making it impossible to confirm a rule violation.

### ambiguous-003 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 1 / 1
- Latency: 2722.54 ms
- Inconclusive reason: The design document states that the shared identity library validates incoming access tokens, but it lacks specific implementation details on whether it validates signature, issuer, audience, expiration time, not-before time, and explicitly configures the signing algorithm as required by rule AUTH-01.

### ambiguous-004 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 2 / 1
- Latency: 3196.15 ms
- Inconclusive reason: The provided code snippet only shows a function signature 'save_order_and_items(order, items)' without its body implementation details. Therefore, it is impossible to verify whether database transactions or proper error rollbacks are actually implemented.

### ambiguous-005 — PASS

- Type: `ambiguous`
- Expected status/rules: `inconclusive` / `none`
- Actual status/rules: `inconclusive` / `none`
- Queries/iterations: 1 / 1
- Latency: 2749.90 ms
- Inconclusive reason: The input states that the payment API includes duplicate-request protection, but lacks required implementation details such as whether it supports an idempotency key bound to the caller and request hash, stores/returns terminal responses, and correctly handles payload mismatches as required by rule API-02.

### irrelevant-001 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 1 / 1
- Latency: 2192.76 ms

### irrelevant-002 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 3185.52 ms

### irrelevant-003 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2746.17 ms

### irrelevant-004 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 3930.55 ms

### irrelevant-005 — PASS

- Type: `irrelevant`
- Expected status/rules: `completed_clean` / `none`
- Actual status/rules: `completed_clean` / `none`
- Queries/iterations: 2 / 1
- Latency: 2715.76 ms
