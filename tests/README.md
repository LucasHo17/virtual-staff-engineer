# Tests

The test suite contains fast unit tests and PostgreSQL integration tests for
the Phase 1 playbook ingestion pipeline.

## Run all tests

From the project root:

```bash
python -m unittest discover -s tests -v
```

## Unit tests

`unit/test_ingestion.py` tests behavior that does not require PostgreSQL:

- Empty Markdown preambles are ignored
- Explicit rule identifiers are extracted from headings
- Fallback rule identifiers are generated
- Embedding metadata and dimensions are preserved

Run only the unit tests:

```bash
python -m unittest tests.unit.test_ingestion -v
```

## PostgreSQL integration tests

`integration/test_ingestion.py` verifies:

- First ingestion creates a document, version, and chunks
- Identical content is skipped without embedding it again
- Changed content creates the next immutable version
- Changing the embedding model creates the next version
- Re-ingestion restores an archived document
- Failed database writes roll back completely
- Concurrent ingestion creates only one version

The integration tests use `TEST_DATABASE_URL` when configured and otherwise
fall back to `DATABASE_URL`. The target database must have the project
migrations applied.

Each test creates a uniquely named playbook and deletes only its own chunks,
versions, and document after completion. No external embedding API calls are
made; deterministic fake embeddings are used.

Run only the integration tests:

```bash
python -m unittest tests.integration.test_ingestion -v
```

To target a dedicated test database:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/staff_engineer_test \
python -m unittest tests.integration.test_ingestion -v
```

If the database is unavailable or its schema has not been initialized, the
integration suite is skipped with an explanatory message.
