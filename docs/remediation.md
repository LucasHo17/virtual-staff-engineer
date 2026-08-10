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

These checks validate the proposal contract, not whether the patch applies,
compiles, passes tests, or remains within an acceptable semantic scope. Those
belong to the next `validating_patch` stage. No file or GitHub mutation occurs
during generation.

## Framework decision

The existing custom Python/PostgreSQL state machine still provides the needed
checkpoint, retry, lease, and handoff behavior directly. Patch generation did
not create a recovery problem that LangGraph would materially simplify, so no
agent framework is added at this stage.
