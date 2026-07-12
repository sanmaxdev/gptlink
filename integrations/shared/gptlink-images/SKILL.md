---
name: gptlink-images
description: Generate, edit, combine, and create variations of images through the GPTLink MCP tools. Use for text-to-image work, visual assets, UI mockups, reference-image edits, masks, aspect ratios, exact dimensions, multiple outputs, image history, or diagnosing GPTLink readiness.
---

# GPTLink Images

Use the GPTLink MCP tools directly. Do not use terminal HTTP commands when the tools are available.

## Workflow

1. Call `gptlink_status` only when readiness is unknown or a generation call fails.
2. Call `gptlink_generate` for text-only creation.
3. Call `gptlink_edit` when one or more reference images must influence the result.
4. Call `gptlink_variation` when the user wants alternatives that preserve the source identity.
5. Return the generated file path and show the image when the client supports local-image rendering.

## Controls

- Use either `aspect_ratio` or `size`, never both.
- Default to `quality: auto` and `output_format: png`.
- Use `16:9` for banners and landscapes, `9:16` for phone/social verticals, `1:1` for icons and products, and `4:3` for general editorial visuals.
- Use `output_directory` when the image belongs in the active project. It must be under a path allowed by the GPTLink installation.
- Use up to 16 reference images. Pass absolute local paths when GPTLink runs on the same machine; use HTTP(S) or data URLs for a remote server.
- Describe what to preserve and what to change in every edit prompt.

## Errors

- If authentication is missing, tell the user to complete the GPTLink/Codex device login; never request or reveal OAuth tokens.
- If a local path is rejected, use a path under an allowed root or ask the GPTLink operator to add it through `GPTLINK_MCP_ALLOWED_ROOTS`.
- If a remote agent cannot access a local reference, upload it to an accessible URL or use local stdio mode.
