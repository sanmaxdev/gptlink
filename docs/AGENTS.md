# Agent installation and operation guide

This document is written for both users and coding agents. If you are an agent
asked to install GPTLink, follow the autonomous procedure below and stop only
when browser-based device approval or missing administrator authority genuinely
requires the user.

## What GPTLink provides

One installation exposes:

- MCP over local stdio or authenticated Streamable HTTP.
- An OpenAI-compatible `/v1` image API.
- `gptlink_status`, `gptlink_models`, `gptlink_generate`, `gptlink_edit`,
  `gptlink_variation`, and `gptlink_history`.
- A concise image workflow skill for the target agent.

MCP results contain saved paths and URLs instead of large base64 payloads.

## Autonomous installation procedure

### 1. Select the target

Use the agent that is currently running:

| Current agent | Installer value |
|---|---|
| Claude Code | `claude-code` |
| Google Antigravity | `antigravity` |
| Codex | `codex` |
| OpenCode | `opencode` |
| Unknown or several installed agents | `all` |
| Hermes | Use the Hermes plugin procedure below |

Choose `user` scope unless the user explicitly wants a project-only Claude Code,
Antigravity, or OpenCode integration. Codex uses user scope.

Choose local mode when the agent and Codex authentication live on the same
machine. Choose remote mode when an existing GPTLink service is hosted on a
different server.

Choose the container procedure in [DOCKER.md](DOCKER.md) when the user asks for
Docker, Compose, portable isolation, or container deployment. A container hosts
the gateway; agents on the host or another machine connect to it through remote
MCP with a dedicated GPTLink key.

### 2. Install or update the repository

Use a stable user-owned location. Preserve an existing installation and update
it with a fast-forward pull:

```bash
GPTLINK_HOME="${GPTLINK_HOME:-$HOME/.local/share/gptlink}"
if [ -d "$GPTLINK_HOME/.git" ]; then
  git -C "$GPTLINK_HOME" pull --ff-only
else
  git clone https://github.com/sanmaxdev/gptlink.git "$GPTLINK_HOME"
fi
cd "$GPTLINK_HOME"
```

Do not overwrite a dirty checkout. Report the local changes and ask before
changing course.

### 3. Bootstrap the current agent

```bash
python3 scripts/bootstrap-agent.py \
  --agent claude-code \
  --scope user \
  --mode local
```

Replace `claude-code` with the selected target. The bootstrapper:

1. Requires Python 3.11 or newer.
2. Creates `.venv` when absent.
3. Installs `requirements.txt` into that environment.
4. Merges MCP configuration without deleting unrelated servers.
5. Installs the shared `gptlink-images` skill.
6. Restricts local reference/output paths to the configured allowed roots.

For Windows PowerShell:

```powershell
$GPTLinkHome = Join-Path $HOME '.local\share\gptlink'
if (Test-Path (Join-Path $GPTLinkHome '.git')) {
    git -C $GPTLinkHome pull --ff-only
} else {
    git clone https://github.com/sanmaxdev/gptlink.git $GPTLinkHome
}
Set-Location $GPTLinkHome
py scripts\bootstrap-agent.py --agent claude-code --scope user --mode local
```

### 4. Reuse or complete authentication

Local MCP reads current-user authentication in this order:

1. A fresh Codex CLI session under `$CODEX_HOME`, normally `~/.codex`.
2. A compatible fresh Hermes `openai-codex` session when present.
3. A new Codex device login when neither is usable.

Never copy, print, upload, or place OAuth credentials in MCP configuration.

If authentication is missing, run as the same user that will run the agent:

```bash
codex login --device-auth
```

Give the user the verification URL and one-time code. Wait for approval, then
check `codex login status`. Do not ask the user to paste passwords, cookies, or
token files.

### 5. Reload and verify

Agent MCP configuration normally loads at session start:

- Claude Code: restart or inspect `/mcp`.
- Antigravity: restart, open `/mcp`, and reload the server.
- Codex: restart and run `codex mcp get gptlink` if diagnosis is needed.
- OpenCode: restart, then inspect the MCP tools or run `opencode mcp list`.

Once the tools are available, call `gptlink_status`. Completion requires
`ready: true`. Do not consume an image allocation for a smoke test unless the
user requested generation.

Report:

- The installed target and scope.
- Local or remote mode.
- Authentication source when returned.
- Whether a restart is still required.
- The first natural-language image prompt the user can try.

## Local installation options

Install all detected agents:

```bash
python3 scripts/bootstrap-agent.py --agent all --scope user --mode local
```

Install one:

```bash
python3 scripts/bootstrap-agent.py --agent claude-code --scope user --mode local
python3 scripts/bootstrap-agent.py --agent antigravity --scope user --mode local
python3 scripts/bootstrap-agent.py --agent codex --scope user --mode local
python3 scripts/bootstrap-agent.py --agent opencode --scope user --mode local
```

Limit file access to explicit roots:

```bash
python3 scripts/bootstrap-agent.py \
  --agent claude-code \
  --scope user \
  --mode local \
  --allowed-root /home/me/projects \
  --allowed-root /home/me/images
```

User scope defaults to the current user's home directory. Project scope defaults
to the chosen workspace.

## Remote GPTLink installation

Remote mode requires a running HTTPS GPTLink service and a dedicated gateway
key. It does not use or transmit the client's Codex OAuth credential.

Create one key per agent on the server:

```bash
sudo -u gptlink -H /opt/gptlink/.venv/bin/python \
  /opt/gptlink/manage.py create-key Claude-Code
```

On the client:

```bash
export GPTLINK_API_KEY='gptlink_generated_secret'
python3 scripts/bootstrap-agent.py \
  --agent claude-code \
  --scope user \
  --mode remote \
  --url https://images.example.com
```

Requirements:

- Use HTTPS except for `127.0.0.1`.
- Configure the server's exact public origin through
  `GPTLINK_PUBLIC_BASE_URL=https://images.example.com`.
- Connect to `https://images.example.com/mcp/`.
- Revoke compromised keys independently through `manage.py revoke-key ID`.

Remote agents cannot use client-local reference paths. Pass an HTTP(S) URL or
data URL, or select local stdio mode.

### Docker-hosted remote service

For a container deployment, follow [DOCKER.md](DOCKER.md). Complete Codex device
login inside the container, start the service, create a distinct gateway key for
the active agent, and then run the normal remote bootstrap on the agent machine.
Keep the published container port loopback-only and place HTTPS in front of it
for any non-local client.

## Agent-specific details

### Claude Code

The installer uses the Claude CLI when available and installs the skill under
`~/.claude/skills/gptlink-images`. Project scope writes `.mcp.json` and a
project skill.

Manual remote fallback:

```bash
claude mcp add --scope user --transport http \
  gptlink https://images.example.com/mcp/ \
  --header "Authorization: Bearer $GPTLINK_API_KEY"
```

The validated distributable plugin is under `integrations/claude-code`.

### Antigravity

User configuration is merged into `~/.gemini/config/mcp_config.json`. Project
configuration is merged into `.agents/mcp_config.json`. The installer also
places a valid plugin containing the GPTLink skill in the matching plugin scope.

Manual remote fallback:

```json
{
  "mcpServers": {
    "gptlink": {
      "serverUrl": "https://images.example.com/mcp/",
      "headers": {
        "Authorization": "Bearer gptlink_your_key"
      }
    }
  }
}
```

Antigravity remote configuration uses `serverUrl`, not `url` or `httpUrl`.

### Codex

The installer uses `codex mcp add` and installs the skill under
`$CODEX_HOME/skills/gptlink-images`.

Manual local fallback:

```bash
codex mcp add gptlink -- /path/to/gptlink/.venv/bin/python \
  -m gptlink.mcp_server --transport stdio
```

Manual remote fallback:

```bash
export GPTLINK_API_KEY='gptlink_your_key'
codex mcp add gptlink \
  --url https://images.example.com/mcp/ \
  --bearer-token-env-var GPTLINK_API_KEY
```

### OpenCode

User configuration is merged into `~/.config/opencode/opencode.json`, and the
skill is installed under `~/.config/opencode/skills/gptlink-images`. Project
scope uses `opencode.json` and `.opencode/skills/gptlink-images` in the selected
workspace.

Manual local fallback:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "gptlink": {
      "type": "local",
      "command": [
        "/path/to/gptlink/.venv/bin/python",
        "-m",
        "gptlink.mcp_server",
        "--transport",
        "stdio"
      ],
      "enabled": true,
      "environment": {
        "PYTHONPATH": "/path/to/gptlink"
      }
    }
  }
}
```

Manual remote fallback:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "gptlink": {
      "type": "remote",
      "url": "https://images.example.com/mcp/",
      "enabled": true,
      "oauth": false,
      "headers": {
        "Authorization": "Bearer gptlink_your_key"
      }
    }
  }
}
```

OpenCode configuration uses `mcp`, `type`, `command`/`url`, and `environment`.
Remote GPTLink entries set `oauth: false` because they use a gateway Bearer key,
not MCP OAuth discovery. Do not reuse the `mcpServers`, `serverUrl`, or `env`
fields used by other clients.

### Hermes

Hermes uses its explicit plugin trust boundary instead of the universal MCP
bootstrapper:

```bash
hermes plugins install sanmaxdev/gptlink --enable
```

Restart Hermes, then ask:

```text
/gptlink-image Set up GPTLink here and reuse my existing Codex authentication.
```

The plugin manages installation, authentication reuse, device-login fallback,
the private service, its internal gateway key, updates, and image delivery. See
[HERMES.md](HERMES.md).

### Generic MCP clients

Local stdio command:

```bash
/path/to/gptlink/.venv/bin/python \
  -m gptlink.mcp_server --transport stdio
```

Use `integrations/generic/stdio.json` or `integrations/generic/remote.json` as
portable configuration templates.

## Image tool workflow

Use `gptlink_generate` for text-only requests, `gptlink_edit` for references or
masks, and `gptlink_variation` for source-preserving alternatives.

Defaults:

- `quality: auto`
- `output_format: png`
- `1:1` for icons/products
- `16:9` for banners/landscapes
- `9:16` for stories/phone assets
- `4:3` for editorial/general photography

For edits, state both the invariants and requested changes. Never silently omit
a reference. Return and render the saved file path when supported.

## Troubleshooting decision table

| Symptom | Action |
|---|---|
| MCP tool missing | Restart/reload the agent and inspect its MCP manager |
| `ready: false` | Complete Codex device login as the agent's OS user |
| Remote `401` | Replace or recreate that agent's GPTLink key |
| Remote `421` | Set the exact `GPTLINK_PUBLIC_BASE_URL`, then restart GPTLink |
| Local path rejected | Reinstall with a narrow additional `--allowed-root` |
| Remote local-file reference fails | Use HTTP(S), a data URL, or local mode |
| Allocation/rate-limit response | Wait for the reported reset; do not retry in a loop |
| Dirty managed checkout | Preserve changes and ask before updating |

Never expose Codex authentication files, Hermes authentication, browser cookies,
or OAuth tokens. Remote client configuration may contain only a revocable
GPTLink gateway key.
