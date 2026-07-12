# Connect coding agents to GPTLink

GPTLink offers two interfaces from one installation:

- MCP for Claude Code, Antigravity, Codex, Cursor, Windsurf, and other agents.
- An OpenAI-compatible `/v1` API for applications and SDKs.

The MCP server provides `gptlink_status`, `gptlink_models`, `gptlink_generate`,
`gptlink_edit`, `gptlink_variation`, and `gptlink_history`. It returns compact
metadata, saved file paths, and URLs rather than filling the model context with
base64 image data.

## Fastest setup on the same machine

Run this from the GPTLink clone with its environment activated:

```bash
python scripts/install-agent.py --agent all --scope user --mode local
```

The installer detects the supported CLIs, merges configuration, installs the
GPTLink image skill, and points each agent at the local stdio MCP server. It
does not copy Codex or Hermes OAuth credentials. The MCP process reads the same
current-user authentication that GPTLink already uses.

Install only one agent:

```bash
python scripts/install-agent.py --agent claude-code --scope user --mode local
python scripts/install-agent.py --agent antigravity --scope user --mode local
python scripts/install-agent.py --agent codex --scope user --mode local
```

For a repository-only setup, run from that repository and use `--scope project`.
Claude Code and Antigravity support project scope. Codex currently uses its
user MCP configuration, so install it with `--scope user`.

By default, a user-scope local installation permits image references and output
paths under the current user's home directory. Narrow or extend this explicitly:

```bash
python scripts/install-agent.py --agent claude-code --scope user --mode local \
  --allowed-root /home/me/projects --allowed-root /home/me/images
```

Restart the agent after installation. Then ask:

```text
Check GPTLink status, then generate a high-quality 16:9 cinematic image of a
rainy futuristic Colombo skyline and save it in my project assets folder.
```

## Connect agents to a remote GPTLink VPS

First create a separate key for every agent:

```bash
sudo -u gptlink -H /opt/gptlink/.venv/bin/python /opt/gptlink/manage.py create-key Claude-Code
sudo -u gptlink -H /opt/gptlink/.venv/bin/python /opt/gptlink/manage.py create-key Antigravity
```

Then run the installer on the client machine:

```bash
export GPTLINK_API_KEY='gptlink_generated_secret'
python scripts/install-agent.py --agent claude-code --scope user --mode remote \
  --url https://images.example.com
```

Use HTTPS for any non-loopback connection. The key is a GPTLink gateway key,
not a Codex OAuth token. Revoke it independently with `manage.py revoke-key`.

Remote agents cannot send their local filesystem paths directly to a VPS. For
reference editing, use an HTTP(S) URL or a data URL, or choose local stdio mode.
Server-local paths are limited to `GPTLINK_MCP_ALLOWED_ROOTS`.

## Claude Code

The universal installer is the easiest route. GPTLink also ships a validated
Claude plugin under `integrations/claude-code` for marketplace or managed-plugin
distribution. The plugin bundles the MCP server declaration and image skill.

Manual remote connection:

```bash
claude mcp add --scope user --transport http \
  --header "Authorization: Bearer $GPTLINK_API_KEY" \
  gptlink https://images.example.com/mcp/
```

Verify with `/mcp` inside Claude Code.

## Antigravity

The installer writes the global configuration to
`~/.gemini/config/mcp_config.json`, or the project configuration to
`.agents/mcp_config.json`. It also installs a valid Antigravity plugin containing
the image skill.

A manual remote entry uses `serverUrl`:

```json
{
  "mcpServers": {
    "gptlink": {
      "serverUrl": "https://images.example.com/mcp/",
      "headers": {"Authorization": "Bearer gptlink_your_key"}
    }
  }
}
```

Open `/mcp` in Antigravity to inspect connection status and reload it.

## Codex

The installer uses the supported `codex mcp add` command and installs the skill
under `$CODEX_HOME/skills/gptlink-images`.

Manual local setup:

```bash
codex mcp add gptlink -- /path/to/gptlink/.venv/bin/python \
  -m gptlink.mcp_server --transport stdio
```

Manual remote setup keeps the token in an environment variable:

```bash
export GPTLINK_API_KEY='gptlink_your_key'
codex mcp add gptlink --url https://images.example.com/mcp/ \
  --bearer-token-env-var GPTLINK_API_KEY
```

Verify with `codex mcp get gptlink`.

## Generic MCP clients

Use `integrations/generic/stdio.json` as a local template and
`integrations/generic/remote.json` as a hosted template. Local clients launch:

```bash
/path/to/gptlink/.venv/bin/python -m gptlink.mcp_server --transport stdio
```

The standalone HTTP transport is also available when it should run separately
from the main API server:

```bash
python -m gptlink.mcp_server --transport http --host 127.0.0.1 --port 8790
```

The normal GPTLink web service already mounts authenticated Streamable HTTP at
`/mcp/`, so a separate process is usually unnecessary.

## Tool usage examples

Text-to-image:

```text
Use gptlink_generate with prompt="A minimal luminous bridge app icon",
aspect_ratio="1:1", quality="high", output_format="png".
```

Reference edit:

```text
Use gptlink_edit with reference_images=["/home/me/product.png"]. Preserve the
product, logo, colors, and proportions exactly; replace only the background with
a warm premium studio set. Use 4:3 and high quality.
```

Multiple references and outputs:

```text
Combine person.png and location.jpg into a coherent 9:16 scene. Preserve the
person's identity and clothing, use the location at sunset, and create 3 options.
```

Exact dimensions:

```text
Generate a WebP hero image at size 2048x1152 with compression 82.
```

## Troubleshooting

- Tool missing: restart the agent and inspect its MCP manager.
- Not authenticated: run Codex device login as the same user as local MCP, or
  authenticate the VPS service user for remote mode.
- Remote `401`: create or replace the per-agent GPTLink key.
- Remote `421`: set `GPTLINK_PUBLIC_BASE_URL=https://your-real-domain` in
  `/etc/gptlink.env`, restart GPTLink, and retry.
- Local path rejected: add a narrow `--allowed-root` during installation.
- Reference unavailable remotely: use an accessible URL or local stdio mode.
- Allocation/rate-limit error: wait for the subscription allocation to reset.

Never place Codex `auth.json`, Hermes authentication, browser cookies, or OAuth
tokens in agent configuration. Only GPTLink gateway keys belong in remote MCP
client settings.
