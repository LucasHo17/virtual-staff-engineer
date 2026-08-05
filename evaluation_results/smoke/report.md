# Phase 1 Retrieval Evaluation

- Run status: **partial**
- Generated: `2026-08-04T05:05:56.636364+00:00`
- Dataset: `phase1-retrieval-v1` (5/65 cases)
- Corpus: `evaluation_playbook.md` version 1 (31 chunks)
- Embedding requests: 5
- Candidate pool: 20

## Overall results

| Method | R@1 | P@1 | Hit@1 | R@3 | P@3 | Hit@3 | R@5 | P@5 | Hit@5 | MRR | Negative FP@5 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| semantic | 1.000 | 1.000 | 1.000 | 1.000 | 0.333 | 1.000 | 1.000 | 0.200 | 1.000 | 1.000 | — | 421.95 | 650.14 |
| lexical | 1.000 | 1.000 | 1.000 | 1.000 | 0.333 | 1.000 | 1.000 | 0.200 | 1.000 | 1.000 | — | 27.42 | 31.91 |
| hybrid | 1.000 | 1.000 | 1.000 | 1.000 | 0.333 | 1.000 | 1.000 | 0.200 | 1.000 | 1.000 | — | 449.48 | 682.21 |

Precision@K uses K as the denominator. Negative cases are reported separately through false-positive rate.

## Results by query type

### Semantic

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| exact | 5 | 1.000 | 1.000 | — | 650.14 |

### Lexical

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| exact | 5 | 1.000 | 1.000 | — | 31.91 |

### Hybrid

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| exact | 5 | 1.000 | 1.000 | — | 682.21 |

## Cases needing review

No failures at K=5.
