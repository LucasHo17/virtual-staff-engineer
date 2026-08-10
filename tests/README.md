# Tests

The test suite contains fast unit tests and PostgreSQL integration tests for
Phase 1 retrieval, Phase 2 analysis, and the Phase 3 durable job lifecycle.

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

Phase 3 unit coverage includes lifecycle validation, exponential retry timing,
failure classification, and analysis-worker polling behavior. The job
repository integration suite additionally verifies transactional completion
and retry/permanent failure persistence against PostgreSQL.

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

The analysis unit tests verify contracts, bounded iterations and tool calls,
structured Gemini responses, deterministic citation validation, duplicate
suppression, evaluator decisions, and successful/failed persistence lifecycle
handling. They use fake reasoners and clients and make no model API calls.

`unit/test_job_lifecycle.py` verifies legal and illegal job transitions, fixed
failure classification, retry requirements, terminal behavior, and monotonic
idempotent checkpoints without PostgreSQL.

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

`integration/test_analysis_repository.py` verifies that one transaction stores
the raw input checksum, executed query, retrieval provenance, supported and
unsupported reviews, deterministic rejection, playbook version, and only the
supported violation.

`integration/test_analysis_workflow_acceptance.py` runs the bounded planner,
retrieval, analyst, validation, and evaluator flow across 20 labeled workflow
scenarios. It uses scripted components rather than PostgreSQL or Gemini, so it
tests cross-module behavior without claiming model quality.

`integration/test_workflow_jobs.py` verifies the database rejects illegal state
skips, checkpoint regression, active work without a lease, and unclassified
retries. It also verifies a retry/requeue cycle and the automatically ordered
transition audit history.

`integration/test_job_repository.py` verifies transactional idempotent
submission, conflicting key rejection, priority ordering, concurrent
`SKIP LOCKED` claims, lease-token heartbeat ownership, same-stage recovery, and
attempt exhaustion. Its concurrency tests use independent PostgreSQL
connections and never call external model APIs.

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
