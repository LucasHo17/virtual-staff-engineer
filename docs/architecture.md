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
input ──→ analysis ──→ retrieval
             │             ↓
             └──────→ PostgreSQL
                           ↑
                       evaluation
```

- `database` owns PostgreSQL connections, SQL migrations, and schema assets.
- `ingestion` owns Markdown parsing, embedding generation, and immutable
  playbook version creation.
- `retrieval` owns semantic, lexical, and hybrid ranking.
- `evaluation` owns datasets, quality metrics, and benchmark execution.
- `analysis` owns reasoning contracts, bounded orchestration, deterministic
  evidence validation, provider adapters, and analysis persistence.
- `scripts` contains only command-line argument handling and calls into the
  application package.

The Phase 2 agent consumes retrieval through a tool boundary. Retrieval does
not depend on agent orchestration, and orchestration does not contain SQL.
`AnalysisService` coordinates the in-memory workflow with the repository so
the reasoning and persistence layers remain independently testable.

## Why a modular monolith

The current bottleneck is analysis correctness, not independent service
scaling. A modular monolith provides clear ownership and test boundaries
without adding network calls, deployment units, or distributed failure modes.
Services such as Go gateways, Redis queues, or separate workers should be
introduced only when measurements demonstrate the need.
