# Phase 1 Retrieval Evaluation

- Run status: **partial**
- Generated: `2026-08-04T05:19:55.963339+00:00`
- Dataset: `phase1-retrieval-v1` (5/65 cases)
- Corpus: `evaluation_playbook.md` version 1 (31 chunks)
- Embedding requests: 5
- Candidate pool: 20

## Overall results

| Method | R@1 | P@1 | Hit@1 | R@3 | P@3 | Hit@3 | R@5 | P@5 | Hit@5 | MRR | Negative FP@5 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| semantic | 0.800 | 0.800 | 0.800 | 0.800 | 0.267 | 0.800 | 1.000 | 0.200 | 1.000 | 0.850 | — | 476.21 | 686.21 |
| lexical | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | — | 25.23 | 28.90 |
| hybrid | 0.800 | 0.800 | 0.800 | 0.800 | 0.267 | 0.800 | 1.000 | 0.200 | 1.000 | 0.850 | — | 501.59 | 713.99 |

Precision@K uses K as the denominator. Negative cases are reported separately through false-positive rate.

## Results by query type

### Semantic

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| semantic | 5 | 1.000 | 0.850 | — | 686.21 |

### Lexical

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| semantic | 5 | 0.000 | 0.000 | — | 28.90 |

### Hybrid

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| semantic | 5 | 1.000 | 0.850 | — | 713.99 |

## Cases needing review

| Case | Type | Method | Expected | Retrieved | Issue |
|---|---|---|---|---|---|
| semantic-001 | semantic | lexical | SEC-01 | none | missing expected rule |
| semantic-002 | semantic | lexical | SEC-02 | none | missing expected rule |
| semantic-003 | semantic | lexical | SEC-03 | none | missing expected rule |
| semantic-004 | semantic | lexical | SEC-04 | none | missing expected rule |
| semantic-005 | semantic | lexical | SEC-05 | none | missing expected rule |
