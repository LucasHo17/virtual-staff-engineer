# Tests

The test suite contains fast unit tests and PostgreSQL integration tests for
Phase 1 ingestion and retrieval.

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
python -m unittest discover -s tests/unit -v
```

`unit/test_semantic_retrieval.py` verifies query validation, embedding
generation, vector validation, supported dimensions, and `top_k` boundaries.

`unit/test_lexical_retrieval.py` verifies query, category, `top_k`, and fuzzy
threshold validation without accessing PostgreSQL.

`unit/test_hybrid_retrieval.py` verifies RRF overlap promotion, one-sided
candidate provenance, weights, candidate-pool validation, and fusion parameter
validation.

The evaluation unit tests verify frozen-dataset validation, case selection,
rule-level metrics, negative-query scoring, latency aggregation, one embedding
request per benchmark case, compact result serialization, and report overwrite
protection. They also verify offline threshold replay, guarded lexical fusion,
semantic-threshold validation, and preflight checks before paid API work.

## PostgreSQL integration tests

`integration/test_ingestion.py` verifies:

- First ingestion creates a document, version, and chunks
- Identical content is skipped without embedding it again
- Changed content creates the next immutable version
- Changing the embedding model creates the next version
- Re-ingestion restores an archived document
- Failed database writes roll back completely
- Concurrent ingestion creates only one version

`integration/test_semantic_retrieval.py` verifies:

- Cosine similarity ordering
- Structured citation metadata
- `top_k` and category filtering
- Archived-document exclusion
- Latest-version selection
- No fallback to stale versions from another embedding model

`integration/test_lexical_retrieval.py` verifies:

- Exact rule-key boosting
- PostgreSQL full-text ranking
- Trigram typo recovery
- Structured citation metadata
- Active/latest/category filtering

`integration/test_hybrid_retrieval.py` verifies the complete semantic and
lexical retrieval flow and confirms that a chunk found by both methods is
promoted above a semantic-only candidate.

The integration tests use `TEST_DATABASE_URL` when configured and otherwise
fall back to `DATABASE_URL`. The target database must have the project
migrations applied.

Each test creates a uniquely named playbook and deletes only its own chunks,
versions, and document after completion. No external embedding API calls are
made; deterministic fake embeddings are used.

Run only the integration tests:

```bash
python -m unittest discover -s tests/integration -v
```

To target a dedicated test database:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/staff_engineer_test \
python -m unittest discover -s tests/integration -v
```

If the database is unavailable or its schema has not been initialized, the
integration suite is skipped with an explanatory message.
