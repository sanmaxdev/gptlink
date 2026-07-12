---
name: gptlink-image
description: Generate, edit, or create variations of images through a self-hosted GPTLink OpenAI-compatible image API. Use when Hermes is asked to create an image, use one or more reference images, change aspect ratio or quality, or return an image file through GPTLink.
version: 1.0.0
author: sanmaxdev
license: MIT
metadata:
  hermes:
    tags: [creative, image-generation, openai-compatible, gptlink]
    category: creative
    requires_tools: [terminal]
    config:
      - key: gptlink.base_url
        description: GPTLink API base URL ending in /v1
        default: "http://127.0.0.1:8787/v1"
        prompt: GPTLink API base URL
required_environment_variables:
  - name: GPTLINK_API_KEY
    prompt: GPTLink API key
    help: Create one with the GPTLink dashboard or manage.py create-key
    required_for: image generation and editing
---

# GPTLink Images

Use the bundled client to generate or edit images. Read `GPTLINK_BASE_URL` from the environment; if absent, export the injected `gptlink.base_url` skill setting for the command.

## Generate

```bash
python3 ${HERMES_SKILL_DIR}/scripts/gptlink_image.py \
  "USER'S COMPLETE IMAGE PROMPT" \
  --aspect-ratio 1:1 --quality auto --format png \
  --output /tmp/gptlink-image.png
```

Choose the aspect ratio from the request. Default to `1:1`; use `16:9` for landscapes and `9:16` for vertical social images.

## Edit with references

Add each local reference with a separate `--reference` argument:

```bash
python3 ${HERMES_SKILL_DIR}/scripts/gptlink_image.py \
  "Keep the subject and replace the background with a snowy mountain" \
  --reference /absolute/path/source.png \
  --aspect-ratio 4:3 --quality high \
  --output /tmp/gptlink-edit.png
```

Use up to 16 references. Describe what to preserve and what to change.

## Return the result

The client prints one absolute output path. Include that bare path in the final response so Hermes delivers the image to the active chat. Add `[[as_document]]` when the user needs the original file without platform recompression.

## Failures

- On `401`, ask the operator to replace `GPTLINK_API_KEY` with an active key.
- On connection failure, check `GPTLINK_BASE_URL` and the server health endpoint.
- On `502`, report the gateway error; the ChatGPT/Codex session may need reauthentication or may have reached its allocation.
- Never print, log, or place `GPTLINK_API_KEY` in a command literal.

Load [references/api.md](references/api.md) only for direct API calls, streaming, masks, multiple outputs, or advanced parameters.

