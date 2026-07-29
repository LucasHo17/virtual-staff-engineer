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

Next:

- Semantic vector retrieval
- Lexical/full-text retrieval
- Hybrid ranking
- Retrieval evaluation and benchmarks

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

Install the current dependencies:

```bash
pip install "psycopg[binary]" google-genai python-dotenv
```

Create `.env`:

```dotenv
GEMINI_API_KEY=your_api_key
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/staff_engineer_db
```

Start PostgreSQL with `pgvector`, then apply all pending migrations:

```bash
python db_init/init_db.py
```

Ingest the sample engineering playbook:

```bash
python ingest.py
```

Run tests:

```bash
python -m unittest discover -s tests -v
```

## Roadmap

1. Build and benchmark hybrid playbook retrieval.
2. Add the controlled LangGraph agent workflow.
3. Add GitHub tools, patch validation, idempotency, and approval checkpoints.
4. Build the Next.js/FastAPI product and optimize measured bottlenecks.

See [db_init/README.md](db_init/README.md) for database migration details.
