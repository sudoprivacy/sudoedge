#!/usr/bin/env bash
# Appliance placement parameters only. Execution belongs to pinned sudostack.
set -euo pipefail

binary="${1:?usage: install-cohost.sh <verified-nexusd-cohost> [unit-name]}"
unit="${2:-sudoedge-cohost}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${SUDOEDGE_DEPLOY_PYTHON:-python3}" "$script_dir/stack-action.py" \
  "${SUDOEDGE_DEPLOY_COMMAND:-install}" \
  --binary "$binary" \
  --sha256 "${SUDOEDGE_COHOST_SHA256:?Set the authenticated producer binary SHA256}" \
  --source "${SUDOEDGE_COHOST_SOURCE:?Set the full producer source commit}" \
  --unit "$unit" \
  --bind "${SUDOEDGE_COHOST_BIND_ADDR:-127.0.0.1:22141}" \
  --zone "${SUDOEDGE_COHOST_CLUSTER:-edge-local}" \
  --root "${SUDOEDGE_COHOST_ROOT:-$HOME/.local/share/sudoedge/cohost}" \
  --config "${SUDOEDGE_COHOST_CONFIG_HOME:-$HOME/.config/sudoedge/cohost}" \
  --install-root "${SUDOEDGE_COHOST_INSTALL_ROOT:-$HOME/.local/lib/sudoedge/cohost-versions}"
