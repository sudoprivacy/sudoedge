#!/usr/bin/env bash
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo bash $0" >&2; exit 1; }
here="$(cd "$(dirname "$0")" && pwd)"
command -v nft >/dev/null || { echo 'Install nftables first.' >&2; exit 1; }
install -m755 "$here/sudoedge.sh" /usr/local/bin/sudoedge
cat > /etc/systemd/system/sudoedge.service <<'UNIT'
[Unit]
Description=Restore SudoEdge connectivity policy before networking
DefaultDependencies=no
After=local-fs.target
Before=network-pre.target docker.service
Wants=network-pre.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/sudoedge connectivity restore
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now sudoedge.service
