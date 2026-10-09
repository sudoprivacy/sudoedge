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
staged_binary="$(mktemp "$install_root/nexusd-cohost.XXXXXX")"
trap 'rm -f "$staged_binary"' EXIT
install -m755 "$binary" "$staged_binary"
mv -f "$staged_binary" "$install_root/nexusd-cohost"

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
expected_hash="$(sha256sum "$install_root/nexusd-cohost")"
actual_hash=""
# Type=simple can report its main PID before exec has replaced the child.
for _attempt in {1..20}; do
  pid="$(systemctl --user show "$unit.service" --property=MainPID --value)"
  if [[ "$pid" =~ ^[1-9][0-9]*$ ]] && [ -r "/proc/$pid/exe" ]; then
    actual_hash="$(sha256sum "/proc/$pid/exe" 2>/dev/null)" || actual_hash=""
    [ "${expected_hash%% *}" = "${actual_hash%% *}" ] && break
  fi
  sleep 0.1
done
if [[ ! "$pid" =~ ^[1-9][0-9]*$ ]] || [ ! -r "/proc/$pid/exe" ]; then
  echo "cohost installation has no running main process: $unit.service" >&2
  exit 1
fi
if [ "${expected_hash%% *}" != "${actual_hash%% *}" ]; then
  echo "cohost installation did not activate the requested binary: $unit.service" >&2
  echo "Inspect systemctl --user cat $unit.service for ExecStart overrides; restart after managed sessions are idle." >&2
  exit 1
fi
printf 'Installed %s on %s (ManagedAgentService at %s).\n' "$unit.service" "$install_root/nexusd-cohost" "$bind_addr"
