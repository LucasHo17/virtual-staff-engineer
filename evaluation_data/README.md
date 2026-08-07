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

`analysis_workflow_cases.json` contains 20 draft cases, balanced across:

```text
violating    5
clean        5
ambiguous    5
irrelevant   5
total       20
```

These cases currently test deterministic workflow behavior with scripted
reasoning and retrieval components. They verify control flow, not Gemini
quality. In particular:

- violating cases must reach `review_required` with the expected rule;
- clean cases inject a false proposal that the evaluator must reject;
- ambiguous cases must stop as `inconclusive` after bounded context requests;
  and
- irrelevant cases receive a retrieval candidate but must produce no proposal.

The dataset intentionally remains `draft`. Before it is used for Phase 2 model
metrics, every input and label must be manually reviewed, the review count must
equal 20, and a new frozen version should be created if labels change later.
