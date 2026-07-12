# GPTLink API reference

Set `GPTLINK_BASE_URL` to the public URL ending in `/v1` and send `Authorization: Bearer $GPTLINK_API_KEY`.

## Endpoints

- `POST /images/generations`: JSON image generation.
- `POST /images/edits`: multipart edit with repeated `image` fields and optional PNG `mask`.
- `POST /images/variations`: multipart reference-based variation.
- `POST /responses`: focused Responses API bridge using an `image_generation` tool.
- `GET /models`: model aliases.

## Generation JSON

```json
{
  "model": "gpt-image-2",
  "prompt": "A paper-cut illustration of a forest at dawn",
  "aspect_ratio": "16:9",
  "quality": "high",
  "n": 1,
  "output_format": "png",
  "response_format": "url"
}
```

Use either `aspect_ratio` or `size`, not both. `size` accepts `auto` or `WIDTHxHEIGHT` subject to GPTLink limits. Other controls: `quality` (`auto`, `low`, `medium`, `high`), `n` (1-10), `output_format` (`png`, `jpeg`, `webp`), `output_compression` (JPEG/WebP only), `background` (`auto`, `opaque`), `moderation` (`auto`, `low`), `stream`, and `partial_images` (0-3).

For URL responses, download the returned `data[0].url` to a local file before replying. For base64 responses, decode `data[0].b64_json`.

