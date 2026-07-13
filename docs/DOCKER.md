# Run GPTLink with Docker

Docker keeps the service, generated images, database, and Codex authentication
separate. The supplied Compose configuration publishes GPTLink only on the
host's loopback interface.

## Requirements

- Docker Engine 24 or newer with Docker Compose v2.
- A ChatGPT account that can authenticate through Codex.
- Approximately 1 GB of free disk space for the initial image and dependencies.

## First installation

```bash
git clone https://github.com/sanmaxdev/gptlink.git
cd gptlink
docker compose build
docker compose run --rm gptlink codex login --device-auth
docker compose up -d
docker compose exec gptlink python manage.py create-key My-Agent
```

Open `http://127.0.0.1:8787`. Save the generated `gptlink_...` key when it is
shown; only its hash is retained afterward.

The device-login command writes the Codex session into the `codex-auth` named
volume. GPTLink data and generated images are retained in `gptlink-data`.

## Reuse an existing Codex login

The safest portable procedure is to perform device login in the container. To
copy an existing current-user Codex session into the private named volume
instead, run from the GPTLink directory:

```bash
docker compose run --rm --user root --cap-add CHOWN --cap-add DAC_OVERRIDE \
  -v "$HOME/.codex:/source-codex:ro" \
  gptlink sh -c \
  'cp -a /source-codex/. /home/gptlink/.codex/ && chown -R gptlink:gptlink /home/gptlink/.codex'
```

Do not expose, print, or copy individual token values.

## Verify and operate

```bash
docker compose ps
curl -fsS http://127.0.0.1:8787/health
docker compose logs --tail=100 gptlink
docker compose exec gptlink codex login status
```

Common operations:

```bash
docker compose exec gptlink python manage.py list-keys
docker compose exec gptlink python manage.py create-key Claude-Code
docker compose exec gptlink python manage.py revoke-key KEY_ID
docker compose restart gptlink
```

## Update

```bash
git pull --ff-only
docker compose build --pull
docker compose up -d
```

Named volumes are not removed by these commands. Never use `docker compose down
-v` unless you intentionally want to erase the GPTLink database, generated
images, and container Codex session.

## Hosted HTTPS deployment

Leave the Compose port bound to `127.0.0.1`. Put Caddy, Nginx, or another HTTPS
reverse proxy on the host and expose only `/v1/*`, `/files/*`, `/health`, and
`/mcp/*`. Do not expose `/`, `/api/*`, or port `8787` directly.

Set the public origin before starting:

```bash
export GPTLINK_PUBLIC_BASE_URL=https://images.example.com
docker compose up -d
```

The hardened route policy in `deploy/Caddyfile` can be used with the host's
Caddy installation. See [VPS.md](VPS.md) for DNS, firewall, TLS, and SSH tunnel
instructions.

## Mount additional reference files

Container MCP access is limited to `/data/images` by default. Add a narrow
read-only bind mount and include it in `GPTLINK_MCP_ALLOWED_ROOTS` through a
Compose override:

```yaml
services:
  gptlink:
    environment:
      GPTLINK_MCP_ALLOWED_ROOTS: /data/images:/references
    volumes:
      - /srv/gptlink-references:/references:ro
```

Avoid mounting the Docker socket, the host root filesystem, or unrelated home
directories.
