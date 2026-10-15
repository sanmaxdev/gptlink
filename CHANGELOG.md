# Changelog

## 0.6.1

- Fix image generation failing with "model is not supported when using Codex with
  a ChatGPT account" after the pinned `gpt-5.5` chat model was retired.
- Resolve the Codex chat model at runtime: `GPTLINK_CODEX_MODEL`, then the Codex
  CLI `config.toml` model (active profile first), then the built-in default.
- Fall back to the next candidate when Codex rejects a chat model, and remember
  the model that worked. Other request errors are never retried.
- Report the chat model candidates in status, and the chat model actually used in
  `/v1/responses` results.

## 0.6.0

- Add persistent asynchronous image jobs shared by HTTP, MCP, and dashboard.
- Add restart recovery, transactional claims, polling, listing, and queued cancellation.
- Add signed webhook completion/failure events with persistent exponential retries.
- Add secure callback destination validation and operator-controlled private-network opt-in.
- Add background controls and live job visibility to the minimal light dashboard.
- Add OpenAI-style `Prefer: respond-async` support for Images endpoints.
- Add job/webhook deployment, agent, Docker, and VPS documentation.
