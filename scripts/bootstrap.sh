#!/usr/bin/env bash
# Host layer for an edge GPU box: memory guardrails + the router's TEE key.
# Run once per box (idempotent). Requires sudo.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/.." && pwd)"

echo "[bootstrap] cgroup memory reservations (persist across reboot)"
sudo systemctl set-property system.slice MemoryMin=12G
sudo systemctl set-property ssh.service MemoryMin=512M

echo "[bootstrap] install sudo-mem-guard"
sudo install -m755 "$here/sudo-mem-guard.sh" /usr/local/bin/sudo-mem-guard.sh
sudo tee /etc/systemd/system/sudo-mem-guard.service >/dev/null <<'UNIT'
[Unit]
Description=Sudo unified-memory guard (hard cgroup cap + OOM circuit breaker)
After=docker.service
[Service]
Type=simple
ExecStart=/usr/local/bin/sudo-mem-guard.sh
Restart=always
RestartSec=2
OOMScoreAdjust=-900
MemoryMin=64M
Nice=-5
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now sudo-mem-guard.service

echo "[bootstrap] throwaway TEE key for the router (kept out of git)"
if [ ! -f "$repo/compose/.env" ]; then
  key="$(openssl ecparam -name prime256v1 -genkey -noout -outform DER | base64 -w0)"
  umask 077
  printf 'TEE_KEY=%s\n' "$key" > "$repo/compose/.env"
fi

echo "[bootstrap] done — next: docker compose -f compose/docker-compose.yml up -d"
