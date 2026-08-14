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

The worker defaults to one analysis lease at a time. For the Phase 4 measured
concurrency experiment, configure one process with:

```bash
VSE_ANALYSIS_WORKER_CONCURRENCY=2 \
VSE_MODEL_REQUESTS_PER_MINUTE=15 \
python scripts/run_workers.py
```

This overlaps independent jobs while smoothing Gemini generation calls. It
does not increase the provider quota; the benchmark should show whether queue
wait improves while total throughput remains provider-limited.

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
| `GET /github/pull-requests` | viewer | Paginated PR lifecycle/history grouped with per-file jobs |
| `POST /webhooks/github` | GitHub HMAC | Verify and record supported PR webhook deliveries |

## GitHub webhook boundary

Set `GITHUB_WEBHOOK_SECRET` to an independent random secret and apply migration
`013_github_webhook_deliveries.sql`. GitHub calls `POST /webhooks/github` with
`X-Hub-Signature-256`, `X-GitHub-Delivery`, and `X-GitHub-Event`; API keys are
not used for this machine-to-machine endpoint.

The endpoint verifies the HMAC against the exact raw request bytes before JSON
parsing. It responds to `ping`, ignores unrelated events and unsupported PR
actions, and durably records `opened`, `reopened`, `synchronize`, and
`ready_for_review` deliveries. Repeated delivery IDs with identical immutable
metadata return `duplicate`; reuse with different metadata returns `409`.

Only repository/PR identity, installation ID, head SHA, action, delivery ID, and
a SHA-256 payload digest are stored. Raw payloads are not retained. This Phase 5
endpoint deliberately does not fetch PR files or call Gemini. A separately
leased worker consumes the durable receipt, downloads an immutable PR snapshot,
and submits idempotent per-file analysis jobs after HTTP has returned.

SSE includes only durable state, checkpoint, attempt, failure code, and time.
It never publishes prompts, hidden reasoning, or chain-of-thought.

## Timing semantics

Status derives metrics from the immutable `workflow_job_transitions` history:

- `queue_wait_ms`: submission until the first active worker stage;
- `stage_timings`: observed duration of each active stage;
- `human_wait_ms`: awaiting approval until approve/reject;
- `automated_processing_ms`: end-to-end time excluding completed human wait;
- `end_to_end_ms`: submission through terminal completion, including human wait.
- `retry_count`: number of durable `retry_scheduled` transitions.

`attempt_count` counts worker-stage claims, so it must not be interpreted as a
retry count.

These are per-job observations. Aggregate p50/p95, throughput, success, and
recovery rates will be calculated by the Phase 4 benchmark workload.

The status response also exposes analysis input/output tokens, retrieval tool
calls, and an estimated analysis cost when model prices are configured. Patch
generation token cost is not yet persisted and is therefore not included.
If either price variable is absent, estimated cost is reported as `null`, not
as a misleading zero. Explicit zero rates may be used for a free-tier run.

## GitHub dashboard

The dashboard's GitHub pull-request feed reads `GET /github/pull-requests`.
Server-side `view`, `state`, `page`, and `page_size` parameters support active,
archive, and full-history navigation without loading the entire audit trail.
Repeated webhook deliveries are grouped under one PR while their per-head file
jobs remain selectable. Selecting a job opens status, cited evidence, validated
patch, and approval. `GET /jobs/{id}` includes optional GitHub provenance and
the created remediation PR URL after idempotent mutation completes.

The feed is read-only. Refreshing it cannot fetch source again, call the model,
or mutate GitHub; it only reads durable Step 4 records.

Migration `015_github_pr_lifecycle.sql` stores immutable lifecycle events and a
current-state projection. GitHub `closed` events map to `merged` only when the
payload's `pull_request.merged` value is true; otherwise they remain `closed`.
Out-of-order events cannot replace a newer GitHub `updated_at` state.

## Reproducible live workload

With FastAPI and the workers running, execute the frozen safe workload:

```bash
python scripts/run_phase4_workload.py \
  --output evaluation_results/phase4_workload/run-001.json
```

The runner uses `VSE_VIEWER_API_KEY`, `VSE_REVIEWER_API_KEY`, and
`VSE_REPOSITORY_ROOT`. It runs clean completion, validated-patch rejection, and
stale-source blocking. It never approves a patch or calls GitHub. Use a new
`--run-id` for an independent run; repeating the same run ID intentionally
exercises API idempotency.

Each new workload result includes run-level duration and per-job retry/stage
metrics. Aggregate one or more successful runs into an offline baseline:

```bash
python scripts/summarize_phase4_baseline.py \
  evaluation_results/phase4_workload/run-004.json \
  --output-dir evaluation_results/phase4_baseline/v1
```

The report labels fewer than 20 jobs as an exploratory sample. It does not
present a three-job p95 as statistically stable evidence.

## Concurrent load and failure tests

The load runner submits clean design reviews in increasing concurrent waves.
Without `--execute`, it only prints the planned number of live jobs:

```bash
python scripts/run_phase4_load_test.py
```

Start with the low-risk waves while FastAPI and one worker process are running:

```bash
python scripts/run_phase4_load_test.py \
  --levels 1,5 \
  --run-id load-001 \
  --output-dir evaluation_results/phase4_load/load-001 \
  --execute
```

Inspect that report before expanding the identical workload:

```bash
python scripts/run_phase4_load_test.py \
  --levels 1,5,10,25 \
  --run-id load-002 \
  --output-dir evaluation_results/phase4_load/load-002 \
  --execute
```

The runner measures submission, health-probe, queue, processing, and end-to-end
latency; clean completions, unexpected outcomes, throughput, retries, and token
usage; and per-job stage timings. It stops before higher waves when the current
wave exceeds `--max-failure-rate` (default 20%). The workload never approves a
patch or invokes GitHub.

Gemini `429 RESOURCE_EXHAUSTED` responses are classified as retryable
`rate_limited` failures. Workers respect the provider retry hint as a minimum
delay, retain bounded exponential backoff and jitter, and persist the scheduled
availability time before releasing the lease.

Run controlled failure behavior without adding production fault switches:

```bash
python scripts/run_phase4_failure_tests.py
```

This deterministic suite covers bounded backoff and jitter, temporary provider
failure, invalid/stale patches, expired job leases when PostgreSQL is available,
and GitHub timeout reconciliation without contacting GitHub.
