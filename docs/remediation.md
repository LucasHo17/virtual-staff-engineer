# Patch generation

Patch generation is a proposal stage, not a source mutation. It consumes only
validated violations, their immutable rule snapshots, exact line locations,
and a read-only source snapshot.

```text
queued [resume: generating_patch]
  → claim + lease
  → load validated violations and cited rules
  → load exact source snapshot
  → generate structured one-file unified diff
  → verify violation, rule, and source identities
  → persist proposal and patch_generated checkpoint atomically
  → queued [resume: validating_patch]
```

## Stored provenance

Migration `008_patch_proposals.sql` adds:

- `patch_proposals`: source path and revision, original content and SHA-256,
  generated unified diff, explanation, model, and prompt version;
- `patch_proposal_rules`: the exact rule keys, playbook chunk identities, and
  immutable rule snapshots addressed by the proposal;
- existing `remediation_action_violations`: every validated violation the
  proposal claims to address.

The proposal is one-to-one with a remediation action. One action may address
multiple violations, but the first implementation requires all violations to
target the same source file. Multi-file remediation should be introduced only
with a deliberate atomicity and validation design.

## Source boundary

`FilesystemSourceProvider` reads the current working-tree file and refuses to
label it as a historical revision. `GitSourceProvider` uses a full commit SHA to
read the exact Git blob. Both reject paths outside the configured repository
root and never write source files.

Storing original source makes later stale-source validation and reproducible
review possible, but increases database sensitivity and storage. Production
deployment therefore needs restricted database access and an explicit source
retention policy.

## Deterministic generation checks

Before persistence, the application requires:

- a standard unified diff for exactly the requested source path;
- exactly one modified file;
- every and only the persisted validated violation IDs;
- every and only the persisted cited rule keys and snapshots; and
- matching source path and commit revision.

Generation checks validate the proposal contract, not whether the patch
applies, parses, compiles, or passes tests. The deterministic validation stage
below handles safe application and supported syntax checks. No file or GitHub
mutation occurs during either stage.

## Deterministic patch validation

Migration `009_patch_validation.sql` stores one immutable validation run per
proposal and its ordered individual check results. The validation worker:

```text
queued [resume: validating_patch]
  → compare stored content with stored SHA-256
  → compare current working-tree source with generation baseline
  → parse and apply the unified diff in memory
  → enforce the configured changed-line budget
  → parse Python or JSON syntax when supported
  → save every result + patch_validated checkpoint atomically
  → awaiting_approval OR failed [patch_invalid]
```

The worker never writes the reconstructed content to disk. A stale file,
mismatched hunk, excessive patch, or syntax error becomes a persisted invalid
validation rather than a retry. Infrastructure timeouts remain retryable.

The current validator performs deterministic Python and JSON parsing. It does
not yet compile arbitrary languages or run repository test commands; those
require an isolated execution policy with explicit allowlisted commands,
resource limits, and timeouts.

## Human approval boundary

Migration `010_human_approval.sql` stores one immutable decision tied to the
exact workflow job, remediation action, patch proposal, and successful
validation run. A reviewer can inspect the complete review package without
changing state:

```bash
python scripts/review_patch.py <workflow-job-id>
```

An explicit manual decision requires a reviewer label:

```bash
python scripts/review_patch.py <workflow-job-id> \
  --decision approved \
  --actor reviewer@example.com \
  --comment "Validated patch is safe to propose."
```

Use `--decision rejected` to reject it. Identical repeated decisions are
idempotent; changing a recorded decision is a conflict. Approval moves the job
to `approved`; rejection moves it to the terminal `rejected` state. A manually
asserted `--actor` remains audit evidence but cannot authorize GitHub mutation.

For a mutation-eligible approval, `--github-auth` resolves the reviewer from
GitHub's authenticated `/user` response using `GITHUB_TOKEN`:

```bash
python scripts/review_patch.py <workflow-job-id> \
  --decision approved --github-auth
python scripts/run_github_pr_worker.py
```

Migration `012_github_pr_operations.sql` adds authenticated identity provenance
and durable GitHub operation state. The PR worker accepts only a
`github_token`-authenticated approval, creates a deterministic branch from the
analyzed commit, verifies the approved source and result hashes, and reconciles
the branch and PR before each mutation. It never writes directly to the default
branch.

## Framework decision

The existing custom Python/PostgreSQL state machine still provides the needed
checkpoint, retry, lease, and handoff behavior directly. Patch generation and
validation did not create a recovery problem that LangGraph would materially
simplify, so no agent framework is added at this stage.
