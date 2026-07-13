---
name: gptlink-images
description: Generate, edit, combine, and vary images through GPTLink MCP. Use for text-to-image work, visual assets, UI mockups, reference edits, masks, exact dimensions, aspect ratios, multiple outputs, image history, or GPTLink readiness diagnosis.
---

# GPTLink Images

Use `gptlink_generate` for text-only creation, `gptlink_edit` for one to sixteen
references or a mask, and `gptlink_variation` for source-preserving alternatives.
Use either aspect ratio or exact size. Default to automatic quality and PNG.
Describe edit invariants explicitly, never omit a requested reference, and
return/show the saved path as a visual artifact. Use `gptlink_status` after
failures and `gptlink_history` to recover recent outputs. Never expose credentials.
