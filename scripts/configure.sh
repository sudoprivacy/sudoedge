#!/usr/bin/env bash
# Provision the local new-api Router and update its appliance clients.
set -euo pipefail
umask 077
if [ -z "${ADMIN_PW:-}" ]; then
  ADMIN_PW="$(cat "${ADMIN_PW_FILE:-$HOME/sudo-dgx/router-admin-pw.txt}")"
  export ADMIN_PW
fi
exec python3 "$(dirname "$0")/configure-router.py"
