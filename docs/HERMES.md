# Autonomous GPTLink setup for Hermes Agent

The `gptlink-image` skill can install and operate GPTLink itself on the same Ubuntu VPS as Hermes. The user performs only the browser approval required by Codex device authentication. No domain, reverse proxy, public port, or manually copied GPTLink API key is needed.

## What Hermes manages

The skill automatically:

1. Clones or updates GPTLink under `~/.local/share/gptlink`.
2. Creates an isolated Python virtual environment and installs dependencies.
3. Finds Codex CLI or installs it under `~/.local` using npm.
4. Starts GPTLink privately on `127.0.0.1:8787`.
5. Reuses the existing Hermes or Codex CLI authentication when compatible.
6. Requests a Codex device-login URL and one-time code only when no reusable session exists.
7. Creates a dedicated GPTLink API key without displaying it.
8. Stores the key in `~/.config/gptlink/hermes.json` with permission mode `0600`.
9. Restarts the local gateway when needed before image requests.
10. Generates or edits images and returns local files to the active Hermes chat.

## Prerequisites

Hermes must run on Linux with its terminal tool enabled. The VPS needs:

- Python 3 with `venv` support
- Git
- Node.js 20+ and npm only when Codex CLI is not already installed
- Outbound HTTPS access

The skill installs everything it can without administrator access. If an OS package is absent, Hermes asks for only the specific one-time `apt` command it cannot perform as an unprivileged user, then resumes setup itself.

## 1. Install the skill

Run this once in the VPS shell:

```bash
hermes skills install sanmaxdev/gptlink/skills/gptlink-image
```

Confirm it is available:

```bash
hermes skills list
```

No environment variables or GPTLink API keys need to be configured.

## Authentication reuse order

The operator checks authentication before starting a new login:

1. **Codex CLI session:** if `~/.codex/auth.json` contains a fresh access token, GPTLink uses it normally.
2. **Hermes OpenAI-Codex session:** if the active `$HERMES_HOME/auth.json` (normally `~/.hermes/auth.json`) contains a fresh `openai-codex` provider or credential-pool token, GPTLink reads that access token directly for image requests.
3. **New device login:** only if neither source is usable does Hermes initiate a new Codex device-code login.

The Hermes store is read-only to GPTLink. GPTLink does not copy its token to `~/.codex`, use its refresh token, rotate it, or write back to `auth.json`. Hermes remains the only component responsible for refreshing its own OAuth session. This avoids two programs competing to rotate the same refresh token.

If Hermes is already actively working through OpenAI Codex, setup normally skips the browser authorization step and reports `auth_source: hermes`. If Hermes uses Codex app-server runtime, it normally reports `auth_source: codex_cli`.

## 2. Tell Hermes to set everything up

In the Hermes CLI, TUI, Telegram, Discord, or another connected chat, send:

```text
/gptlink-image Set up GPTLink on this VPS and connect my Codex account.
```

Hermes runs the bundled operator. If it finds existing compatible authentication, it finishes automatically. Only when authentication is needed does Hermes respond with content similar to:

```text
Open this verification link:
https://auth.openai.com/codex/device

Enter this one-time code:
ABCD-EFGH

Approve access, then reply "done".
```

Open the clickable link on any computer or phone, enter the displayed code, and approve the account. Do not send ChatGPT passwords, session cookies, access tokens, or the contents of `~/.codex/auth.json` to Hermes.

## 3. Complete authorization

Reply to Hermes:

```text
done
```

Hermes checks the account, creates its internal gateway key, stores it securely, and reports that GPTLink is ready. If approval has not propagated yet, it asks you to finish the browser step and retry; it should not issue repeated device codes unnecessarily.

## 4. Generate images

Examples:

```text
/gptlink-image Create a cinematic 16:9 image of Colombo during a futuristic rainy night.
```

```text
/gptlink-image Generate a square minimal app icon showing a luminous bridge. Use high quality and return the original PNG as a document.
```

Before each request, Hermes verifies that GPTLink is installed, authenticated, running, and has a valid internal key. If the server stopped after a reboot, the skill starts it again automatically.

## 5. Edit with reference images

Give Hermes an uploaded image or an absolute path it can access:

```text
/gptlink-image Edit /home/hermes/inbox/product.png. Preserve the product exactly, replace the background with a warm studio set, and return a high-quality 4:3 PNG.
```

For several references:

```text
/gptlink-image Use /home/hermes/inbox/person.png and /home/hermes/inbox/location.jpg as references. Place the same person in that location at sunset, vertical 9:16.
```

The skill supports up to 16 references. Hermes downloads the generated result to a local file and returns the absolute path so Telegram, Discord, Slack, or the CLI can deliver it.

## Management through conversation

The user can ask naturally:

```text
/gptlink-image Check GPTLink status.
/gptlink-image Restart GPTLink and tell me whether it is healthy.
/gptlink-image Update GPTLink to the newest version.
/gptlink-image Rotate its internal API key.
/gptlink-image Show the recent GPTLink logs and diagnose the failure.
```

Hermes uses the operator’s `status`, `restart`, `update`, `rotate-key`, and `logs` actions. It must not reveal the stored gateway key or Codex credential file.

## Storage locations

For the Linux user running Hermes:

| Purpose | Location |
|---|---|
| GPTLink checkout | `~/.local/share/gptlink` |
| Python environment | `~/.local/share/gptlink/.venv` |
| Generated images and database | `~/.local/share/gptlink-data` |
| Managed gateway credential | `~/.config/gptlink/hermes.json` |
| Server PID and logs | `~/.local/state/gptlink-skill` |
| Codex authentication | `~/.codex` |

The managed credential file is created with permission mode `0600`. GPTLink listens only on `127.0.0.1` and should not be exposed publicly.

## Recovery behavior

- Missing `python3-venv`: Hermes requests `sudo apt-get install -y python3-venv`, then resumes.
- Missing Git: Hermes requests `sudo apt-get install -y git`, then resumes.
- Missing Codex and npm: Hermes asks for Node.js 20+ and npm, installs Codex itself, then resumes.
- Expired Codex session: Hermes starts a new device authorization and returns the new link and code.
- Invalid internal API key: Hermes rotates the key and retries once.
- Server stopped: Hermes starts it automatically.
- Server failure: Hermes restarts it and reads its own logs.
- Allocation or rate limit reached: Hermes reports the limit rather than repeatedly retrying.

## Manual diagnostic fallback

These are optional operator checks; normal users should ask Hermes instead:

```bash
python3 ~/.hermes/skills/gptlink-image/scripts/gptlink_operator.py status
python3 ~/.hermes/skills/gptlink-image/scripts/gptlink_operator.py logs
curl -fsS http://127.0.0.1:8787/health
```

If a profile uses a different `HERMES_HOME`, locate the installed skill with `hermes skills list` and run the operator from that skill directory.
