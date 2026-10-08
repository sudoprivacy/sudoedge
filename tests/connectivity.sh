#!/usr/bin/env bash
# Runs the actual firewall in an isolated network namespace. No host rules change.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
if [ "${1:-}" != inside ]; then
  exec unshare --net bash "$0" inside
fi
export SUDOEDGE_STATE_DIR
SUDOEDGE_STATE_DIR="$(mktemp -d)"
server=''
trap 'if [ -n "$server" ]; then kill "$server" 2>/dev/null || true; fi; rm -rf "$SUDOEDGE_STATE_DIR"' EXIT
ip link set lo up
ip address add 198.18.0.1/32 dev lo
ip address add 192.168.88.1/32 dev lo
ip -6 address add 2001:db8::1/128 dev lo
ip -6 address add fd00::1/128 dev lo
nft add table inet unrelated_policy
python3 -m http.server 18080 --bind :: --directory "$SUDOEDGE_STATE_DIR" >/dev/null 2>&1 &
server=$!
probe() { curl --noproxy '*' --fail --silent --max-time 2 "http://$1:18080/" >/dev/null; }
for _ in $(seq 1 20); do probe 192.168.88.1 && break; sleep .1; done
test "$(bash "$here/scripts/sudoedge.sh" connectivity status)" = online
probe 198.18.0.1
probe '[2001:db8::1]'
for _ in 1 2; do
  bash "$here/scripts/sudoedge.sh" connectivity local
  probe 192.168.88.1
  probe '[fd00::1]'
  if probe 198.18.0.1 || probe '[2001:db8::1]'; then echo 'WAN escaped local mode' >&2; exit 1; fi
done
nft delete table inet sudoedge_egress
bash "$here/scripts/sudoedge.sh" connectivity restore
if probe 198.18.0.1; then echo 'restore failed' >&2; exit 1; fi
if bash "$here/scripts/sudoedge.sh" connectivity typo; then exit 1; fi
test "$(bash "$here/scripts/sudoedge.sh" connectivity status)" = local
bash "$here/scripts/sudoedge.sh" connectivity online
probe 198.18.0.1
probe '[2001:db8::1]'
nft list table inet unrelated_policy >/dev/null
echo 'PASS: default online, IPv4/IPv6 local mode, LAN access, idempotence, restore, unrelated rules'
