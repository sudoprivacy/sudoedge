#!/usr/bin/env bash
# Deploy gpustack (local GPU inference) as its native single-node pair:
#   * server  — management API + OpenAI gateway on :80 (bridge net)
#   * worker  — privileged, host-network; actually drives the GPU and spawns the
#               vLLM runner containers. It joins the server with a token the
#               server mints at start, so this is a start -> read-token ->
#               start-worker sequence (not expressible in a compose file — which
#               is why gpustack lives here and only new-api is in compose).
# Idempotent: reuses the box's existing gpustack-data volume (registry + weights).
set -euo pipefail
IMG="${GPUSTACK_IMAGE:-quay.io/gpustack/gpustack:latest}"
REGISTRY="${GPUSTACK_REGISTRY:-quay.io}"
# The worker must reach the server; default to the box's primary IP. On a box
# whose NIC changes, override with a NIC-independent address.
ADDR="${GPUSTACK_ADVERTISE_ADDR:-$(hostname -I | awk '{print $1}')}"

if ! docker ps --format '{{.Names}}' | grep -qx gpustack; then
  docker rm -f gpustack 2>/dev/null || true
  docker run -d --name gpustack --restart unless-stopped --ipc host -p 80:80 \
    -v gpustack-data:/var/lib/gpustack -v /var/run/docker.sock:/var/run/docker.sock \
    "$IMG" --system-default-container-registry "$REGISTRY"
  echo "[gpustack] server started"
fi

echo "[gpustack] waiting for the server to mint the worker token"
tok=""
for _ in $(seq 1 60); do
  tok="$(docker exec gpustack sh -c 'cat /var/lib/gpustack/worker_token 2>/dev/null' 2>/dev/null || true)"
  [ -n "$tok" ] && break
  sleep 2
done
[ -n "$tok" ] || { echo "[gpustack] worker token never appeared"; exit 1; }

if ! docker ps --format '{{.Names}}' | grep -qx gpustack-worker; then
  docker rm -f gpustack-worker 2>/dev/null || true
  docker run -d --name gpustack-worker --restart unless-stopped --network host --privileged --gpus all \
    -v gpustack-data:/var/lib/gpustack -v /var/run/docker.sock:/var/run/docker.sock \
    "$IMG" --server-url "http://$ADDR" --token "$tok" \
    --advertise-address "$ADDR" --system-default-container-registry "$REGISTRY"
  echo "[gpustack] worker started (advertise $ADDR)"
fi
echo "[gpustack] up — OpenAI endpoint http://$ADDR/v1-openai (admin on :80)"
