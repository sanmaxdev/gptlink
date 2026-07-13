# Background jobs and signed webhooks

GPTLink 0.6 adds a durable image queue shared by the HTTP API, dashboard, and
MCP. Queued and running records live in SQLite, interrupted running jobs return
to the queue after restart, and generated files remain in the normal image
directory.

## Queue work

Create a generation job:

```bash
curl https://images.example.com/v1/jobs \
  -H "Authorization: Bearer $GPTLINK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "operation": "generate",
    "prompt": "A calm futuristic harbor at sunrise",
    "aspect_ratio": "16:9",
    "quality": "high",
    "output_format": "png",
    "n": 2,
    "metadata": {"project": "harbor-campaign"}
  }'
```

For edits, set `operation` to `edit` and add up to 16 `reference_images` plus
an optional `mask_image`. Values may be an HTTPS URL, an image data URL, or a
server-local path allowed by `GPTLINK_MCP_ALLOWED_ROOTS`. A variation uses
`operation: variation` and exactly one reference.

Existing Images endpoints can also opt in without changing their payload:

```bash
curl https://images.example.com/v1/images/generations \
  -H "Authorization: Bearer $GPTLINK_API_KEY" \
  -H "Prefer: respond-async" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"A clean product hero image","size":"1536x864"}'
```

Both forms return HTTP `202` and an opaque `job_...` identifier.

## Poll, list, and cancel

```bash
curl -H "Authorization: Bearer $GPTLINK_API_KEY" \
  https://images.example.com/v1/jobs/job_REPLACE_ME

curl -H "Authorization: Bearer $GPTLINK_API_KEY" \
  "https://images.example.com/v1/jobs?status=completed&limit=20"

curl -X POST -H "Authorization: Bearer $GPTLINK_API_KEY" \
  https://images.example.com/v1/jobs/job_REPLACE_ME/cancel
```

States are `queued`, `running`, `completed`, `failed`, and `cancelled`.
Cancellation is intentionally limited to queued work. Completed results expose
compact image paths and URLs, not base64 output.

MCP clients use `gptlink_job_create`, `gptlink_job_status`, `gptlink_jobs`, and
`gptlink_job_cancel` with the same semantics.

## Enable webhook delivery

Set a random signing secret on the GPTLink server. Never send this secret in a
job body or commit it to the repository.

```bash
GPTLINK_WEBHOOK_SECRET="$(openssl rand -hex 32)"
GPTLINK_WEBHOOK_ALLOWED_HOSTS=hooks.example.com
```

Then include `webhook_url` in a job request. The secret must contain at least
32 characters. Callback URLs must use HTTPS, cannot contain URL credentials or
fragments, cannot redirect, and must resolve to public addresses. Every host
must appear in the comma-separated exact `GPTLINK_WEBHOOK_ALLOWED_HOSTS`
operator allowlist.

Private RFC1918 callbacks are disabled by default. They require both
`GPTLINK_WEBHOOK_ALLOW_PRIVATE=true` and an exact hostname in the allowlist.
Loopback, link-local, multicast, reserved, and unspecified addresses stay
blocked. Also enforce egress policy at the VPS firewall when possible.

GPTLink sends `image_job.completed` or `image_job.failed` with these headers:

```text
X-GPTLink-Delivery: whd_...
X-GPTLink-Event: image_job.completed
X-GPTLink-Timestamp: 1780000000
X-GPTLink-Signature: v1=<hex HMAC-SHA256>
```

The signature input is the ASCII timestamp, one period, and the exact raw HTTP
body. Verify it before parsing or acting on the event:

```python
import hashlib
import hmac
import time

def verify_gptlink(body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, f"v1={expected}")
```

Store processed `X-GPTLink-Delivery` values to make the receiver idempotent.

## Delivery retries and operation

Non-2xx responses and network failures are retried with exponential backoff,
starting at five seconds and capping at one hour. Six attempts are made by
default; set `GPTLINK_WEBHOOK_MAX_ATTEMPTS` from 1 to 12 to change this. Delivery
state, attempts, last HTTP status, and sanitized error appear in job status.

`GPTLINK_JOB_WORKERS` controls concurrent background workers from 1 to 4. Start
with one on subscription-backed deployments. Run one GPTLink service process;
worker threads claim SQLite records transactionally. Jobs and deliveries use
at-least-once recovery, so receivers must deduplicate delivery IDs and an
interrupted generation may be retried after restart.
