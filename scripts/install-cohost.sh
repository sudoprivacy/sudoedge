#!/usr/bin/env bash
# Install the local ManagedAgentService runtime used by Moss browser sessions.
# The binary is built and released by sudocode; this script owns only the
# appliance placement, state directories and user service.
set -euo pipefail

binary="${1:?usage: install-cohost.sh <nexusd-cohost-arm64> [unit-name]}"
unit="${2:-sudoedge-cohost}"
bind_addr="${SUDOEDGE_COHOST_BIND_ADDR:-127.0.0.1:22141}"
cluster="${SUDOEDGE_COHOST_CLUSTER:-edge-local}"
root="${SUDOEDGE_COHOST_ROOT:-$HOME/.local/share/sudoedge/cohost}"
config="${SUDOEDGE_COHOST_CONFIG_HOME:-$HOME/.config/sudoedge/cohost}"
install_root="${SUDOEDGE_COHOST_INSTALL_ROOT:-$HOME/.local/lib/sudoedge}"

[ -x "$binary" ] || { echo "cohost binary is not executable: $binary" >&2; exit 1; }
install -d -m700 "$root/data" "$root/id" "$root/model-cache" "$config" "$install_root"
install -m755 "$binary" "$install_root/nexusd-cohost"

systemd_dir="$HOME/.config/systemd/user"
install -d -m700 "$systemd_dir"
cat > "$systemd_dir/$unit.service" <<UNIT
[Unit]
Description=SudoEdge local cohost ManagedAgentService
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$root
Environment=NEXUS_DATA_DIR=$root/data
Environment=NEXUS_IDENTITY_DIR=$root/id
Environment=NEXUS_CLUSTER_INIT=$cluster
Environment=NEXUS_CLUSTER_INIT_MOUNTS=/agents=$cluster
Environment=NEXUS_ADVERTISE_ADDR=$bind_addr
Environment=SUDO_CODE_CONFIG_HOME=$config
Environment=RUST_LOG=info
ExecStart=$install_root/nexusd-cohost --bind-addr $bind_addr
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "$unit.service"
printf 'Installed %s on %s (ManagedAgentService at %s).\n' "$unit.service" "$install_root/nexusd-cohost" "$bind_addr"
