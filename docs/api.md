# Phase 4 API MVP

The FastAPI boundary submits work asynchronously. HTTP requests never execute
Gemini analysis directly; they create a durable PostgreSQL job for the existing
workers.

## Authentication

The MVP uses server-configured API keys:

- `VSE_VIEWER_API_KEY`: submit and inspect jobs;
- `VSE_REVIEWER_API_KEY`: all viewer capabilities plus approve/reject;
- `VSE_VIEWER_IDENTITY` and `VSE_REVIEWER_IDENTITY`: stable audit subjects.

Clients send the credential in `X-API-Key`. The reviewer identity is derived
from server configuration and cannot be supplied in decision JSON. API keys are
an MVP boundary; production deployment should replace them with an identity
provider and explicit role/team policy.

## Run

```bash
uvicorn virtual_staff_engineer.api.app:app --reload
```

Submit a pasted code diff:

```bash
curl -X POST http://127.0.0.1:8000/analysis-runs \
  -H "X-API-Key: $VSE_VIEWER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "input_type": "code_diff",
    "content": "+ logger.info(request.token)",
    "source_path": "app.py",
    "idempotency_key": "demo:app.py:change-1"
  }'
```

The response is `202 Accepted` with a `workflow_job_id`. The API has not run
the analysis yet; a worker must claim the queued job.

Run the asynchronous workers in another terminal:

```bash
python scripts/run_workers.py
```

`VSE_REPOSITORY_ROOT` identifies the local repository whose full source files
may be read for patch generation. A pasted diff can be analyzed without it, but
a supported finding cannot become a valid patch unless its `source_path`
resolves inside that configured root.

Run the dashboard in a third terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:3000`. API keys are held only in page memory; the MVP
does not persist them in browser storage.

## Endpoints

| Endpoint | Role | Purpose |
|---|---|---|
| `GET /health` | public | Process health |
| `POST /analysis-runs` | viewer | Submit code diff or design document |
| `GET /jobs/{id}` | viewer | Status, failures, and timing metrics |
| `GET /jobs/{id}/events` | viewer | Safe SSE workflow transitions |
| `GET /jobs/{id}/review` | viewer | Exact validated patch review package |
| `POST /jobs/{id}/decision` | reviewer | Authenticated approve/reject |

SSE includes only durable state, checkpoint, attempt, failure code, and time.
It never publishes prompts, hidden reasoning, or chain-of-thought.

## Timing semantics

Status derives metrics from the immutable `workflow_job_transitions` history:

- `queue_wait_ms`: submission until the first active worker stage;
- `stage_timings`: observed duration of each active stage;
- `human_wait_ms`: awaiting approval until approve/reject;
- `automated_processing_ms`: end-to-end time excluding completed human wait;
- `end_to_end_ms`: submission through terminal completion, including human wait.

These are per-job observations. Aggregate p50/p95, throughput, success, and
recovery rates will be calculated by the Phase 4 benchmark workload.

The status response also exposes analysis input/output tokens, retrieval tool
calls, and an estimated analysis cost when model prices are configured. Patch
generation token cost is not yet persisted and is therefore not included.
