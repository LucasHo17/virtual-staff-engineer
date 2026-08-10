# Virtual Staff Engineer

Virtual Staff Engineer is a human-supervised code-governance agent that reviews
GitHub changes against versioned engineering playbooks. It is designed to find
evidence-backed rule violations, propose validated patches, pause for approval,
and create remediation pull requests safely.

## Current status

The project is currently in **Phase 3: Reliability and Safe Execution**.

Implemented:

- PostgreSQL with `pgvector`
- Migration-tracked database schema
- Versioned Markdown playbook ingestion
- Gemini embeddings
- HNSW vector index
- PostgreSQL full-text and trigram indexes
- Checksum-based duplicate detection
- Semantic cosine retrieval with citable results
- Lexical full-text and trigram retrieval
- Hybrid retrieval using Reciprocal Rank Fusion
- Frozen labeled retrieval dataset and reproducible benchmark runner
- Offline threshold/fusion replay without additional embedding calls
- Confidence-gated lexical evidence for safer hybrid ranking
- Structured code-diff and design-document analysis contracts
- Bounded planner → retrieval → analyst → evaluator workflow
- Deterministic rule and input citation validation
- Transactional analysis audit trail in PostgreSQL
- Balanced 20-case deterministic workflow acceptance suite
- Frozen 20-case live-agent benchmark with quality, safety, latency, usage, and
  estimated-cost reporting
- Durable PostgreSQL workflow job state machine with idempotency identity,
  attempts, leases, retry scheduling, monotonic checkpoints, and transition
  audit history

The first measured Phase 2 baseline (`gemini-3.5-flash-lite`) had precision
`1.00`, recall `0.60`, and F1 `0.75`. After deterministic excerpt construction
and a narrower missing-context policy, the same frozen development set measured
precision `0.833`, recall `1.00`, F1 `0.909`, and status accuracy `1.00` while
preserving zero clean/irrelevant false positives and perfect ambiguous-input
abstention. The remaining extra `REL-01` result on an `API-02` case requires
label adjudication before a new dataset version. A separately reviewed frozen
holdout was then run once with no tuning: precision `0.833`, recall `1.00`, F1
`0.909`, exact-rule accuracy `0.95`, and terminal-status accuracy `0.95`. It
found every violation and handled every ambiguous and irrelevant case correctly,
with one false positive on ownership-scoped authorization code.

Phase 3A is complete: the job lifecycle, failure taxonomy, database invariants,
and acceptance tests are implemented. Phase 3B will add atomic job submission,
worker claiming, heartbeats, and expired-lease recovery.

## Architecture

```text
Code diff / design document
           ↓
Bounded Python orchestrator
           ↓
Planner → hybrid retrieval → analyst
           ↓
Deterministic evidence gate → evaluator
           ↓
PostgreSQL audit trail
```

PostgreSQL is the durable source of truth for versioned playbooks, analysis
runs, evidence, approvals, and remediation history.

## Local setup

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install the project and its dependencies in editable mode:

```bash
python -m pip install --upgrade pip setuptools
pip install -e .
```

Copy `.env.example` to `.env`, then provide local credentials:

```dotenv
GEMINI_API_KEY=your_api_key
GEMINI_REASONING_MODEL=your_reasoning_model
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/staff_engineer_db
```

Start PostgreSQL with `pgvector`, then apply all pending migrations:

```bash
python scripts/migrate.py
```

Ingest the sample engineering playbook:

```bash
python scripts/ingest_playbook.py playbooks/sample_playbook.md \
    --category standards
```

Search active playbooks semantically:

```bash
python scripts/search_semantic.py \
    "Can an application write authentication tokens to logs?" \
    --top-k 5 \
    --category standards
```

Search by exact terms, rule identifiers, or fuzzy text:

```bash
python scripts/search_lexical.py "SEC-01" \
    --top-k 5 \
    --category standards
```

Search using semantic and lexical rank fusion:

```bash
python scripts/search_hybrid.py \
    "Can an application write authentication tokens to logs?" \
    --top-k 5 \
    --candidate-k 20 \
    --category standards
```

Validate the frozen evaluation dataset against PostgreSQL without making any
embedding API calls:

```bash
python scripts/evaluate_retrieval.py --dry-run
```

Run a five-case smoke benchmark before the complete 65-case evaluation:

```bash
python scripts/evaluate_retrieval.py \
    --limit 5 \
    --output-dir evaluation_results/smoke
```

Analyze a completed benchmark offline:

```bash
python scripts/analyze_retrieval_results.py
```

Validate the frozen Phase 2 dataset and database corpus without model calls:

```bash
python scripts/evaluate_analysis.py \
    --model gemini-3.5-flash-lite \
    --dry-run
```

Run the live 20-case agent benchmark. `--case-delay-seconds` is an explicit
quota-control setting and is recorded in the report:

```bash
python scripts/evaluate_analysis.py \
    --model gemini-3.5-flash-lite \
    --case-delay-seconds 15 \
    --output-dir evaluation_results/phase2_v1
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

See [tests/README.md](tests/README.md) for test coverage, database isolation,
and commands for running individual test suites.

## Roadmap

1. Build and benchmark hybrid playbook retrieval.
2. Build and evaluate the controlled agent workflow.
3. Add GitHub tools, patch validation, idempotency, and approval checkpoints.
4. Build the Next.js/FastAPI product and optimize measured bottlenecks.

## Project structure

```text
src/virtual_staff_engineer/
├── database/       PostgreSQL connections, migrations, and SQL
├── ingestion/      Markdown parsing, embeddings, and versioned ingestion
├── retrieval/      Semantic, lexical, and hybrid retrieval
├── evaluation/     Retrieval datasets, metrics, and benchmarks
├── analysis/       Agent contracts, orchestration, validation, and persistence
└── jobs/           Durable lifecycle, checkpoints, and failure taxonomy

scripts/            Thin command-line entry points
tests/unit/         Fast tests without infrastructure
tests/integration/  PostgreSQL integration tests
docs/               Architecture and subsystem documentation
```

See [docs/architecture.md](docs/architecture.md) for module boundaries,
[docs/database.md](docs/database.md) for database migration details, and
[docs/retrieval.md](docs/retrieval.md) for retrieval behavior. The benchmark
workflow and metric definitions are in [docs/evaluation.md](docs/evaluation.md).
The Phase 2 workflow and safety boundaries are in
[docs/analysis.md](docs/analysis.md). The Phase 3 job lifecycle and reliability
decisions are in [docs/jobs.md](docs/jobs.md).
