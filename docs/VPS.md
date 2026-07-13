# Self-host GPTLink on an Ubuntu VPS

This guide uses Ubuntu 22.04 or 24.04, systemd, and Caddy. Use a VPS you control with at least 1 GB RAM, a domain name, and outbound HTTPS access. GPTLink performs image generation remotely, so no GPU is required.

## Architecture

```text
Hermes -> HTTPS + GPTLink API key -> Caddy -> 127.0.0.1:8787 -> Codex session
                                                   |
                                            SQLite + images
```

Caddy exposes only `/v1/*`, authenticated `/mcp`, `/files/*`, and `/health`. Management endpoints and the dashboard remain private.

## 1. Prepare DNS and firewall

Create an `A` record such as `images.example.com` pointing to the VPS. Allow SSH, HTTP, and HTTPS:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Do not open port `8787`.

## 2. Clone and install

```bash
git clone https://github.com/sanmaxdev/gptlink.git
cd gptlink
sudo bash scripts/install-vps.sh
```

The installer creates a locked-down `gptlink` system user, installs Python and the Codex CLI, creates `/opt/gptlink/.venv`, stores state in `/var/lib/gptlink`, and installs the systemd unit. Review `/etc/gptlink.env` if you need different paths or a different local port. For a public MCP endpoint, set its real origin before starting:

```bash
sudo sed -i 's#GPTLINK_PUBLIC_BASE_URL=.*#GPTLINK_PUBLIC_BASE_URL=https://YOUR_REAL_DOMAIN#' /etc/gptlink.env
```

## 3. Authenticate the Codex account

Run device authentication as the same Linux user that runs the service:

```bash
sudo -u gptlink -H codex login --device-auth
sudo -u gptlink -H codex login status
```

Open the displayed URL on your own browser, enter the device code, and approve the account. Never copy `/home/gptlink/.codex/auth.json` to another host or commit it to Git.

## 4. Start and test locally

```bash
sudo systemctl start gptlink
sudo systemctl status gptlink --no-pager
curl -fsS http://127.0.0.1:8787/health
```

Create a separate key for Hermes. The secret is printed once:

```bash
sudo -u gptlink -H /opt/gptlink/.venv/bin/python /opt/gptlink/manage.py create-key Hermes
```

Store it in a password manager. List or revoke keys with:

```bash
sudo -u gptlink -H /opt/gptlink/.venv/bin/python /opt/gptlink/manage.py list-keys
sudo -u gptlink -H /opt/gptlink/.venv/bin/python /opt/gptlink/manage.py revoke-key KEY_ID
```

## 5. Add HTTPS with Caddy

Install Caddy from its official Debian repository:

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
sudo apt update
sudo apt install -y caddy
```

Copy the supplied configuration and replace the example domain:

```bash
sudo cp /opt/gptlink/deploy/Caddyfile /etc/caddy/Caddyfile
sudo sed -i 's/images\.example\.com/YOUR_REAL_DOMAIN/g' /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Caddy obtains and renews the TLS certificate automatically after DNS resolves and ports 80/443 are reachable.

## 6. Verify the public API

```bash
export GPTLINK_BASE_URL='https://YOUR_REAL_DOMAIN/v1'
export GPTLINK_API_KEY='gptlink_your_key'

curl -fsS "${GPTLINK_BASE_URL%/v1}/health"
curl -fsS "$GPTLINK_BASE_URL/models" \
  -H "Authorization: Bearer $GPTLINK_API_KEY"
```

Generate a small test:

```bash
curl -sS "$GPTLINK_BASE_URL/images/generations" \
  -H "Authorization: Bearer $GPTLINK_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"A minimal blue bridge app icon","aspect_ratio":"1:1","quality":"low","response_format":"url"}'
```

## 7. Open the private dashboard

From your computer, create an SSH tunnel:

```bash
ssh -L 8787:127.0.0.1:8787 your-user@YOUR_VPS_IP
```

Open `http://127.0.0.1:8787` locally. Do not add `/api/*` or `/` to the public Caddy routes.

## 8. Connect Hermes

Follow [HERMES.md](HERMES.md). When Hermes runs on the same VPS, prefer the
explicitly enabled plugin in that guide: install it with
`hermes plugins install sanmaxdev/gptlink --enable`. The plugin keeps GPTLink
on localhost, reuses existing authentication when available, initiates device
login only when needed, and manages its internal API key. It does not require
the public Caddy deployment described above.

## 9. Connect Claude Code, Antigravity, Codex, and MCP clients

Use [AGENTS.md](AGENTS.md) for the universal installer, local/remote selection,
per-agent keys, reference-image behavior, manual configurations, and tool examples.

For a remote agent, create a dedicated key and configure
`https://YOUR_REAL_DOMAIN/mcp/`. Never reuse the Codex OAuth credential as a
client key.

## Operations

### Enable signed webhooks

Jobs are enabled automatically. Webhook callbacks require a server-side HMAC
secret. Add one without printing it into shell history:

```bash
secret="$(openssl rand -hex 32)"
sudo sh -c 'umask 077; printf "\nGPTLINK_WEBHOOK_SECRET=%s\nGPTLINK_WEBHOOK_ALLOWED_HOSTS=hooks.example.com\n" "$1" >> /etc/gptlink.env' sh "$secret"
unset secret
sudo systemctl restart gptlink
```

Replace `hooks.example.com` with the exact callback host. GPTLink permits only
public HTTPS destinations by default. Follow [JOBS.md](JOBS.md) for API and MCP
examples, HMAC verification, retries, and private-network policy.

Logs:

```bash
sudo journalctl -u gptlink -f
sudo journalctl -u caddy -f
```

Update:

```bash
cd ~/gptlink
git pull --ff-only
sudo bash scripts/install-vps.sh
sudo systemctl restart gptlink
```

Backup `/var/lib/gptlink` if image history matters. The Codex credential store is not part of that backup; reauthenticate on replacement hosts.

## Troubleshooting

- `401` from GPTLink: the client key is invalid or revoked.
- `502` with authentication text: rerun `sudo -u gptlink -H codex login --device-auth` and restart GPTLink.
- `502` with rate-limit or allocation text: wait for the subscription allocation to reset.
- Caddy certificate failure: verify DNS and inbound ports 80/443.
- Wrong `http://` URLs in output: confirm Caddy is the only proxy and systemd includes `--proxy-headers --forwarded-allow-ips=127.0.0.1`.
- MCP returns `421`: set `GPTLINK_PUBLIC_BASE_URL` to the exact public HTTPS origin and restart the service.
- Service cannot write: check ownership of `/var/lib/gptlink` and `/home/gptlink/.codex`.

## Security checklist

- Keep port 8787 private.
- Expose only the routes in `deploy/Caddyfile`.
- Use one API key per agent and rotate it if disclosed.
- Protect `/home/gptlink/.codex`, `/etc/gptlink.env`, and `/var/lib/gptlink` with root/service-user permissions.
- Patch the VPS regularly and review logs for unexpected use.
- Do not offer this gateway as a public multi-user service.
