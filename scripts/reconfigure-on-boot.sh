#!/usr/bin/env bash
# Re-apply the router config after a reboot. new-api's /data is RAM-backed,
# so its channels + relay token are gone when the container restarts empty —
# this restores them. Installed as the sudoedge-reconfigure.service unit by
# bootstrap.sh and run as the deployer.
#
# Restore local inference first, then the optional cloud route from Moss Vault.
# Client refresh and mount recovery still run if the cloud secret is unavailable.
set -euo pipefail
repo="${1:?usage: reconfigure-on-boot.sh <repo>}"
: "${GPUSTACK_KEY_FILE:?set GPUSTACK_KEY_FILE}"
GPUSTACK_KEY="$(python3 -c "import json,os;print(json.load(open(os.environ['GPUSTACK_KEY_FILE']))['value'])")"
export GPUSTACK_KEY
if [ -n "${ADMIN_PW_FILE:-}" ]; then
  ADMIN_PW="$(cat "$ADMIN_PW_FILE")"
  export ADMIN_PW
fi
# configure.sh waits for new-api itself, so no extra wait needed here.
bash "$repo/scripts/configure.sh"
restore_status=0
python3 "$repo/scripts/restore-cloud-router.py" || restore_status=$?
python3 "$repo/scripts/sync-moss-router.py" || restore_status=$?
if [ -f "${SUDOEDGE_MODEL_MOUNT_CONFIG:-$HOME/.config/sudoedge/model-mount.json}" ]; then
  sudoedge model restore || restore_status=$?
fi
exit "$restore_status"
