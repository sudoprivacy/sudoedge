#!/usr/bin/env bash
# Attach model provisioning to the deployed Nexus service's start transaction.
set -euo pipefail
unit="${1:?usage: install-model-mount.sh <nexus-user-unit> <config.json> <bundle.mjs>}"
config="$(realpath "${2:?provide the model mount config}")"
bundle="$(realpath "${3:?provide the bundled mount-model.mjs}")"
[[ "$unit" =~ ^[a-zA-Z0-9_-]+\.service$ ]] || { echo 'Expected a user service name.' >&2; exit 2; }
node="${SUDOEDGE_NODE_BINARY:-$(command -v node)}"
[ -x "$node" ] || { echo 'Provide an executable SUDOEDGE_NODE_BINARY.' >&2; exit 1; }
systemctl --user cat "$unit" >/dev/null
install -d -m700 "$HOME/.config/sudoedge" "$HOME/.local/lib/sudoedge"
target="$HOME/.config/sudoedge/model-mount.json"
[ "$config" = "$target" ] || install -m600 "$config" "$target"
install -m600 "$bundle" "$HOME/.local/lib/sudoedge/mount-model.mjs"
printf '%s\n' "$node" > "$HOME/.local/lib/sudoedge/node-path"
dropin="$HOME/.config/systemd/user/$unit.d"
install -d -m700 "$dropin"
cat > "$dropin/model-mount.conf" <<UNIT
[Service]
Environment="SUDOEDGE_MODEL_MOUNT_CONFIG=$target"
ExecStartPost=$node "$HOME/.local/lib/sudoedge/mount-model.mjs"
TimeoutStartSec=180
UNIT
systemctl --user daemon-reload
printf 'Installed model recovery for %s. It runs on the next service start.\n' "$unit"
