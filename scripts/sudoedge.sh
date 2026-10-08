#!/usr/bin/env bash
# Operator entry point for the appliance.
set -euo pipefail
connectivity() (
  state_dir="${SUDOEDGE_STATE_DIR:-/etc/sudoedge}"
  state_file="$state_dir/connectivity-mode"
  mode="${1:-status}"
  read_mode() {
    if [ -f "$state_file" ]; then cat "$state_file"; else printf 'online\n'; fi
  }
  if [ "$mode" = status ]; then read_mode; exit 0; fi
  case "$mode" in
    online|local|restore) ;;
    *) echo 'usage: sudoedge connectivity {online|local|status|restore}' >&2; exit 2 ;;
  esac
  [ "$(id -u)" -eq 0 ] || { echo 'Connectivity changes require root.' >&2; exit 1; }
  command -v nft >/dev/null
  install -d -m755 "$state_dir"
  exec 9>"$state_dir/connectivity.lock"
  flock 9
  [ "$mode" != restore ] || mode="$(read_mode)"
  case "$mode" in online|local) ;; *) echo 'Invalid persisted connectivity mode.' >&2; exit 2 ;; esac
  rules="$(mktemp "$state_dir/.connectivity-rules.XXXXXXXX")"
  trap 'rm -f "$rules"' EXIT
  if nft list table inet sudoedge_egress >/dev/null 2>&1; then
    printf 'delete table inet sudoedge_egress\n' >> "$rules"
  fi
  if [ "$mode" = local ]; then
    cat >> "$rules" <<'NFT'
table inet sudoedge_egress {
  set lan4 { type ipv4_addr; flags interval; elements = { 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 224.0.0.0/24, 255.255.255.255 } }
  set lan6 { type ipv6_addr; flags interval; elements = { ::1, fc00::/7, fe80::/10, ff02::/16 } }
  chain local_destinations {
    ip daddr @lan4 return
    ip6 daddr @lan6 return
    counter reject with icmpx type admin-prohibited
  }
  chain output { type filter hook output priority -10; policy accept; jump local_destinations; }
  chain forward { type filter hook forward priority -10; policy accept; jump local_destinations; }
}
NFT
  fi
  nft --check --file "$rules"
  save_mode() {
    printf '%s\n' "$mode" > "$state_file.next"
    chmod 644 "$state_file.next"
    mv -f "$state_file.next" "$state_file"
  }
  # Persist local intent before enforcement; persist online after removal.
  [ "$mode" != local ] || save_mode
  nft --file "$rules"
  [ "$mode" != online ] || save_mode
  printf 'sudoedge connectivity: %s\n' "$mode"
)
usage() {
  cat <<'HELP'
Usage: sudoedge status
       sudoedge connectivity [status|online|local|restore]
       sudoedge webui status
       sudoedge model restore

Connectivity changes require sudo. Status commands are read-only.
On Windows, run scripts/open-webui.ps1 to install the reconnecting SSH tunnel.
HELP
}
probe() {
  local name="$1" url="$2"
  if curl --noproxy '*' --fail --silent --output /dev/null --max-time 3 "$url"; then
    printf '%s: reachable (%s)\n' "$name" "$url"
  else
    printf '%s: unavailable (%s)\n' "$name" "$url"
    return 1
  fi
}
webui_status() {
  probe WebUI "${SUDOEDGE_WEBUI_URL:-http://127.0.0.1:26808}/health/live"
}
case "${1:-status}" in
  status)
    [ "$#" -le 1 ] || { usage >&2; exit 2; }
    printf 'Connectivity: '
    connectivity status
    is_failed=0
    webui_status || is_failed=1
    probe Moss "${SUDOEDGE_MOSS_URL:-http://127.0.0.1:43127}/healthz" || is_failed=1
    probe Router "${SUDOEDGE_ROUTER_URL:-http://127.0.0.1:3000}/api/status" || is_failed=1
    exit "$is_failed"
    ;;
  connectivity)
    [ "$#" -le 2 ] || { usage >&2; exit 2; }
    connectivity "${2:-status}"
    ;;
  webui)
    [ "$#" -eq 2 ] && [ "$2" = status ] || { usage >&2; exit 2; }
    webui_status
    ;;
  model)
    [ "$#" -eq 2 ] && [ "$2" = restore ] || { usage >&2; exit 2; }
    export SUDOEDGE_MODEL_MOUNT_CONFIG="${SUDOEDGE_MODEL_MOUNT_CONFIG:-$HOME/.config/sudoedge/model-mount.json}"
    node="${SUDOEDGE_NODE_BINARY:-$(cat "$HOME/.local/lib/sudoedge/node-path")}"
    exec "$node" "${SUDOEDGE_MODEL_MOUNT_SCRIPT:-$HOME/.local/lib/sudoedge/mount-model.mjs}"
    ;;
  help|--help|-h) usage ;;
  *) usage >&2; exit 2 ;;
esac
