#!/usr/bin/env bash
# Host layer for an edge GPU box: memory guardrails and Router credentials.
# Run once per box, as root:  sudo bash scripts/bootstrap.sh   (idempotent)
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo bash $0"; exit 1; }
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/.." && pwd)"
owner="${SUDO_USER:-root}"

echo "[bootstrap] base-host prerequisites (a DGX ships these; installs on a bare box)"
if ! command -v docker >/dev/null; then
  echo "[bootstrap]   installing docker"; curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || echo "[bootstrap]   WARN: docker compose plugin missing"
if ! docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q '"nvidia"'; then
  if command -v nvidia-ctk >/dev/null; then
    echo "[bootstrap]   configuring nvidia container runtime"
    nvidia-ctk runtime configure --runtime=docker && systemctl restart docker
  else
    echo "[bootstrap]   WARN: nvidia-container-toolkit not found (DGX OS ships it) — GPU containers need it"
  fi
fi
nvidia-smi >/dev/null 2>&1 || echo "[bootstrap]   WARN: nvidia-smi not working — check the GPU driver"

echo "[bootstrap] cgroup memory reservations (persist across reboot)"
systemctl set-property system.slice MemoryMin=12G
systemctl set-property ssh.service MemoryMin=512M

echo "[bootstrap] install sudo-mem-guard"
install -m755 "$here/sudo-mem-guard.sh" /usr/local/bin/sudo-mem-guard.sh
tee /etc/systemd/system/sudo-mem-guard.service >/dev/null <<'UNIT'
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
systemctl daemon-reload
systemctl enable --now sudo-mem-guard.service

echo "[bootstrap] local Router administrator credential"
owner_home="$(getent passwd "$owner" | cut -d: -f6)"
admin_file="$owner_home/sudo-dgx/router-admin-pw.txt"
install -d -m700 -o "$owner" -g "$owner" "$owner_home/sudo-dgx"
if [ ! -f "$admin_file" ]; then
  ( umask 077; openssl rand -base64 24 > "$admin_file" )
  chown "$owner":"$owner" "$admin_file"
fi

echo "[bootstrap] boot-reprovision hook (router /data is RAM-backed → re-configure on boot)"
key_file="$(getent passwd "$owner" | cut -d: -f6)/sudo-dgx/gpustack-key.json"
tee /etc/systemd/system/sudoedge-reconfigure.service >/dev/null <<UNIT
[Unit]
Description=SudoEdge restore new-api configuration after boot
After=docker.service
Wants=docker.service
[Service]
Type=oneshot
User=$owner
Environment=GPUSTACK_KEY_FILE=$key_file
Environment=ADMIN_PW_FILE=$admin_file
ExecStart=/usr/bin/env bash $repo/scripts/reconfigure-on-boot.sh $repo
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable sudoedge-reconfigure.service >/dev/null 2>&1 && echo "[bootstrap]   enabled sudoedge-reconfigure.service"

echo "[bootstrap] persistent connectivity mode (online by default)"
command -v nft >/dev/null || { apt-get update && apt-get install -y nftables; }
bash "$here/install-ops.sh"

echo "[bootstrap] done — next: docker compose -f compose/docker-compose.yml up -d"
