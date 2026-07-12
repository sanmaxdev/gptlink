---
name: gptlink-image
description: Operate GPTLink through the explicitly enabled GPTLink Hermes plugin. Use when the user asks to set up or manage the GPTLink image API, connect existing Hermes or Codex authentication, complete device authorization, generate images, edit images with references, select aspect ratio or quality, or diagnose the local image gateway.
version: 3.0.0
author: sanmaxdev
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [creative, image-generation, self-hosted, codex, gptlink]
    category: creative
    requires_tools: [gptlink_manage, gptlink_generate]
---

# GPTLink Images

Use only the plugin tools. Do not recreate installation, authentication, key management, HTTP, or process-control logic through terminal commands.

## Setup and authentication

Call `gptlink_manage` with `action: setup`.

Handle its state exactly:

- `ready`: report that GPTLink is ready. Mention `auth_source` when present.
- `authentication_required`: give the user the clickable `verification_url` and clearly formatted `user_code`. Ask them to approve it and reply `done`.
- `authentication_pending`: repeat the existing link and code without starting another login.
- `error`: report the specific prerequisite or failure returned by the plugin.

When the user replies that approval is complete, call `gptlink_manage` with `action: auth_complete`. Continue automatically when it returns `ready`.

The plugin prefers existing authentication. `auth_source: hermes` means it reused the active Hermes OpenAI-Codex session read-only. `auth_source: codex_cli` means it reused the Codex CLI session. Never ask for another login when either source is ready.

## Generate

Call `gptlink_generate` with the complete prompt and requested controls.

Default choices when unspecified:

- `1:1` for icons, products, and general requests.
- `16:9` for landscapes, banners, and presentation visuals.
- `9:16` for stories, reels, and phone wallpapers.
- `4:3` for editorial images and general photography.
- `quality: auto` unless the user explicitly prioritizes speed, cost, or final quality.
- `format: png` unless JPEG or WebP is requested.

## Reference edits

Pass each accessible absolute local file through `reference_paths`. Support at most 16 references. Describe both what to preserve and what to change in the prompt. Never silently omit a requested reference.

## Deliver

On `state: completed`, return the absolute `image` path so the active Hermes platform delivers it natively. Add `[[as_document]]` when the user asks for original quality or a downloadable file without messaging-platform recompression.

## Management

Use `gptlink_manage` with the matching action:

- `status`: inspect installation, server, authentication source, and gateway key state.
- `restart`: restart an unhealthy local gateway.
- `update`: update the managed GPTLink checkout and dependencies.
- `rotate_key`: revoke and replace the internal gateway key.
- `logs`: retrieve recent service logs for diagnosis.

Never reveal stored gateway credentials, Hermes authentication data, or Codex authentication data.
