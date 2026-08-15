# Reproducible local setup

This guide takes a new contributor from a clean clone to the working local
dashboard. The manual workflow requires only PostgreSQL and Gemini. The GitHub
workflow additionally requires a GitHub App, a webhook tunnel, and write
credentials for a disposable repository.

## 1. Prerequisites

- Git
- Docker with Docker Compose
- Python 3.11 or newer
- Node.js 20 or newer and npm
- a Gemini API key

The package currently declares Python 3.9 compatibility, but Python 3.11+ is
recommended because Python 3.9 is end-of-life and older macOS Python builds may
link against an unsupported LibreSSL version.

Check the local tools:

```bash
git --version
docker compose version
python3.11 --version
node --version
npm --version
```

## 2. Clone and install the Python project

```bash
git clone https://github.com/LucasHo17/virtual-staff-engineer.git
cd virtual-staff-engineer

python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

The editable install makes `virtual_staff_engineer` importable while preserving
the source tree for development.

## 3. Configure local environment variables

```bash
cp .env.example .env
```

Configure the manual local workflow first:

```dotenv
GEMINI_API_KEY=your_gemini_api_key
GEMINI_REASONING_MODEL=your_supported_gemini_model
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/staff_engineer_db

VSE_VIEWER_API_KEY=replace_with_a_random_viewer_secret
VSE_REVIEWER_API_KEY=replace_with_a_different_reviewer_secret
VSE_VIEWER_IDENTITY=local-viewer
VSE_REVIEWER_IDENTITY=local-reviewer
VSE_CORS_ORIGINS=http://localhost:3000
VSE_REPOSITORY_ROOT=/absolute/path/to/repository/being_reviewed
VSE_PLAYBOOK_CATEGORY=evaluation
```

Generate independent local API keys if needed:

```bash
openssl rand -hex 32
openssl rand -hex 32
```

Do not commit `.env`, GitHub private keys, or access tokens. The repository's
`.gitignore` excludes them.

Environment assignments must not contain spaces around `=`. For example:

```dotenv
GEMINI_REASONING_MODEL=gemini-model-name
```

## 4. Start PostgreSQL and apply migrations

The Compose service uses PostgreSQL 16 with `pgvector` already installed:

```bash
docker compose up -d postgres
docker compose ps
```

Wait until the service reports `healthy`, then apply every ordered migration:

```bash
source .venv/bin/activate
python scripts/migrate.py
```

The migration runner records completed files, so rerunning it is safe. It also
creates the `vector`, `pg_trgm`, and `uuid-ossp` extensions used by retrieval and
the relational schema.

To stop PostgreSQL without deleting its data:

```bash
docker compose stop postgres
```

`docker compose down -v` deletes the named database volume and should only be
used when a complete local reset is intentional.

## 5. Ingest the evaluation playbook

```bash
source .venv/bin/activate
python scripts/ingest_playbook.py playbooks/evaluation_playbook.md \
  --category evaluation
```

Expected final output:

```text
Ingested evaluation_playbook.md version 1 with 31 chunks.
```

Rerunning unchanged content is handled through checksum-based version identity
instead of silently creating a duplicate version.

## 6. Install the dashboard

```bash
cp frontend/.env.example frontend/.env.local
cd frontend
npm ci
cd ..
```

The default frontend configuration points to `http://localhost:8000`:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 7. Run the application

Keep PostgreSQL running and start these processes in separate terminals from
the repository root.

Terminal 1 — FastAPI:

```bash
source .venv/bin/activate
uvicorn virtual_staff_engineer.api.app:app --reload
```

Terminal 2 — asynchronous workflow workers:

```bash
source .venv/bin/activate
python scripts/run_workers.py
```

Terminal 3 — Next.js dashboard:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`. Use the viewer key for read-only inspection or the
reviewer key when testing approval and rejection.

## 8. Verify the manual workflow

Check the API without authentication:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

The repository includes a deterministic fixture at
`tests/fixtures/demo-repository/app.py`. For a safe local demonstration, set:

```dotenv
VSE_REPOSITORY_ROOT=/absolute/path/to/virtual-staff-engineer/tests/fixtures/demo-repository
```

Restart the workers after changing `.env`. In the dashboard's optional manual
analysis tool, use:

- input type: `Code diff`
- source path: `app.py`
- change:

```diff
--- a/app.py
+++ b/app.py
@@ -2,4 +2,5 @@
 
 logger = logging.getLogger(__name__)
 
 def process_request(request):
+    logger.info(request.token)
```

The expected path is:

```text
submitted
→ analysis running
→ SEC-01 finding with cited evidence
→ patch generated and validated
→ awaiting approval
```

Rejecting the proposal records an audit decision and performs no GitHub
mutation.

## 9. Enable the real GitHub workflow

Use a disposable repository for the portfolio demonstration.

### GitHub App reads and webhooks

Create a GitHub App and configure:

- repository permission `Contents`: read-only;
- repository permission `Pull requests`: read-only;
- event subscription: `Pull request`;
- installation scope: only the disposable repository; and
- webhook URL: `<public-tunnel-url>/webhooks/github`.

Generate a webhook secret and store the same value in GitHub and `.env`:

```bash
openssl rand -hex 32
```

Download the App private key to a location outside the repository, then add:

```dotenv
GITHUB_WEBHOOK_SECRET=your_independent_webhook_secret
GITHUB_APP_ID=your_numeric_app_id
GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/outside/repository/app-key.pem
```

Restart FastAPI and the workers after changing these values. The webhook secret
is loaded when the API application starts.

For local webhook delivery, expose port 8000 with a temporary HTTPS tunnel such
as ngrok:

```bash
ngrok http 8000
```

Tunnel URLs change between sessions on free plans. Update the GitHub App webhook
URL whenever the tunnel URL changes.

### Approved GitHub mutations

The current MVP uses a separate fine-grained personal access token for approved
branch, commit, and remediation-PR writes. Scope it only to the disposable
repository with:

- `Contents`: read and write;
- `Pull requests`: read and write.

Add it to `.env`:

```dotenv
GITHUB_TOKEN=your_fine_grained_repository_token
```

Restart the workers. Without `GITHUB_TOKEN`, analysis and approval still work,
but the GitHub mutation worker is intentionally not started.

Opening or updating a pull request should now produce:

```text
webhook accepted
→ GitHub ingestion worker downloads an immutable snapshot
→ per-file analysis jobs created
→ dashboard shows the source PR and file status
→ validated finding awaits reviewer decision
→ approval creates or reconciles a remediation PR
```

More detail is available in [github-app.md](github-app.md).

## 10. Run verification checks

Unit tests:

```bash
source .venv/bin/activate
python -m unittest discover -s tests/unit -v
```

Frontend type checking and production build:

```bash
cd frontend
npm run lint
npm run build
```

Database integration commands, isolation requirements, and evaluation runners
are documented in [../tests/README.md](../tests/README.md) and
[evaluation.md](evaluation.md).

## Troubleshooting

### `Set GEMINI_REASONING_MODEL or pass an explicit model`

Confirm `.env` contains a supported model name with no spaces around `=` and
restart the worker process.

### `stale_source: Source file does not exist`

`VSE_REPOSITORY_ROOT` must point to the repository root, while the submitted
source path must be relative to that root. GitHub-originated jobs use immutable
database snapshots and do not require the PR repository to be cloned locally.

### `403 Forbidden` when approving or rejecting

The viewer key cannot make decisions. Enter `VSE_REVIEWER_API_KEY` in the
dashboard before approving or rejecting.

### Workers start but no GitHub delivery is processed

Confirm that both `GITHUB_APP_ID` and `GITHUB_APP_PRIVATE_KEY_PATH` are set,
the App is installed on the source repository, the webhook URL is current, and
the worker was restarted after configuration changes.

### Port 5432 is already in use

Stop the existing PostgreSQL container/service or reuse it by setting
`DATABASE_URL` appropriately. Do not start the Compose service on the same
port.
