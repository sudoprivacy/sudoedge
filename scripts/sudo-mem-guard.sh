#!/usr/bin/env bash
# sudo-mem-guard — keeps a unified-memory box recoverable and turns an
# over-allocation into a cheap clean kill.
#   (1) Caps each vLLM container cgroup memory.max at (RAM-RESERVE), re-applied
#       to the ephemeral /system.slice/docker-*.scope names.
#   (2) Reclaims the largest vLLM process when system MemAvailable stays below
#       FLOOR for SUSTAIN rounds (covers GPU/unified allocations that are charged
#       outside per-cgroup accounting).
# Generous by design: the cap is far above any single sane model, and the
# tripwire acts only at genuine near-OOM.
set -o pipefail
RESERVE_GB=${RESERVE_GB:-14}
FLOOR_GB=${FLOOR_GB:-6}
SUSTAIN=${SUSTAIN:-5}          # x3s ≈ 15s sustained before the tripwire acts
CG=/sys/fs/cgroup
LOG=/var/log/sudo-mem-guard.log
memtotal_kb=$(awk '/MemTotal/{print $2}' /proc/meminfo)
cap=$(( memtotal_kb*1024 - RESERVE_GB*1024*1024*1024 ))
low=0
log(){ echo "[up $(cut -d' ' -f1 /proc/uptime)] $*" >>"$LOG"; }
log "started: cap=$((cap/1024/1024/1024))G floor=${FLOOR_GB}G reserve=${RESERVE_GB}G"
while :; do
  for pid in $(pgrep -f "bin/vllm serve" 2>/dev/null); do
    scope=$(awk -F: '{print $3}' "/proc/$pid/cgroup" 2>/dev/null)
    case "$scope" in
      /system.slice/docker-*.scope) : ;;   # only container scopes, never user sessions or system daemons
      *) continue ;;
    esac
    f="$CG$scope/memory.max"
    [ -f "$f" ] || continue
    cur=$(cat "$f" 2>/dev/null)
    if [ "$cur" = "max" ] || { [ -n "$cur" ] && [ "$cur" -gt "$cap" ] 2>/dev/null; }; then
      echo "$cap" >"$f" 2>/dev/null && log "capped $scope -> $((cap/1024/1024/1024))G"
    fi
  done
  avail_kb=$(awk '/MemAvailable/{print $2}' /proc/meminfo)
  if [ "$avail_kb" -lt $((FLOOR_GB*1024*1024)) ]; then
    low=$((low+1))
    if [ "$low" -ge "$SUSTAIN" ]; then
      big=$(ps -eo pid,rss,comm --sort=-rss 2>/dev/null | awk 'tolower($3)~/vllm/{print $1; exit}')
      [ -n "$big" ] && { log "TRIP avail<${FLOOR_GB}G x${SUSTAIN} -> kill vllm pid=$big"; kill -9 "$big" 2>/dev/null; }
      low=0
    fi
  else
    low=0
  fi
  sleep 3
done
