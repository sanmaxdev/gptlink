# Compatibility matrix

GPTLink exposes the same image service through MCP, the OpenAI Images API, and
a focused Responses API bridge. This matrix distinguishes automated coverage
from configuration-only support so compatibility claims remain auditable.

## Coding agents

| Client | Local stdio | Remote HTTPS | Skill | Scope | Verification |
|---|---:|---:|---:|---|---|
| Claude Code | Yes | Yes | Yes | User and project | Native plugin validation; installer tests |
| Antigravity | Yes | Yes | Yes | User and project | Native plugin validation; installer tests |
| Codex | Yes | Yes | Yes | User | Installer command tests; manual `codex mcp` smoke |
| OpenCode | Yes | Yes | Yes | User and project | Current `opencode.json` schema shape + installer tests |
| Hermes Agent | Managed plugin | Same-VPS or HTTPS | Bundled | User | Hermes plugin unit tests |
| Generic MCP clients | Yes | Yes | Portable | Client-defined | JSON template tests |

Local MCP uses stdio and returns local paths. Remote MCP uses authenticated
Streamable HTTP at `/mcp/` and returns URLs or server-side paths.

## MCP capabilities

| Capability | Tool | Automated coverage |
|---|---|---:|
| Readiness and authentication | `gptlink_status` | Yes |
| Models and controls | `gptlink_models` | Yes |
| Text-to-image | `gptlink_generate` | Tool contract + provider payload |
| Reference editing and masks | `gptlink_edit` | Tool contract + provider payload |
| Source-preserving alternatives | `gptlink_variation` | Tool contract |
| Recent result recovery | `gptlink_history` | Tool contract + database tests |
| Durable async creation | `gptlink_job_create` | Tool contract + database tests |
| Job polling/list/cancel | `gptlink_job_status`, `gptlink_jobs`, `gptlink_job_cancel` | Tool contract + HTTP tests |
| Local allowed-root enforcement | All file tools | Yes |
| Remote Bearer authentication | `/mcp/` | Token verifier configuration |

## OpenAI-compatible HTTP surface

| Endpoint | Compatibility target | Status |
|---|---|---|
| `GET /v1/models` | OpenAI model listing | Supported |
| `POST /v1/images/generations` | Images generation | ASGI contract tested |
| `POST /v1/images/edits` | Multipart references and mask | ASGI contract tested |
| `POST /v1/images/variations` | Variations | GPTLink emulation using reference editing |
| `POST /v1/responses` | Responses `image_generation` tool | Focused subset |
| `POST /v1/jobs` | GPTLink durable image job | Supported; strict JSON schema |
| `GET /v1/jobs`, `GET /v1/jobs/{id}` | Job listing and polling | Supported |
| `POST /v1/jobs/{id}/cancel` | Cancel queued job | Supported |
| `Prefer: respond-async` | Queue Images generation/edit/variation | Supported |
| Image generation SSE | OpenAI-style event stream | Supported |

The API is intentionally image-focused. It does not claim general text,
embeddings, audio, fine-tuning, assistants, batches, or Files API compatibility.

## Image controls

| Control | Generate | Edit | Variation | MCP |
|---|---:|---:|---:|---:|
| `quality` | Yes | Yes | Automatic | Yes |
| Exact `size` | Yes | Yes | Yes | Yes |
| `aspect_ratio` convenience | Yes | Yes | No | Yes |
| `n` from 1 to 10 | Yes | Yes | Yes | Yes |
| PNG/JPEG/WebP | Yes | Yes | PNG | Yes |
| Compression | JPEG/WebP | JPEG/WebP | No | Yes |
| Up to 16 references | No | Yes | One | Yes |
| Mask | No | Yes | No | Yes |
| Partial previews | Yes | Yes | No | HTTP Responses/Images |
| Hosted URL response | Yes | Yes | Yes | Yes |
| Durable async job | Yes | Yes | Yes | Yes |
| Signed webhook | Yes | Yes | Yes | Yes |

## Verification levels

- **Automated:** exercised by the repository test suite without consuming live
  subscription allocation.
- **Native validation:** checked using the client's own plugin validator where
  the client provides one.
- **Configuration tested:** generated configuration is parsed and its required
  schema shape is asserted.
- **Live upstream:** requires a current Codex login and consumes subscription
  allocation, so it is a release smoke test rather than a normal CI job.

When reporting a client regression, include the GPTLink version, client
version, operating system, local or remote mode, and the sanitized error body.
Never attach OAuth credential files or gateway secrets.
