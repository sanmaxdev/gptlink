#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root: sudo bash scripts/install-vps.sh" >&2
  exit 1
fi

install -d -m 0755 /opt/gptlink
rsync -a --delete --exclude .git --exclude .venv --exclude data ./ /opt/gptlink/

if ! id gptlink >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /home/gptlink --shell /bin/bash gptlink
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip rsync ca-certificates curl gnupg

if ! command -v node >/dev/null 2>&1 || [[ $(node -p 'Number(process.versions.node.split(".")[0])') -lt 20 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

npm install --global @openai/codex
python3 -m venv /opt/gptlink/.venv
/opt/gptlink/.venv/bin/pip install --upgrade pip
/opt/gptlink/.venv/bin/pip install -r /opt/gptlink/requirements.txt

install -d -o gptlink -g gptlink -m 0700 /var/lib/gptlink /home/gptlink/.codex
chown -R gptlink:gptlink /opt/gptlink /home/gptlink

if [[ ! -f /etc/gptlink.env ]]; then
  install -m 0600 /opt/gptlink/.env.example /etc/gptlink.env
fi

install -m 0644 /opt/gptlink/deploy/gptlink.service /etc/systemd/system/gptlink.service
systemctl daemon-reload
systemctl enable gptlink

echo
echo "Installed. Authenticate next:"
echo "  sudo -u gptlink -H codex login --device-auth"
echo "Then run:"
echo "  sudo systemctl start gptlink"
echo "  sudo -u gptlink -H /opt/gptlink/.venv/bin/python /opt/gptlink/manage.py create-key Hermes"

