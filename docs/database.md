# Database setup

Run all pending migrations from the project root:

```bash
python scripts/migrate.py
```

The initializer records each migration filename and SHA-256 checksum in
`schema_migrations`. Applied migrations are skipped on later runs. Never edit an
applied migration; add a new numbered SQL file under
`src/virtual_staff_engineer/database/sql/` instead.

## Baseline migration

`001_complete_schema.sql` is a one-time reset of the disposable prototype
schema. It removes the original four prototype tables and creates the complete
versioned, auditable schema. Because the migration is recorded atomically, its
reset statements do not run again after a successful application.

## Deletion policy

Historical records use restrictive foreign keys. Repositories and playbook
documents are archived by setting `archived_at`; they are not normally deleted.
Playbook versions and chunks are immutable after insertion.

## Ingestion

After migrations are applied:

```bash
python scripts/ingest_playbook.py playbooks/sample_playbook.md \
    --category standards
```

An unchanged checksum embedded by the same model and dimension is skipped.
Changed content or an embedding-model change creates the next immutable
`playbook_versions.version` and a new set of `playbook_chunks`.
