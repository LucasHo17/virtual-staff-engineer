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
