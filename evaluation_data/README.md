# Retrieval evaluation data

`retrieval_cases.json` is the reviewed ground-truth source for the Phase 1
retrieval benchmark. It is tied to `evaluation_playbook.md`, category
`evaluation`, database playbook version 1.

## Current status

The dataset is frozen at 65 reviewed cases. The review resolved one labeling
inconsistency by adding `AUTH-02` to `semantic-018`; all other expected rule
sets were approved. Any label or query change now requires a new dataset
version or an explicit review record.

## Labeling rules

- Include every rule that directly answers the query.
- Do not label a rule merely because it contains similar terminology.
- Multi-rule cases must include all independently applicable rules.
- Negative cases use an empty `expected_rule_keys` array.
- If the playbook changes, create a new dataset version or review every label
  against the new immutable playbook version.

## Case distribution

```text
exact       10
semantic    20
fuzzy       10
tier        10
multi_rule  10
negative     5
total       65
```

## Phase 2 workflow acceptance cases

`analysis_workflow_cases.json` contains 20 frozen development cases, balanced
across:

```text
violating    5
clean        5
ambiguous    5
irrelevant   5
total       20
```

These cases serve two purposes: deterministic workflow acceptance with
scripted components and a live development benchmark using the production
Gemini reasoner and hybrid retriever. The scripted suite verifies control flow;
the live runner measures model-dependent quality. In particular:

- violating cases must reach `review_required` with the expected rule;
- clean cases inject a false proposal that the evaluator must reject;
- ambiguous cases must stop as `inconclusive` after bounded context requests;
  and
- irrelevant cases receive a retrieval candidate but must produce no proposal.

The labels were cross-checked against `evaluation_playbook.md` version 1 and
frozen on 2026-08-07. Any input, candidate-rule, or expected-outcome change now
requires a new dataset version or an explicit review record. This is a
development benchmark; a separate holdout is still required before making
final generalization claims.

The first complete live run produced 1.000 precision, 0.600 recall, 0.750 F1,
and 0.900 terminal-status accuracy. All clean, ambiguous, and irrelevant cases
had the expected safety outcome; two violating cases were false negatives.
The detailed generated reports are written under `evaluation_results/` and are
intentionally not treated as source labels.

An optimized rerun improved recall to 1.000 and status accuracy to 1.000 while
preserving all clean, irrelevant, and ambiguous safety outcomes. It also
surfaced one cross-rule labeling question: the payment-retry case labeled
`API-02` also directly matches the idempotency requirement in `REL-01`. The
frozen dataset has not been edited in response. Any adjudicated correction must
create a new dataset version with an explicit review record.

`analysis_holdout_v1.json` is a separate balanced 20-case holdout. All labels
were independently reviewed against the complete playbook and approved with
zero changes on 2026-08-08 before any agent exposure. The dataset is frozen and
was run exactly once without tuning. The result measured 0.833 precision,
1.000 recall, 0.909 F1, and 0.950 terminal-status accuracy. Every violating,
ambiguous, and irrelevant case had the expected outcome; one clean
ownership-scoped authorization example was falsely flagged. The result is final
holdout evidence and must not be used for further prompt selection.

## Phase 4 reproducible workload

`phase4_workload_v1.json` freezes three safe live-stack cases: clean analysis,
a validated SEC-01 patch followed by rejection, and missing-source rejection.
The workload runner submits through FastAPI and observes the asynchronous
workers; it does not mutate source files or invoke GitHub.

Faults that should not be exposed through production HTTP switches—invalid
patches, temporary provider failures, expired leases, and GitHub timeouts after
mutation—are mapped to their deterministic unit/integration tests in the same
workload file. Controlled live fault injection is deferred to Phase 4 failure
testing.
