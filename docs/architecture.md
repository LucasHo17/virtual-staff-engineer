# Project architecture

Virtual Staff Engineer is currently a modular Python application. The modules
have explicit responsibilities but deploy together while the project is still
establishing real performance and scaling requirements.

## Module boundaries

```text
playbook Markdown
      ↓
ingestion ─────→ PostgreSQL + pgvector
                       ↑
query ─────────→ retrieval
                       ↓
                  evaluation
```

- `database` owns PostgreSQL connections, SQL migrations, and schema assets.
- `ingestion` owns Markdown parsing, embedding generation, and immutable
  playbook version creation.
- `retrieval` will own semantic, lexical, and hybrid ranking.
- `evaluation` will own datasets, quality metrics, and benchmark execution.
- `scripts` contains only command-line argument handling and calls into the
  application package.

The Phase 2 agent will consume retrieval through a tool boundary. Retrieval
must not depend on agent orchestration.

## Why a modular monolith

The current bottleneck is retrieval correctness, not independent service
scaling. A modular monolith provides clear ownership and test boundaries
without adding network calls, deployment units, or distributed failure modes.
Services such as Go gateways, Redis queues, or separate workers should be
introduced only when measurements demonstrate the need.
