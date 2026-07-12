# Use GPTLink with Hermes Agent

Hermes can use GPTLink as an image capability without changing its primary chat model. The included `gptlink-image` skill calls GPTLink with a secret API key, downloads the result to Hermes, and returns an absolute path so the active chat platform can deliver the image.

## Install the skill

Install directly from the GPTLink repository:

```bash
hermes skills install sanmaxdev/gptlink/skills/gptlink-image
```

For a local checkout:

```bash
mkdir -p ~/.hermes/skills
cp -r skills/gptlink-image ~/.hermes/skills/
```

## Configure it

Store the API key as a Hermes secret and the base URL as non-secret skill configuration:

```bash
hermes config set GPTLINK_API_KEY 'gptlink_your_key'
hermes config set skills.config.gptlink.base_url 'https://images.example.com/v1'
hermes config migrate
```

Restart the Hermes gateway after changing configuration. Do not put the API key in `SKILL.md`, prompts, chat messages, source control, or shell history shared with other users.

## Use it

```text
/gptlink-image Create a clean 16:9 editorial illustration of a solar-powered coastal city.
```

With a reference already present on the Hermes machine:

```text
/gptlink-image Edit /home/hermes/inbox/product.png. Preserve the product exactly, replace the background with a warm studio set, and return a 4:3 PNG.
```

Hermes runs the bundled standard-library Python client. Generated files are written locally and can be sent through Telegram, Discord, Slack, or the CLI. Ask for the image "as a document" when original resolution must be preserved.

## Direct API use

```bash
curl -sS "$GPTLINK_BASE_URL/images/generations" \
  -H "Authorization: Bearer $GPTLINK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "A minimal isometric robot workshop",
    "aspect_ratio": "16:9",
    "quality": "high",
    "output_format": "png",
    "response_format": "url"
  }'
```

Reference edit:

```bash
curl -sS "$GPTLINK_BASE_URL/images/edits" \
  -H "Authorization: Bearer $GPTLINK_API_KEY" \
  -F 'prompt=Preserve the subject and change the background to a forest' \
  -F 'aspect_ratio=4:3' \
  -F 'quality=high' \
  -F 'response_format=url' \
  -F 'image=@reference.png'
```

## Verify

```bash
curl -fsS "${GPTLINK_BASE_URL%/v1}/health"
curl -fsS "$GPTLINK_BASE_URL/models" -H "Authorization: Bearer $GPTLINK_API_KEY"
hermes chat --toolsets skills -q "/gptlink-image Create a small square test icon of a blue bridge"
```

If Hermes reports `401`, rotate the GPTLink key. If GPTLink reports `502`, inspect its service log and confirm the Codex account is still authenticated and has available allocation.
