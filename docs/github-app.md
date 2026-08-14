# GitHub App integration

## Step 1: secure webhook boundary

The local API exposes `POST /webhooks/github`. This endpoint authenticates
GitHub with the `X-Hub-Signature-256` HMAC of the exact raw body; it is not
protected by the dashboard API keys.

Current behavior:

```text
request body
→ 2 MB size limit
→ required delivery/event headers
→ SHA-256 HMAC verification
→ JSON object validation
→ event/action filtering
→ minimal delivery metadata persisted once
→ 202 response
```

Supported PR actions are `opened`, `reopened`, `synchronize`, and
`ready_for_review`. GitHub `ping` receives `pong`. Other events and actions are
acknowledged as `ignored` so GitHub does not repeatedly redeliver work the
application does not consume.

Apply the database migration:

```bash
python scripts/migrate.py
```

Generate a secret locally and place it only in `.env`:

```ini
GITHUB_WEBHOOK_SECRET=your-independent-random-secret
```

Restart FastAPI after changing the environment. The secret is loaded when the
application is created. The raw webhook payload is never stored; the database
retains only the minimal PR identity and its SHA-256 payload digest for audit
and deduplication.

This step does not yet require a GitHub App or public tunnel. Unit tests use
signed fixture payloads. Creating and installing the real GitHub App is Step 2.

## Step 2: local GitHub App installation

Create the App in GitHub, subscribe only to pull-request events, and install it
only on a disposable repository. Set the webhook URL to the temporary tunnel's
`/webhooks/github` endpoint and use the same `GITHUB_WEBHOOK_SECRET` as the
local API. Store the downloaded private key outside this repository.

## Step 3: read-only PR snapshots

Configure:

```ini
GITHUB_APP_ID=your_numeric_app_id
GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/outside/repository/app-key.pem
```

The adapter signs a short-lived RS256 App JWT and exchanges it for an
installation token scoped down to read-only `contents` and `pull_requests`
permissions. Tokens are cached until one minute before expiry. The adapter then:

```text
read PR metadata and expected head SHA
→ retrieve changed files in 100-file pages
→ classify deleted, binary/unavailable, and oversized patches
→ normalize analyzable patches as unified diffs
→ read PR metadata again
→ reject the snapshot if the head SHA moved
```

The snapshot is bounded to 3,000 files and 200,000 patch characters per file.
Reaching the file boundary fails rather than silently analyzing incomplete
data. Missing patches (including binary or API-truncated cases), deleted files,
and oversized patches remain visible with a skip reason but are not sent to the
agent.

Test a real PR without creating branches, commits, jobs, or model calls:

```bash
python scripts/fetch_github_pr.py \
  --owner YOUR_OWNER \
  --repository YOUR_REPOSITORY \
  --pull-request 1 \
  --installation-id YOUR_INSTALLATION_ID \
  --head-sha THE_CURRENT_PR_HEAD_SHA
```

The command prints only snapshot metadata, analyzable paths, and skipped-file
reasons. It does not print source patches. GitHub documents the App JWT and
installation-token flow in its
[authentication guide](https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app)
and the PR/file endpoints in its
[pull-request REST reference](https://docs.github.com/en/rest/pulls/pulls?apiVersion=2022-11-28).

## Step 4: asynchronous job submission

Migration `014_github_webhook_ingestion.sql` turns accepted deliveries into a
small durable queue. The webhook request still performs no GitHub or model API
calls. `scripts/run_workers.py` adds a GitHub ingestion stage whenever both
`GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY_PATH` are configured:

```text
signed webhook
→ delivery persisted as received
→ HTTP 202 returned

leased ingestion worker
→ scoped installation token
→ stable PR metadata, file pages, and exact Git blobs
→ repository and commit identity persisted
→ immutable source snapshots persisted
→ one workflow job per analyzable file
→ delivery marked completed
```

The per-file job identity contains repository, PR number, head SHA, and a hash
of the source path. Repeated GitHub deliveries for the same PR head therefore
reuse existing jobs, while a new head commit creates new jobs. A link table
records which delivery produced or reused each workflow job.

GitHub ingestion uses a five-minute lease. Expired work becomes retryable and
can be reclaimed after a worker crash. Network failures, server failures, and
rate limits are retried with bounded exponential backoff; stale heads,
unsupported responses, and oversized PRs stop permanently. A later
`synchronize` event for a new head SHA remains independently processable.

For analyzable files, the exact UTF-8 Git blob at the PR head is stored with its
hash and normalized diff. Patch generation and validation load this immutable
snapshot instead of assuming the file exists under `VSE_REPOSITORY_ROOT`.

Apply the new migration and restart the workers:

```bash
python scripts/migrate.py
python scripts/run_workers.py
```

Opening or updating a PR should now produce a `github_ingestion` worker event
followed by ordinary `analysis-*` events.

## Step 5: GitHub review dashboard

Enter a viewer or reviewer API key in the dashboard and select **Refresh** in
the GitHub pull-request section. The feed groups webhook deliveries by source
PR and lists every per-file analysis job created by Step 4. Selecting a file
loads its status, evidence, validation checks, and approval controls. Source PR
links and, after approved mutation, the created remediation PR link are shown
directly in the workflow view.

No new migration or GitHub permission is required for Step 5. The new API is a
read-only projection over existing webhook, job, snapshot, and PR-operation
tables.
