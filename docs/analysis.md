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

## Why confidence is not acceptance

`ProposedFinding.confidence` records the analyst model's estimate. It never
decides whether a finding is valid. This prevents an unsupported but
high-confidence generation from bypassing the evaluator and preserves an
explicit no-finding outcome for irrelevant inputs.
