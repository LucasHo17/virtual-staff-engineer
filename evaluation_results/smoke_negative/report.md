# Phase 1 Retrieval Evaluation

- Run status: **partial**
- Generated: `2026-08-04T05:22:08.891331+00:00`
- Dataset: `phase1-retrieval-v1` (5/65 cases)
- Corpus: `evaluation_playbook.md` version 1 (31 chunks)
- Embedding requests: 5
- Candidate pool: 20

## Overall results

| Method | R@1 | P@1 | Hit@1 | R@3 | P@3 | Hit@3 | R@5 | P@5 | Hit@5 | MRR | Negative FP@5 | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| semantic | — | — | — | — | — | — | — | — | — | — | 1.000 | 475.48 | 684.32 |
| lexical | — | — | — | — | — | — | — | — | — | — | 0.000 | 25.35 | 32.75 |
| hybrid | — | — | — | — | — | — | — | — | — | — | 1.000 | 501.20 | 712.44 |

Precision@K uses K as the denominator. Negative cases are reported separately through false-positive rate.

## Results by query type

### Semantic

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| negative | 5 | — | — | 1.000 | 684.32 |

### Lexical

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| negative | 5 | — | — | 0.000 | 32.75 |

### Hybrid

| Query type | Cases | Recall@5 | MRR | FP@5 | p95 ms |
|---|---|---|---|---|---|
| negative | 5 | — | — | 1.000 | 712.44 |

## Cases needing review

| Case | Type | Method | Expected | Retrieved | Issue |
|---|---|---|---|---|---|
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
