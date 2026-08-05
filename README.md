# Virtual Staff Engineer

Virtual Staff Engineer is a human-supervised code-governance agent that reviews
GitHub changes against versioned engineering playbooks. It is designed to find
evidence-backed rule violations, propose validated patches, pause for approval,
and create remediation pull requests safely.

## Current status

The project is currently in **Phase 1: Reliable Organizational Memory**.

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

Next:

- Run and analyze the frozen Phase 1 retrieval benchmark

## Architecture

```text
GitHub diff
    ↓
LangGraph orchestrator
    ↓
Agent → tools → evaluator
    ↓
Human approval
    ↓
GitHub pull request
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

Run tests:

```bash
python -m unittest discover -s tests -v
```

See [tests/README.md](tests/README.md) for test coverage, database isolation,
and commands for running individual test suites.

## Roadmap

1. Build and benchmark hybrid playbook retrieval.
2. Add the controlled LangGraph agent workflow.
3. Add GitHub tools, patch validation, idempotency, and approval checkpoints.
4. Build the Next.js/FastAPI product and optimize measured bottlenecks.

## Project structure

```text
src/virtual_staff_engineer/
├── database/       PostgreSQL connections, migrations, and SQL
├── ingestion/      Markdown parsing, embeddings, and versioned ingestion
├── retrieval/      Semantic, lexical, and hybrid retrieval
└── evaluation/     Retrieval datasets, metrics, and benchmarks

scripts/            Thin command-line entry points
tests/unit/         Fast tests without infrastructure
tests/integration/  PostgreSQL integration tests
docs/               Architecture and subsystem documentation
```

See [docs/architecture.md](docs/architecture.md) for module boundaries,
[docs/database.md](docs/database.md) for database migration details, and
[docs/retrieval.md](docs/retrieval.md) for retrieval behavior. The benchmark
workflow and metric definitions are in [docs/evaluation.md](docs/evaluation.md).
