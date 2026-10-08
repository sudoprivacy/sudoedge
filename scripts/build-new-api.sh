#!/usr/bin/env bash
# Build the shared production Router source for the appliance architecture.
set -euo pipefail
source_dir="${1:-$HOME/new-api}"
image="${ROUTER_IMAGE:-sudoedge-new-api:local}"
[ -f "$source_dir/go.mod" ] || { echo "new-api source not found: $source_dir" >&2; exit 1; }
grep -q '^module github.com/QuantumNous/new-api$' "$source_dir/go.mod" || {
  echo 'Expected the sudoprivacy/new-api source tree.' >&2; exit 1;
}
revision="${ROUTER_REVISION:-$(git -C "$source_dir" rev-parse HEAD)}"
docker build --label org.opencontainers.image.source=https://github.com/sudoprivacy/new-api \
  --label "org.opencontainers.image.revision=$revision" -t "$image" "$source_dir"
printf '[build] %s (%s)\n' "$image" "$revision"
