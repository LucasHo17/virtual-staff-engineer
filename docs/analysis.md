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

The future orchestrator must also perform deterministic checks that an input
excerpt really occurs at the cited lines and that the cited chunk was actually
returned by retrieval. An evaluator decision cannot override those checks.

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

## Why confidence is not acceptance

`ProposedFinding.confidence` records the analyst model's estimate. It never
decides whether a finding is valid. This prevents an unsupported but
high-confidence generation from bypassing the evaluator and preserves an
explicit no-finding outcome for irrelevant inputs.
