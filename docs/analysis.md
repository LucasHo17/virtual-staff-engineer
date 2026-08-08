# Analysis contracts

Phase 2 converts Phase 1 retrieval candidates into evidence-backed findings.
Its first boundary is a set of immutable contracts; orchestration and model
providers must depend on these contracts rather than passing unvalidated
dictionaries between steps.

## Contract flow

```text
AnalysisInput
     ↓
SearchQuery ──→ RuleEvidence
                    ↓
              ProposedFinding
                    ↓
              EvaluationResult
               ↙          ↘
        unsupported      supported
          (reject)     (valid finding)
```

- `AnalysisInput` contains either a code diff or design document. Stable line
  numbering allows every finding to cite the submitted input.
- `SearchQuery` records both the query and why the agent requested it. Query
  count and iteration limits belong to the orchestrator, not this value.
- `RuleEvidence` identifies an immutable playbook chunk and its version, while
  preserving retrieval rank and score provenance.
- `ProposedFinding` must cite both a playbook chunk and an exact location and
  excerpt from the analyzed input. It is a proposal, not a confirmed
  violation.
- `EvaluationResult` independently marks each proposal as `supported` or
  `unsupported`. It may request another bounded retrieval query when evidence
  is insufficient.

The orchestrator performs deterministic checks that an input excerpt really
occurs at the cited lines and that the cited chunk was actually returned by
retrieval. An evaluator decision cannot override those checks.

## Deterministic evidence gate

Analyst proposals now pass through `validate_findings` before evaluation. The
gate rejects a proposal when:

- its playbook chunk was not returned during this run;
- its rule key does not match that chunk;
- its source path does not match the analyzed input;
- its cited lines are outside the input;
- its excerpt is not the exact text at those lines; or
- the same rule and location have already been proposed.

Rejected proposals never reach the evaluator, but remain in
`AnalysisResult.rejected_findings` with a stable rejection code and reason.
This makes fabricated-citation and duplicate rates measurable later. A model's
confidence or evaluator verdict cannot bypass this gate.

## Bounded orchestration

`BoundedAnalysisOrchestrator` now controls an in-memory Phase 2 workflow:

```text
plan queries → retrieve evidence → propose findings → evaluate
      ↑                                              │
      └──────── bounded request for context ─────────┘
```

Default safety limits allow two reasoning iterations, three initial queries,
two additional queries, five queries total, and twenty unique evidence chunks.
Duplicate query text and duplicate playbook chunks are removed. If the
evaluator still needs context when a limit is reached, the run returns
`inconclusive` with no accepted findings.

The three terminal states are:

- `completed_clean`: the analyst proposed nothing or every proposal was
  rejected.
- `review_required`: at least one proposal was supported by the evaluator.
- `inconclusive`: the evaluator requested evidence that could not be obtained
  within the configured limits.

The orchestrator currently has no database or model-provider dependency. A
reasoner adapter supplies generation and evaluation, while
`HybridRetrievalTool` exposes the existing Phase 1 retriever through a narrow,
deterministic tool interface.

`GeminiReasoner` is the first production reasoner adapter. It uses separate
structured-output calls for planning, analysis, and evaluation, with
temperature zero and explicit JSON schemas. Its model name must be configured
through `GEMINI_REASONING_MODEL`; the application does not silently pin a
possibly outdated reasoning model. Model calls are not made during unit tests.

## Durable audit trail

`AnalysisService` wraps the in-memory orchestrator with a PostgreSQL run
lifecycle. It creates an `analyzing` run before external work begins, persists
one terminal result transactionally, and marks the run `failed` when
orchestration raises an error.

The audit trail stores:

- the input type, source, exact content, and SHA-256 checksum;
- model, workflow, and prompt versions;
- executed queries in sequence;
- retrieved chunks with rank, score, query, and rule snapshots;
- every deterministic rejection with the original proposal;
- evaluator-supported, unsupported, and undecided findings; and
- only supported findings as validated `violations`.

Every run also links to the exact immutable playbook versions it consulted.
The repository writes the terminal query/evidence/finding graph in one
transaction, so a write failure cannot expose a partially persisted analysis.

## Why confidence is not acceptance

`ProposedFinding.confidence` records the analyst model's estimate. It never
decides whether a finding is valid. This prevents an unsupported but
high-confidence generation from bypassing the evaluator and preserves an
explicit no-finding outcome for irrelevant inputs.

## Workflow acceptance suite

Phase 2 Step 5 uses `evaluation_data/analysis_workflow_cases.json`, a balanced
20-case development set covering violating, clean, ambiguous, and irrelevant inputs. A
scripted reasoner and retrieval tool exercise the complete bounded workflow
without external model calls:

- violating inputs produce evaluator-supported findings;
- clean inputs deliberately produce analyst proposals that the evaluator
  rejects;
- ambiguous inputs request context until the iteration limit and finish
  `inconclusive`; and
- irrelevant inputs receive retrieval candidates but produce no proposals.

This proves workflow behavior but does not measure agent intelligence. The
labels were frozen only after the workflow distinguished missing submitted
input from missing playbook evidence.

## Live agent benchmark

Phase 2 Step 6 runs the production `GeminiReasoner`, hybrid retrieval tool,
deterministic evidence gate, and evaluator against the same frozen 20-case
development set. The runner records rule-level precision/recall/F1, terminal
status accuracy, category-specific safety rates, latency, query and iteration
counts, token usage, embedding requests, and estimated reasoning cost.

The CLI validates both the destination and the exact PostgreSQL playbook
version before paid requests. It supports case and category selection for
smoke tests, uses the model's default reasoning policy unless an explicit
legacy numeric thinking budget is supplied, and can pace cases to respect API
request quotas.

```bash
python scripts/evaluate_analysis.py \
    --model gemini-3.5-flash-lite \
    --case-delay-seconds 15 \
    --output-dir evaluation_results/phase2_v1
```

The first complete baseline on 2026-08-07 measured:

| Metric | Result |
|---|---:|
| Precision | 1.000 |
| Recall | 0.600 |
| F1 | 0.750 |
| Exact-rule accuracy | 0.900 |
| Terminal-status accuracy | 0.900 |
| Clean false-positive rate | 0.000 |
| Irrelevant false-positive rate | 0.000 |
| Ambiguous-inconclusive rate | 1.000 |
| Latency p50 / p95 | 2.85 s / 3.93 s |
| Estimated reasoning cost | $0.024816 |

The system missed two of five violating examples. One `DB-01` example was
classified as lacking sufficient context. One `API-02` proposal was retrieved
and generated, then correctly blocked by the deterministic gate because its
input excerpt was not verbatim. These are development-set diagnostics, not
production-quality claims. Any prompt or workflow optimization must be
confirmed on a separately reviewed holdout to avoid overfitting.

## Development-set optimization

The first iteration addressed both failure mechanisms without relaxing the
evidence gate:

- The Gemini finding schema now asks for inclusive input line coordinates, not
  model-written paths or excerpts. Application code validates the range and
  constructs the exact source path and verbatim excerpt deterministically.
- Missing-input context is reserved for cases where relevant behavior is not
  shown, such as a declaration or function call without an implementation. A
  directly visible conflict with a mandatory rule proceeds to evaluator and
  human review rather than assuming an unseen mitigation.
- The analyst is instructed to prefer the narrowest directly applicable rule
  when several retrieved rules describe the same location and underlying
  defect.

The complete frozen development benchmark was then rerun without changing its
labels:

| Metric | Baseline v1 | Optimized v2 |
|---|---:|---:|
| Precision | 1.000 | 0.833 |
| Recall | 0.600 | 1.000 |
| F1 | 0.750 | 0.909 |
| Exact-rule accuracy | 0.900 | 0.950 |
| Terminal-status accuracy | 0.900 | 1.000 |
| Clean false-positive rate | 0.000 | 0.000 |
| Irrelevant false-positive rate | 0.000 | 0.000 |
| Ambiguous-inconclusive rate | 1.000 | 1.000 |
| Deterministic citation rejections | 2 | 0 |
| Latency p50 | 2.85 s | 2.78 s |

The only non-exact v2 case expected `API-02` but returned both `API-02` and
`REL-01`. Independent inspection shows that `REL-01` also explicitly prohibits
retrying an operation that is neither idempotent nor protected by an
idempotency mechanism. Because the label was frozen before observing the model
output, it remains unchanged in v1. This overlap must be adjudicated explicitly
and, if accepted, represented in a new dataset version rather than silently
editing the benchmark. The v2 result is an optimization signal, not final
generalization evidence.

A separate 20-case holdout exists as
`evaluation_data/analysis_holdout_v1.json`. All labels were independently
reviewed against the full playbook and approved with zero changes on
2026-08-08, before any live-agent exposure. The review explicitly adjudicated
`AUTH-02` as the sole root-cause label for the invoice-ownership case; `OBS-04`
is a downstream audit obligation rather than the violated access-control rule.
The dataset is now frozen for one final, no-tuning evaluation.

## Frozen holdout result

The frozen holdout was run exactly once on 2026-08-08 using the same
`gemini-3.5-flash-lite` model, retrieval configuration, and quota pacing as the
optimized development run. No prompt or label changes were made after seeing
its results.

| Metric | Holdout v1 |
|---|---:|
| Precision | 0.833 |
| Recall | 1.000 |
| F1 | 0.909 |
| Exact-rule accuracy | 0.950 |
| Terminal-status accuracy | 0.950 |
| Violating detection rate | 1.000 |
| Clean false-positive rate | 0.200 |
| Irrelevant false-positive rate | 0.000 |
| Ambiguous-inconclusive rate | 1.000 |
| Latency p50 / p95 | 2.62 s / 4.22 s |
| Estimated reasoning cost | $0.030598 |

All five violating cases returned the exact expected rule. All five ambiguous
cases stopped inconclusively, and all five irrelevant cases returned clean. The
only failure was `holdout-clean-004`: an invoice query explicitly scoped with
`Invoice.for_customer(current_user.id)` was incorrectly flagged as `AUTH-02`.
The analyst and evaluator both recognized the owner scope but still speculated
that resource ownership might be only partially verified. This is retained as
a measured limitation in recognizing positive compliance evidence; the system
was not tuned against the holdout after observing it.
