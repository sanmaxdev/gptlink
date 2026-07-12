# GPTLink plugin for Hermes Agent

GPTLink follows Hermes’s supported plugin architecture:

- The explicitly enabled `gptlink` plugin owns installation, authentication, subprocesses, local credentials, server lifecycle, and image generation.
- The bundled `gptlink-image` skill contains workflow instructions only and calls the plugin’s typed tools.
- The community skill contains no executable scripts, environment access, secret handling, administrator commands, or subprocess code. It passes Hermes Skills Guard as `SAFE`.

Do not use `hermes skills install sanmaxdev/gptlink/skills/gptlink-image`. Install the plugin instead; it registers the bundled skill automatically.

## 1. Install and enable the plugin

On the Ubuntu VPS, as the same Linux user that runs Hermes:

```bash
hermes plugins install sanmaxdev/gptlink --enable
```

This is Hermes’s explicit trust boundary for third-party executable code. The plugin is opt-in and does not load until enabled.

Restart the long-running Hermes gateway after installation, or exit and reopen the Hermes CLI. Verify discovery:

```bash
hermes plugins list
```

Expected plugin name: `gptlink`. With plugin debugging enabled, Hermes should report two registered tools: `gptlink_manage` and `gptlink_generate`.

## 2. Ask Hermes to set up GPTLink

Send this in the CLI, TUI, Telegram, Discord, or another Hermes chat:

```text
Set up GPTLink on this VPS and reuse my existing Codex authentication when possible.
```

Hermes calls `gptlink_manage` with `action: setup`. The plugin:

1. Clones the managed GPTLink service under `~/.local/share/gptlink`.
2. Creates an isolated Python environment and installs its declared dependencies.
3. Starts the API privately on `127.0.0.1:8787`.
4. Reuses compatible existing authentication when possible.
5. Creates and stores a dedicated internal GPTLink API key without exposing it to the model.

## Authentication order

The plugin checks:

1. `~/.codex/auth.json` for an existing Codex CLI session.
2. `$HERMES_HOME/auth.json`, normally `~/.hermes/auth.json`, for a fresh Hermes `openai-codex` provider or credential-pool token.
3. A new Codex device login only when neither source is usable.

Hermes authentication is read-only. GPTLink does not copy it into the Codex store, use its refresh token, modify it, or print it. Hermes remains responsible for refreshing its own OAuth session.

When reuse succeeds, Hermes reports either:

```text
auth_source: hermes
```

or:

```text
auth_source: codex_cli
```

No additional browser login is needed.

## Device login fallback

If no reusable authentication exists, `gptlink_manage` returns structured fields containing a verification URL and one-time code. Hermes presents them to the user:

```text
Open this verification link:
https://auth.openai.com/codex/device

Enter this code:
ABCD-EFGH

Approve access and reply "done".
```

After approval, reply `done`. Hermes calls `gptlink_manage` with `action: auth_complete`, verifies the account, creates its internal gateway key, and reports `ready`.

Never send ChatGPT passwords, browser cookies, OAuth tokens, `~/.codex/auth.json`, or `~/.hermes/auth.json` through chat.

## Generate images

Ask naturally:

```text
Generate a cinematic 16:9 image of Colombo during a futuristic rainy night.
```

Hermes calls `gptlink_generate`, which verifies the service before generation and returns an absolute local image path for native delivery.

Another example:

```text
Create a square minimal app icon showing a luminous bridge. Use high quality and return the original PNG as a document.
```

## Reference-image editing

Upload an image to Hermes or provide a local absolute path:

```text
Edit /home/hermes/inbox/product.png. Preserve the product exactly, replace the background with a warm studio set, and return a high-quality 4:3 PNG.
```

For multiple references:

```text
Use /home/hermes/inbox/person.png and /home/hermes/inbox/location.jpg as references. Place the same person in that location at sunset, vertical 9:16.
```

The plugin supports up to 16 reference paths.

## Manage GPTLink through Hermes

Ask naturally:

```text
Check GPTLink status.
Restart GPTLink and verify it is healthy.
Update GPTLink.
Rotate GPTLink's internal API key.
Show recent GPTLink logs and diagnose the problem.
```

Hermes maps these requests to the typed `gptlink_manage` actions `status`, `restart`, `update`, `rotate_key`, and `logs`.

## Storage

| Purpose | Location |
|---|---|
| Installed plugin checkout | Under `$HERMES_HOME/plugins/` |
| Managed GPTLink checkout | `~/.local/share/gptlink` |
| GPTLink virtual environment | `~/.local/share/gptlink/.venv` |
| Images and SQLite database | `~/.local/share/gptlink-data` |
| Internal gateway credential | `~/.config/gptlink/hermes.json` |
| Managed server logs and PID | `~/.local/state/gptlink-skill` |
| Codex CLI authentication | `~/.codex` |
| Hermes authentication | `$HERMES_HOME/auth.json` |

The internal gateway credential is written with permission mode `0600`. Port 8787 remains loopback-only.

## Update or remove

```bash
hermes plugins update gptlink
hermes plugins disable gptlink
hermes plugins remove gptlink
```

Restart a running Hermes gateway after plugin updates or enable/disable changes.

## Troubleshooting

- Plugin not listed: run `HERMES_PLUGINS_DEBUG=1 hermes plugins list` and inspect `hermes logs --level WARNING`.
- Tools not visible: confirm the plugin is enabled, then restart Hermes.
- Missing Python venv support or Git: install the named Ubuntu package returned by `gptlink_manage`, then ask Hermes to resume setup.
- Expired authentication: ask Hermes to set up GPTLink again; it returns a new device link and code only if reuse fails.
- Invalid internal key: ask Hermes to rotate it, then retry once.
- Allocation reached: wait for the reported ChatGPT/Codex allocation reset instead of repeatedly retrying.

## Security verification

The standalone workflow skill is intentionally non-executable. Release validation runs Hermes’s current `tools/skills_guard.py` against `skills/gptlink-image` and requires:

```text
Verdict: SAFE
Decision: ALLOWED
```

The plugin contains powerful code because it must manage authentication and processes. Hermes installs and enables plugins through a separate explicit opt-in flow designed for that purpose.
