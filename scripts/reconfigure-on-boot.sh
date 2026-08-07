#!/usr/bin/env bash
# Re-apply the router config after a reboot. nova-gateway's /data is RAM-backed,
# so its channels + relay token are gone when the container restarts empty —
# this restores them. Installed as the sudoedge-reconfigure.service unit by
# bootstrap.sh and run as the deployer.
#
# Restores the LOCAL config (gpustack channel + relay token + sudocode wiring).
# The cloud channel's key is not persisted (by design), so it is NOT restored
# here — re-inject it deliberately (SUDOROUTER_KEY) when needed.
set -euo pipefail
repo="${1:?usage: reconfigure-on-boot.sh <repo>}"
: "${GPUSTACK_KEY_FILE:?set GPUSTACK_KEY_FILE}"
GPUSTACK_KEY="$(python3 -c "import json,os;print(json.load(open(os.environ['GPUSTACK_KEY_FILE']))['value'])")"
export GPUSTACK_KEY
# configure.sh waits for nova-gateway itself, so no extra wait needed here.
exec bash "$repo/scripts/configure.sh"
