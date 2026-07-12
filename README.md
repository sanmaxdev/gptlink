# GPTLink

GPTLink is a self-hostable OpenAI-compatible image gateway backed by your authenticated
ChatGPT/Codex session. It exposes GPT Image 2 generation and editing through a
local API key without requiring an OpenAI Platform API key. It implements the
GPT Image 2 portions of the Images API plus a focused Responses API bridge.

> [!IMPORTANT]
> GPTLink is an experimental, unofficial bridge. It is not an OpenAI product and
> it does not turn a ChatGPT subscription into an official OpenAI Platform API
> entitlement. Operate it only for an account you control, keep access private,
> and comply with the applicable OpenAI terms and usage limits.

## What it enables

- OpenAI-style API keys for agents such as Hermes
- Image generation, reference-based editing, masks, and variations
- Arbitrary supported aspect ratios and resolutions
- PNG, JPEG, WebP, multiple outputs, partial images, and SSE streaming
- A minimal local dashboard and image history
- Linux VPS operation behind HTTPS without exposing management routes
- Native MCP tools for Claude Code, Antigravity, Codex, and generic MCP clients
- One installer that merges agent configuration and installs the image skill

## Start on Windows

Double-click `Launch-GPTLink.cmd`. On the first run it creates a Python virtual
environment on this drive, installs dependencies, starts the service on
`http://127.0.0.1:8787`, and opens the dashboard.

Prerequisites:

- Codex CLI installed and available as `codex`
- Python 3.11 installed at the standard per-user location

## Self-host on a VPS

Use [docs/VPS.md](docs/VPS.md) for the complete Ubuntu, systemd, DNS, HTTPS,
Codex device-login, firewall, update, backup, and troubleshooting procedure.

The short version after cloning is:

```bash
sudo bash scripts/install-vps.sh
sudo -u gptlink -H codex login --device-auth
sudo systemctl start gptlink
sudo -u gptlink -H /opt/gptlink/.venv/bin/python /opt/gptlink/manage.py create-key Hermes
```

Keep GPTLink bound to `127.0.0.1`. The supplied Caddy example exposes only
`/v1/*`, generated files, and health; dashboard and key-management routes stay
available through an SSH tunnel.

## Connect Hermes

GPTLink uses an explicitly enabled Hermes plugin for executable and authentication
logic. Install it from the VPS shell:

```bash
hermes plugins install sanmaxdev/gptlink --enable
```

Restart the Hermes gateway or begin a new Hermes process so the two tools
`gptlink_manage` and `gptlink_generate` are loaded.

Then tell Hermes:

```text
/gptlink-image Set up GPTLink on this VPS and connect my Codex account.
```

Hermes handles the clone, virtual environment, dependencies, private server,
GPTLink API key, and local configuration. If Hermes or Codex CLI already has a
fresh OpenAI-Codex session, GPTLink reuses it read-only. Otherwise Hermes gives
you an OpenAI verification link and one-time device code. Open the link, enter
the code, approve access, and reply `done`; Hermes completes setup and can
generate images immediately. You do not copy API keys or run GPTLink commands.

Do not install `skills/gptlink-image` directly. It is a bundled, scanner-safe
workflow registered by the plugin. See [docs/HERMES.md](docs/HERMES.md) for the
complete autonomous flow, reference-image use, updates, recovery, and security
behavior.

## Connect Claude Code, Antigravity, Codex, and other agents

GPTLink includes a native MCP server over local stdio and authenticated
Streamable HTTP. Install every supported local agent in one command:

```bash
python scripts/install-agent.py --agent all --scope user --mode local
```

Or connect one agent to a hosted GPTLink service:

```bash
export GPTLINK_API_KEY='gptlink_your_agent_key'
python scripts/install-agent.py --agent claude-code --scope user --mode remote \
  --url https://images.example.com
```

Available MCP tools are `gptlink_status`, `gptlink_models`,
`gptlink_generate`, `gptlink_edit`, `gptlink_variation`, and
`gptlink_history`. See [docs/AGENTS.md](docs/AGENTS.md) for complete Claude Code,
Antigravity, Codex, generic MCP, local/remote, reference-image, and security
instructions.

## API

Create a `gptlink_...` key in the dashboard, then call:

```powershell
$headers = @{
    Authorization = 'Bearer gptlink_your_key'
    'Content-Type' = 'application/json'
}
$body = @{
    prompt = 'A futuristic tropical city at golden hour'
    model = 'gpt-image-2-medium'
    size = '1024x1024'
    response_format = 'url'
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri 'http://127.0.0.1:8787/v1/images/generations' `
    -Method Post `
    -Headers $headers `
    -Body $body
```

Endpoints:

- `POST /v1/images/generations`
- `POST /v1/images/edits`
- `POST /v1/images/variations` (reference-based emulation)
- `POST /v1/responses` (image-generation tool requests)
- `GET /v1/models`
- `GET /api/status`
- `GET /health`
- `POST /mcp/` (MCP Streamable HTTP; accepts the same Bearer key)

Supported image aliases are `gpt-image-2-low`, `gpt-image-2-medium`,
`gpt-image-2-high`, and `gpt-image-2-auto`.

### Image controls

- `size`: `auto` or any valid `WIDTHxHEIGHT` resolution
- `aspect_ratio`: GPTLink convenience value such as `16:9`, used instead of `size`
- `quality`: `auto`, `low`, `medium`, or `high`
- `n`: 1–10 outputs (one Codex image call per output)
- `output_format`: `png`, `jpeg`, or `webp`
- `output_compression`: 0–100 for JPEG or WebP
- `background`: `auto` or `opaque`
- `moderation`: `auto` or `low`
- `stream`: stream Server-Sent Events
- `partial_images`: 0–3 previews

GPT Image 2 accepts up to 16 reference images. Send them as repeated `image`
multipart fields to `/v1/images/edits`; an optional PNG `mask` field enables
masked editing. GPT Image 2 always uses high input fidelity and does not support
transparent output, so GPTLink intentionally does not expose those controls.

## Development

```powershell
./Setup-GPTLink.ps1
.venv/Scripts/python.exe -m pytest
.venv/Scripts/python.exe run.py
```

GPTLink binds to localhost by default. Codex OAuth tokens remain in the Codex
credential store under the active `CODEX_HOME`; GPTLink does not copy them into
its database. Local API keys are stored only as SHA-256 hashes.

## Security model

- Do not bind GPTLink directly to a public interface.
- Do not expose `/api/*` or the dashboard through the reverse proxy.
- Treat the Codex credential directory and GPTLink API keys as secrets.
- Use a separate key per agent and revoke lost keys with `python manage.py revoke-key ID`.

Licensed under the [MIT License](LICENSE).
