#!/usr/bin/env bash
# Build the sudorouter (nova-gateway) image for this box's architecture.
# The nova-gateway source is shipped to the box from the VPN machine
# (git bundle / git archive over the LAN).
#
# In regions where Docker Hub is unreachable, base images are pulled from a
# mirror and retagged to their canonical names, so `docker build` finds them
# locally without reconfiguring (or restarting) the docker daemon.
set -euo pipefail
SRC="${1:-$HOME/nova-gateway}"
MIRROR="${MIRROR:-docker.1ms.run/library}"
[ -d "$SRC" ] || { echo "nova-gateway source not found at $SRC"; exit 1; }

for img in alpine:3.22 golang:1.26-alpine3.22 node:18.20.8-slim; do
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "[build] staging $img from $MIRROR"
    docker pull "$MIRROR/$img"
    docker tag "$MIRROR/$img" "$img"
  fi
done

cd "$SRC"
# Point the in-image package managers at regional mirrors (idempotent).
grep -q registry.npmmirror Dockerfile || \
  sed -i 's#pnpm config set store-dir /.pnpm-store#pnpm config set store-dir /.pnpm-store \&\& pnpm config set registry https://registry.npmmirror.com/#' Dockerfile
sed -i 's@# RUN go env -w GOPROXY=https://goproxy.cn,direct@RUN go env -w GOPROXY=https://goproxy.cn,direct@' Dockerfile

DOCKER_BUILDKIT=1 docker build -t sudorouter:latest .
echo "[build] built sudorouter:latest"
