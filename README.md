# Virtual Staff Engineer

Virtual Staff Engineer is a human-supervised AI code-governance system. It
reviews GitHub pull requests against versioned engineering playbooks, cites the
rules behind each finding, validates proposed fixes, and creates remediation
pull requests only after authorized human approval.

Unlike a standalone RAG demo, the project includes the surrounding production
workflow: signed webhooks, durable asynchronous jobs, evaluation datasets,
deterministic safety checks, failure recovery, idempotent GitHub mutations, and
an approval dashboard.

## Why it exists

Engineering standards are often documented but enforced through slow and
inconsistent manual review. Sending an entire playbook to a model is expensive,
while allowing generated code to mutate a repository without verification is
unsafe.

Virtual Staff Engineer addresses both problems:

1. retrieve only the rules relevant to a change;
2. require the agent to ground findings in exact evidence;
3. validate proposed patches deterministically;
4. pause before external mutation; and
5. reconcile GitHub state so retries do not create duplicate actions.

## System architecture

```mermaid
flowchart TD
    GH["GitHub pull request"] --> WH["Signed GitHub App webhook"]
    WH --> API["FastAPI service<br/>HMAC verification and deduplication"]
    API --> Q["PostgreSQL durable job queue<br/>leases, checkpoints, retries"]

    Q --> ORCH["Python orchestrator"]
    ORCH --> RET["Hybrid retrieval tool<br/>semantic + lexical ranking"]
    RET <--> DB["PostgreSQL + pgvector<br/>versioned playbooks and audit state"]
    RET --> AGENT["Gemini reasoning agent"]
    AGENT --> EVAL["Evidence evaluator"]
    EVAL --> PATCH["Patch generator and deterministic validator"]
    PATCH --> Q

    Q --> UI["Next.js review dashboard<br/>safe status and cited evidence"]
    UI --> APPROVAL["Authenticated approve or reject decision"]
    APPROVAL --> MUTATE["Idempotent GitHub mutation tool"]
    MUTATE --> PR["Branch, commit, and remediation PR"]
    PR --> GH
```

The project remains a **modular monolith**. Measurement showed that the Gemini
free-tier request quota—not FastAPI or PostgreSQL—was the current bottleneck, so
Redis, Kafka, Kubernetes, and a Go gateway would add complexity without solving
the measured constraint.

## End-to-end workflow

```text
PR opened or updated
→ webhook authenticated and persisted
→ exact PR snapshot downloaded
→ one durable job created per analyzable file
→ relevant playbook rules retrieved
→ agent finding checked against cited evidence
→ patch generated and validated
→ authorized reviewer approves or rejects
→ existing GitHub state reconciled
→ remediation PR created safely
```

The dashboard also retains a collapsed manual diff/design-document form for
development and debugging. GitHub webhook ingestion is the primary workflow.

## Engineering results

### Agent quality

A frozen, independently reviewed 20-case holdout covered violating, clean,
ambiguous, and irrelevant inputs against a 31-rule playbook:

| Precision | Recall | F1 | Exact-rule accuracy | Status accuracy |
|---:|---:|---:|---:|---:|
| 0.833 | 1.000 | 0.909 | 0.950 | 0.950 |

See the [Phase 2 holdout report](evaluation_results/phase2_holdout_v1/report.md)
and [analysis methodology](docs/analysis.md).

### Measured backend optimization

In a controlled ten-job load benchmark, provider-aware worker scheduling:

- completed 10/10 jobs with no unexpected failures;
- eliminated observed provider retries (`2 → 0`);
- improved throughput from `7.363 → 7.724 jobs/min` (`+4.9%`); and
- kept FastAPI health-check p95 below `4 ms`.

The trade-off was higher queue latency because unpredictable quota retries
became intentional rate-limit waiting. The complete before/after evidence is in
[Phase 4 optimization](docs/phase4-optimization.md).

These are controlled evaluation results, not production-user claims.

## Reliability and safety boundaries

- PostgreSQL queue claims use leases, heartbeats, retry scheduling, and
  monotonic checkpoints.
- Transient failures use bounded exponential backoff with jitter; permanent
  failures stop safely and preserve their state.
- Findings must cite retrieved playbook evidence and the submitted input.
- Patch validation checks source hashes, unified-diff applicability, change
  budget, and syntax before approval becomes available.
- Reviewer identity comes from API credentials rather than request JSON.
- Rejection causes no GitHub mutation.
- GitHub branch and PR creation reconcile existing external state after
  uncertain responses instead of blindly repeating writes.
- Pull-request lifecycle events remain available in the audit archive after a
  source PR is merged or closed.

## Technology decisions

| Technology | Reason it exists |
|---|---|
| PostgreSQL + pgvector | Keeps relational workflow state, audit history, lexical search, and vector retrieval in one durable system. |
| Hybrid retrieval | Combines semantic recall with exact rule identifiers and engineering terminology. |
| FastAPI + workers | Returns HTTP requests quickly while model calls run asynchronously. |
| Gemini | Performs probabilistic planning, analysis, and patch generation behind deterministic contracts. |
| Next.js | Provides evidence inspection and the human approval boundary. |
| GitHub App + REST API | Authenticates webhooks, reads exact PR snapshots, and integrates remediation with the real developer workflow. |

## Quick start

Prerequisites: Docker, Python 3.11+, Node.js 20+, npm, and a Gemini API key.

```bash
git clone https://github.com/LucasHo17/virtual-staff-engineer.git
cd virtual-staff-engineer

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .

cp .env.example .env
docker compose up -d postgres
python scripts/migrate.py
python scripts/ingest_playbook.py playbooks/evaluation_playbook.md \
  --category evaluation

cp frontend/.env.example frontend/.env.local
cd frontend
npm ci
cd ..
```

Set at least these values in `.env` before starting the application:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
GEMINI_REASONING_MODEL=your_supported_gemini_model
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/staff_engineer_db
VSE_VIEWER_API_KEY=replace_with_a_random_viewer_secret
VSE_REVIEWER_API_KEY=replace_with_a_different_reviewer_secret
VSE_REPOSITORY_ROOT=/absolute/path/to/repository/being_reviewed
VSE_PLAYBOOK_CATEGORY=evaluation
```

Run the three application processes in separate terminals:

```bash
# Terminal 1: API
source .venv/bin/activate
uvicorn virtual_staff_engineer.api.app:app --reload

# Terminal 2: asynchronous workers
source .venv/bin/activate
python scripts/run_workers.py

# Terminal 3: dashboard
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000), enter the viewer or
reviewer key configured in `.env`, and submit a manual test or inspect incoming
GitHub activity.

The complete clean-machine instructions—including environment variables,
smoke tests, GitHub App permissions, webhook tunneling, and troubleshooting—are
in [docs/setup.md](docs/setup.md).

## Verification

Run the local unit suite and frontend checks:

```bash
python -m unittest discover -s tests/unit -v
cd frontend
npm run lint
npm run build
```

Database integration tests and evaluation runners are documented in
[tests/README.md](tests/README.md) and [docs/evaluation.md](docs/evaluation.md).
The committed reports under `evaluation_results/` make the reported metrics
auditable without rerunning paid model calls.

## Project structure

```text
src/virtual_staff_engineer/
├── analysis/       Agent contracts, orchestration, and evidence validation
├── api/            FastAPI submission, status, SSE, review, and webhooks
├── database/       PostgreSQL connections and ordered SQL migrations
├── evaluation/     Frozen datasets, metrics, and benchmark execution
├── github/         GitHub App reads and idempotent REST mutations
├── ingestion/      Markdown parsing, embeddings, and playbook versions
├── jobs/           Durable lifecycle, leases, checkpoints, and workers
├── providers/      Shared model-provider request controls
├── remediation/    Patch generation, source snapshots, and validation
└── retrieval/      Semantic, lexical, and hybrid ranking

frontend/           Next.js review and approval dashboard
playbooks/          Sample and evaluation engineering playbooks
scripts/            Thin CLI entry points
tests/              Unit, integration, and deterministic workflow tests
docs/               Architecture, setup, subsystem, and benchmark decisions
```

## Documentation

- [Local and GitHub setup](docs/setup.md)
- [Architecture and module boundaries](docs/architecture.md)
- [GitHub App integration](docs/github-app.md)
- [Database schema and migrations](docs/database.md)
- [Durable job lifecycle](docs/jobs.md)
- [Retrieval design](docs/retrieval.md)
- [Agent evaluation](docs/analysis.md)
- [Patch validation and approval](docs/remediation.md)
- [Phase 4 closeout](docs/phase4-closeout.md)

## Current boundary

The repository contains a complete local portfolio MVP and has been exercised
against a real disposable GitHub repository. It is not presented as a deployed
multi-tenant production service. Production identity, secret management,
managed infrastructure, and real-user impact remain future work.
