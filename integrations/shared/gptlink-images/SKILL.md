---
name: gptlink-images
description: Generate, edit, combine, and vary images through GPTLink MCP. Use for text-to-image work, visual assets, UI mockups, reference edits, masks, exact dimensions, aspect ratios, multiple outputs, image history, or GPTLink readiness diagnosis.
---

# GPTLink Images

Use GPTLink MCP tools directly. Do not recreate HTTP calls or request credentials
when the tools are available.

## Choose the tool

1. Use `gptlink_generate` for text-only creation.
2. Use `gptlink_edit` for one to sixteen references or a mask.
3. Use `gptlink_variation` for alternatives that preserve source identity.
4. Use `gptlink_models` only when capability discovery matters.
5. Use `gptlink_status` when readiness is unknown or a call fails.
6. Use `gptlink_history` to recover recent output paths without regenerating.

## Set controls

- Use either `aspect_ratio` or `size`, never both.
- Default to `quality: auto` and `output_format: png`.
- Choose `1:1` for icons/products, `16:9` for banners/landscapes, `9:16`
  for vertical social assets, and `4:3` for editorial visuals.
- Use `output_directory` for project-bound assets.
- Use absolute local references in local mode. Use HTTP(S) or data URLs when
  the MCP server is remote.
- Describe what to preserve and what to change in every edit prompt.
- Never silently omit a requested reference.

## Deliver the result

Return the saved path and render the image when the client supports it. Prefer
paths/URLs over base64. If the user asks for several distinct assets, make a
separate call per distinct prompt; use `n` only for variants of one prompt.

## Recover safely

- If authentication is missing, direct the user to complete GPTLink/Codex device
  login. Never request or reveal OAuth tokens, cookies, or credential files.
- If a path is rejected, use an allowed root or ask the operator to add a narrow
  root through `GPTLINK_MCP_ALLOWED_ROOTS`.
- If a remote server cannot access a client-local reference, use an accessible
  URL or local stdio mode.
- If an allocation limit is returned, report it and wait for reset rather than
  retrying repeatedly.
