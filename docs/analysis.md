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
20-case draft covering violating, clean, ambiguous, and irrelevant inputs. A
scripted reasoner and retrieval tool exercise the complete bounded workflow
without external model calls:

- violating inputs produce evaluator-supported findings;
- clean inputs deliberately produce analyst proposals that the evaluator
  rejects;
- ambiguous inputs request context until the iteration limit and finish
  `inconclusive`; and
- irrelevant inputs receive retrieval candidates but produce no proposals.

This proves workflow behavior but does not measure agent intelligence. The
dataset must remain excluded from quality claims until its labels are manually
reviewed and a real Gemini run is measured in Step 6.
