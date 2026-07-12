---
name: gptlink-image
description: Autonomously install, authenticate, operate, update, and use the self-hosted GPTLink image gateway. Use whenever the user asks Hermes to set up GPTLink or Codex image access, connect a ChatGPT/Codex subscription through device login, manage the local gateway or API key, generate images, edit images with references, select aspect ratio or quality, or troubleshoot GPTLink.
version: 2.0.0
author: sanmaxdev
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [creative, image-generation, setup, self-hosted, codex, gptlink]
    category: creative
    requires_tools: [terminal]
---

# GPTLink Autonomous Image Operator

Manage the complete GPTLink lifecycle for the user. Do not ask the user to run installation, server, key-management, or configuration commands that this skill can run itself.

## Mandatory state machine

Before every generation or edit, run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/gptlink_operator.py ensure
```

Parse its JSON `state`:

- `ready`: continue with the image request immediately.
- `authentication_required`: send the user a clickable `verification_url` and clearly formatted `user_code`. Tell them to open the link, enter the code, approve access, and reply `done`. Stop until they reply.
- `authentication_pending`: remind the user to finish the browser step. Do not start a second login unless they ask for a new code.
- `error`: inspect the message, try the recovery rules below, and only request the smallest prerequisite the skill cannot install without elevated OS access.

Inspect `auth_source` when ready:

- `hermes`: GPTLink is reusing the fresh OpenAI-Codex access token already maintained in the active Hermes auth store.
- `codex_cli`: GPTLink is reusing the Codex CLI session from `~/.codex/auth.json`.

Prefer those existing sessions in that order of availability. Do not initiate another login when `ensure` returns `ready` with either source.

When the user replies that authentication is complete, run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/gptlink_operator.py auth-complete
```

Continue automatically if it returns `ready`. The operator creates and securely saves a dedicated API key; never ask the user to copy or configure that key.

## First-time setup

When asked to install, set up, connect, or configure GPTLink, run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/gptlink_operator.py setup
```

The operator installs GPTLink under `~/.local/share/gptlink`, installs Python dependencies in its own virtual environment, installs Codex CLI into `~/.local` when npm is available, starts a private localhost server, initiates device login when necessary, and stores its gateway credential at `~/.config/gptlink/hermes.json` with mode `0600`.

Authentication order is automatic:

1. Reuse a fresh Codex CLI session from `~/.codex/auth.json` when present.
2. Otherwise reuse the active Hermes OpenAI-Codex session from `$HERMES_HOME/auth.json` (normally `~/.hermes/auth.json`) read-only.
3. Only when neither store has a fresh compatible access token, initiate Codex device login and give the user the verification link and code.

Never copy tokens between the Hermes and Codex stores. Never refresh, modify, print, or expose the Hermes token. GPTLink reads only the current access token for the image request; Hermes remains responsible for refreshing its own session.

Never expose port 8787 publicly. Hermes and GPTLink communicate through `127.0.0.1` on the same VPS.

## Generate an image

After `ensure` returns `ready`, run:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/gptlink_image.py \
  "USER'S COMPLETE IMAGE PROMPT" \
  --aspect-ratio 1:1 --quality auto --format png \
  --output /tmp/gptlink-image.png
```

Match explicit user choices. Otherwise choose:

- `1:1` for icons, product images, and unspecified requests.
- `16:9` for landscapes, banners, and presentation visuals.
- `9:16` for stories, reels, and phone wallpapers.
- `4:3` for editorial and general photography.
- `high` only when the user prioritizes final quality; otherwise use `auto`.

## Edit with references

Resolve each reference to an existing absolute local path. Then add one `--reference` per image:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/gptlink_image.py \
  "Preserve the subject exactly and replace the background with a snowy mountain" \
  --reference /absolute/path/source.png \
  --aspect-ratio 4:3 --quality high \
  --output /tmp/gptlink-edit.png
```

Use up to 16 references. State what to preserve and what to change. Never silently omit a requested reference.

## Deliver the result

The image client prints one absolute path. Include that bare path in the final response so Hermes delivers it to the active chat. Add `[[as_document]]` when the user requests original quality, a downloadable file, or no platform recompression.

## Management requests

- Status: `python3 ${HERMES_SKILL_DIR}/scripts/gptlink_operator.py status`
- Restart: `python3 ${HERMES_SKILL_DIR}/scripts/gptlink_operator.py restart`
- Update: `python3 ${HERMES_SKILL_DIR}/scripts/gptlink_operator.py update`
- Rotate the internal API key: `python3 ${HERMES_SKILL_DIR}/scripts/gptlink_operator.py rotate-key`
- Inspect logs: `python3 ${HERMES_SKILL_DIR}/scripts/gptlink_operator.py logs`

Do not reveal the stored gateway key. Do not print `~/.codex/auth.json` or `~/.config/gptlink/hermes.json`.

## Recovery rules

- If `python3-venv` is missing, ask the user only to run `sudo apt-get install -y python3-venv`, then resume setup yourself.
- If both Codex and npm are missing, ask the user only to install Node.js 20+ and npm, then resume setup yourself.
- If git is missing, ask the user only to run `sudo apt-get install -y git`, then resume.
- On authentication failure or expiry, rerun `setup` and present the new device link and code.
- On allocation or rate-limit errors, report the reset/limit information and do not repeatedly retry.
- On a server failure, run `restart`, then `logs` if restart fails.
- On `401`, run `rotate-key` and retry the image once.

Load [references/api.md](references/api.md) only for masks, direct API calls, streaming, multiple outputs, or advanced parameters.
