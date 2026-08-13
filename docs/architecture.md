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
             └──────→ PostgreSQL ←──── jobs
                          ↑
             github ← remediation
                           ↑
                       evaluation

Next.js ──→ FastAPI ──→ PostgreSQL queue ──→ concurrent stage workers
   ↑                                              │
   └──────── safe SSE/status/review ──────────────┘
```

- `database` owns PostgreSQL connections, SQL migrations, and schema assets.
- `ingestion` owns Markdown parsing, embedding generation, and immutable
  playbook version creation.
- `retrieval` owns semantic, lexical, and hybrid ranking.
- `evaluation` owns datasets, quality metrics, and benchmark execution.
- `analysis` owns reasoning contracts, bounded orchestration, deterministic
  evidence validation, provider adapters, and analysis persistence.
- `jobs` owns the durable Phase 3 lifecycle, legal transitions, checkpoints,
  queue leases, workers, and failure taxonomy.
- `remediation` owns structured patch contracts, provider-backed read-only
  source snapshots, patch generation, and deterministic proposal checks.
- `github` owns reviewer authentication and retry-safe external branch, file,
  and pull-request reconciliation.
- `providers` owns process-wide controls around model-provider requests.
- `frontend` owns the human submission, inspection, and approval interface.
- `scripts` contains only command-line argument handling and calls into the
  application package.

The Phase 2 agent consumes retrieval through a tool boundary. Retrieval does
not depend on agent orchestration, and orchestration does not contain SQL.
`AnalysisService` coordinates the in-memory workflow with the repository so
the reasoning and persistence layers remain independently testable.

The Phase 3 job is deliberately separate from `analysis_runs` and
`remediation_actions`: those tables describe domain outcomes, while the job
describes how work is scheduled, leased, retried, resumed, and completed.

## Why a modular monolith

The current bottleneck is analysis correctness, not independent service
scaling. A modular monolith provides clear ownership and test boundaries
without adding network calls, deployment units, or distributed failure modes.
The Phase 4 level-10 load run kept FastAPI health p95 below 4 ms while the
Gemini free-tier request quota limited total capacity. Services such as a Go
gateway, Redis queue, or independently deployed workers would not address that
measured constraint and should be introduced only when a future benchmark
demonstrates the need.
