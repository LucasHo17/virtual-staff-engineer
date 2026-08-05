# Phase 1 Retrieval Evaluation

- Run status: **complete**
- Generated: `2026-08-04T06:09:23.835256+00:00`
- Dataset: `phase1-retrieval-v1` (65/65 cases)
- Corpus: `evaluation_playbook.md` version 1 (31 chunks)
- Embedding requests: 65
- Candidate pool: 20

## Overall results

| Method | R@1 | P@1 | Hit@1 | R@3 | P@3 | Hit@3 | R@5 | P@5 | Hit@5 | MRR | Negative FP@5 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| semantic | 0.786 | 0.967 | 0.967 | 0.953 | 0.433 | 0.983 | 1.000 | 0.277 | 1.000 | 0.979 | 1.000 | 448.49 | 583.41 |
| lexical | 0.317 | 0.383 | 0.383 | 0.325 | 0.133 | 0.383 | 0.325 | 0.080 | 0.383 | 0.383 | 0.000 | 29.18 | 31.69 |
| hybrid | 0.769 | 0.950 | 0.950 | 0.953 | 0.433 | 0.983 | 1.000 | 0.277 | 1.000 | 0.971 | 1.000 | 481.56 | 612.79 |

Precision@K uses K as the denominator. Negative cases are reported separately through false-positive rate.

## Results by query type

### Semantic

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| exact | 10 | 1.000 | 1.000 | — | 610.07 |
| fuzzy | 10 | 1.000 | 1.000 | — | 583.09 |
| multi_rule | 10 | 1.000 | 1.000 | — | 526.14 |
| negative | 5 | — | — | 1.000 | 583.41 |
| semantic | 20 | 1.000 | 0.938 | — | 585.03 |
| tier | 10 | 1.000 | 1.000 | — | 450.34 |

### Lexical

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| exact | 10 | 1.000 | 1.000 | — | 31.38 |
| fuzzy | 10 | 0.500 | 0.500 | — | 29.78 |
| multi_rule | 10 | 0.200 | 0.300 | — | 41.06 |
| negative | 5 | — | — | 0.000 | 30.34 |
| semantic | 20 | 0.000 | 0.000 | — | 31.19 |
| tier | 10 | 0.250 | 0.500 | — | 31.69 |

### Hybrid

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| exact | 10 | 1.000 | 1.000 | — | 627.48 |
| fuzzy | 10 | 1.000 | 0.950 | — | 612.51 |
| multi_rule | 10 | 1.000 | 1.000 | — | 553.37 |
| negative | 5 | — | — | 1.000 | 612.79 |
| semantic | 20 | 1.000 | 0.938 | — | 614.47 |
| tier | 10 | 1.000 | 1.000 | — | 481.56 |

## Cases needing review

| Case | Type | Method | Expected | Retrieved | Issue |
|---|---|---|---|---|---|
| semantic-001 | semantic | lexical | SEC-01 | none | missing expected rule |
| semantic-002 | semantic | lexical | SEC-02 | none | missing expected rule |
| semantic-003 | semantic | lexical | SEC-03 | none | missing expected rule |
| semantic-004 | semantic | lexical | SEC-04 | none | missing expected rule |
| semantic-005 | semantic | lexical | SEC-05 | none | missing expected rule |
| semantic-006 | semantic | lexical | AUTH-01 | none | missing expected rule |
| semantic-007 | semantic | lexical | AUTH-02 | none | missing expected rule |
| semantic-008 | semantic | lexical | AUTH-03 | none | missing expected rule |
| semantic-009 | semantic | lexical | AUTH-04 | none | missing expected rule |
| semantic-010 | semantic | lexical | API-01 | none | missing expected rule |
| semantic-011 | semantic | lexical | API-02 | none | missing expected rule |
| semantic-012 | semantic | lexical | API-03 | none | missing expected rule |
| semantic-013 | semantic | lexical | API-04 | none | missing expected rule |
| semantic-014 | semantic | lexical | API-05 | none | missing expected rule |
| semantic-015 | semantic | lexical | DB-01 | none | missing expected rule |
| semantic-016 | semantic | lexical | DB-02 | none | missing expected rule |
| semantic-017 | semantic | lexical | DB-03 | none | missing expected rule |
| semantic-018 | semantic | lexical | DB-04, AUTH-02 | none | missing expected rule |
| semantic-019 | semantic | lexical | DB-05 | none | missing expected rule |
| semantic-020 | semantic | lexical | REL-01 | none | missing expected rule |
| fuzzy-001 | fuzzy | lexical | SEC-01 | AUTH-04 | missing expected rule |
| fuzzy-002 | fuzzy | lexical | SEC-02 | none | missing expected rule |
| fuzzy-003 | fuzzy | lexical | SEC-03 | none | missing expected rule |
| fuzzy-004 | fuzzy | lexical | AUTH-01 | none | missing expected rule |
| fuzzy-007 | fuzzy | lexical | REL-02 | none | missing expected rule |
| tier-001 | tier | lexical | GOV-01, SEC-02 | none | missing expected rule |
| tier-002 | tier | lexical | GOV-01, OBS-01 | OBS-01 | missing expected rule |
| tier-003 | tier | lexical | GOV-01, AUTH-02 | none | missing expected rule |
| tier-004 | tier | lexical | GOV-01, DB-05 | DB-05 | missing expected rule |
| tier-005 | tier | lexical | GOV-01, API-03 | none | missing expected rule |
| tier-006 | tier | lexical | GOV-01, REL-02 | REL-02 | missing expected rule |
| tier-007 | tier | lexical | GOV-01, REL-03 | none | missing expected rule |
| tier-008 | tier | lexical | GOV-01, DEP-01 | none | missing expected rule |
| tier-009 | tier | lexical | GOV-01, DATA-01 | DATA-01 | missing expected rule |
| tier-010 | tier | lexical | GOV-01, OBS-03 | OBS-03 | missing expected rule |
| multi-001 | multi_rule | lexical | REL-01, REL-05, API-02 | none | missing expected rule |
| multi-002 | multi_rule | lexical | AUTH-04, SEC-01 | none | missing expected rule |
| multi-003 | multi_rule | lexical | DB-04, AUTH-02 | none | missing expected rule |
| multi-004 | multi_rule | lexical | API-05, REL-01 | none | missing expected rule |
| multi-005 | multi_rule | lexical | DB-05, DEP-01 | DB-05 | missing expected rule |
| multi-007 | multi_rule | lexical | REL-05, DB-01 | none | missing expected rule |
| multi-008 | multi_rule | lexical | OBS-01, SEC-01 | none | missing expected rule |
| multi-009 | multi_rule | lexical | OBS-02, OBS-03, SEC-01 | none | missing expected rule |
| multi-010 | multi_rule | lexical | REL-02, API-04 | REL-02 | missing expected rule |
| negative-001 | negative | semantic | none | GOV-01, OBS-01, OBS-03, OBS-02, API-04 | false positive |
| negative-001 | negative | hybrid | none | GOV-01, OBS-01, OBS-03, OBS-02, API-04 | false positive |
| negative-002 | negative | semantic | none | GOV-01, OBS-03, DB-03, REL-04, REL-03 | false positive |
| negative-002 | negative | hybrid | none | GOV-01, OBS-03, DB-03, REL-04, REL-03 | false positive |
| negative-003 | negative | semantic | none | GOV-01, DB-02, AUTH-04, OBS-02, SEC-04 | false positive |
| negative-003 | negative | hybrid | none | GOV-01, DB-02, AUTH-04, OBS-02, SEC-04 | false positive |
| negative-004 | negative | semantic | none | GOV-01, DATA-01, AUTH-02, DEP-01, REL-01 | false positive |
| negative-004 | negative | hybrid | none | GOV-01, DATA-01, AUTH-02, DEP-01, REL-01 | false positive |
| negative-005 | negative | semantic | none | GOV-01, OBS-01, OBS-02, DEP-01, SEC-05 | false positive |
| negative-005 | negative | hybrid | none | GOV-01, OBS-01, OBS-02, DEP-01, SEC-05 | false positive |
