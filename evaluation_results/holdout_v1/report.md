# Phase 1 Retrieval Evaluation

- Run status: **complete**
- Generated: `2026-08-04T09:19:30.308564+00:00`
- Dataset: `phase1-retrieval-holdout-v1` (20/20 cases)
- Corpus: `evaluation_playbook.md` version 1 (31 chunks)
- Embedding requests: 20
- Candidate pool: 20

## Overall results

| Method | R@1 | P@1 | Hit@1 | R@3 | P@3 | Hit@3 | R@5 | P@5 | Hit@5 | MRR | Negative FP@5 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| semantic | 0.900 | 1.000 | 1.000 | 1.000 | 0.400 | 1.000 | 1.000 | 0.240 | 1.000 | 1.000 | 1.000 | 436.73 | 485.38 |
| lexical | 0.200 | 0.200 | 0.200 | 0.200 | 0.067 | 0.200 | 0.200 | 0.040 | 0.200 | 0.200 | 0.000 | 28.12 | 32.11 |
| hybrid | 0.900 | 1.000 | 1.000 | 1.000 | 0.400 | 1.000 | 1.000 | 0.240 | 1.000 | 1.000 | 1.000 | 455.99 | 512.33 |

Precision@K uses K as the denominator. Negative cases are reported separately through false-positive rate.

## Results by query type

### Semantic

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| multi_rule | 2 | 1.000 | 1.000 | — | 436.73 |
| negative | 10 | — | — | 1.000 | 485.38 |
| semantic | 8 | 1.000 | 1.000 | — | 636.79 |

### Lexical

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| multi_rule | 2 | 0.000 | 0.000 | — | 31.55 |
| negative | 10 | — | — | 0.000 | 32.11 |
| semantic | 8 | 0.250 | 0.250 | — | 32.61 |

### Hybrid

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| multi_rule | 2 | 1.000 | 1.000 | — | 464.61 |
| negative | 10 | — | — | 1.000 | 512.33 |
| semantic | 8 | 1.000 | 1.000 | — | 670.16 |

## Rank-1 misses

| Case | Type | Method | Expected | Rank 1 | First expected rank |
|---|---|---|---|---|---|
| holdout-semantic-002 | semantic | lexical | DB-04 | none | not retrieved |
| holdout-semantic-003 | semantic | lexical | REL-04 | none | not retrieved |
| holdout-semantic-005 | semantic | lexical | DB-05 | none | not retrieved |
| holdout-semantic-006 | semantic | lexical | OBS-02 | none | not retrieved |
| holdout-semantic-007 | semantic | lexical | SEC-05 | none | not retrieved |
| holdout-semantic-008 | semantic | lexical | AUTH-02 | API-02 | not retrieved |
| holdout-multi-001 | multi_rule | lexical | API-02, REL-05 | none | not retrieved |
| holdout-multi-002 | multi_rule | lexical | API-05, REL-01 | none | not retrieved |

## Cases failing at K=5

| Case | Type | Method | Expected | Retrieved | Issue |
|---|---|---|---|---|---|
| holdout-semantic-002 | semantic | lexical | DB-04 | none | missing expected rule |
| holdout-semantic-003 | semantic | lexical | REL-04 | none | missing expected rule |
| holdout-semantic-005 | semantic | lexical | DB-05 | none | missing expected rule |
| holdout-semantic-006 | semantic | lexical | OBS-02 | none | missing expected rule |
| holdout-semantic-007 | semantic | lexical | SEC-05 | none | missing expected rule |
| holdout-semantic-008 | semantic | lexical | AUTH-02 | API-02 | missing expected rule |
| holdout-multi-001 | multi_rule | lexical | API-02, REL-05 | none | missing expected rule |
| holdout-multi-002 | multi_rule | lexical | API-05, REL-01 | none | missing expected rule |
| holdout-negative-001 | negative | semantic | none | API-01, API-03, GOV-01, API-04, DB-02 | false positive |
| holdout-negative-001 | negative | hybrid | none | API-01, API-03, GOV-01, API-04, DB-02 | false positive |
| holdout-negative-002 | negative | semantic | none | GOV-01, REL-03, OBS-02, OBS-01, REL-04 | false positive |
| holdout-negative-002 | negative | hybrid | none | GOV-01, REL-03, OBS-02, OBS-01, REL-04 | false positive |
| holdout-negative-003 | negative | semantic | none | API-04, API-01, API-02, GOV-01, REL-01 | false positive |
| holdout-negative-003 | negative | hybrid | none | API-04, API-01, API-02, GOV-01, REL-01 | false positive |
| holdout-negative-004 | negative | semantic | none | GOV-01, DEP-01, SEC-05, DB-05, API-01 | false positive |
| holdout-negative-004 | negative | hybrid | none | GOV-01, DEP-01, SEC-05, DB-05, API-01 | false positive |
| holdout-negative-005 | negative | semantic | none | GOV-01, REL-03, SEC-05, DEP-01, SEC-03 | false positive |
| holdout-negative-005 | negative | hybrid | none | GOV-01, REL-03, SEC-05, DEP-01, SEC-03 | false positive |
| holdout-negative-006 | negative | semantic | none | GOV-01, DEP-01, DB-02, OBS-03, SEC-05 | false positive |
| holdout-negative-006 | negative | hybrid | none | GOV-01, DEP-01, DB-02, OBS-03, SEC-05 | false positive |
| holdout-negative-007 | negative | semantic | none | GOV-01, OBS-01, API-01, SEC-05, SEC-02 | false positive |
| holdout-negative-007 | negative | hybrid | none | GOV-01, OBS-01, API-01, SEC-05, SEC-02 | false positive |
| holdout-negative-008 | negative | semantic | none | SEC-05, GOV-01, DB-03, DEP-01, REL-03 | false positive |
| holdout-negative-008 | negative | hybrid | none | SEC-05, GOV-01, DB-03, DEP-01, REL-03 | false positive |
| holdout-negative-009 | negative | semantic | none | GOV-01, DEP-01, SEC-05, DATA-01, OBS-03 | false positive |
| holdout-negative-009 | negative | hybrid | none | GOV-01, DEP-01, SEC-05, DATA-01, OBS-03 | false positive |
| holdout-negative-010 | negative | semantic | none | GOV-01, OBS-03, DEP-01, API-01, SEC-05 | false positive |
| holdout-negative-010 | negative | hybrid | none | GOV-01, OBS-03, DEP-01, API-01, SEC-05 | false positive |
