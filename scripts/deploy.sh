#!/usr/bin/env bash
# One-command sudoedge bring-up on a DGX. Chains the validated pieces; all
# secrets come from the environment (never the repo).
#
# Required env:
#   GPUSTACK_ADMIN_PW    gpustack admin password (management API)
# Optional env:
#   SUDOROUTER_KEY       cloud upstream key (sudorouter.ai) — injected just-in-time
#   NEW_API_SRC         sudoprivacy/new-api source dir       (default ~/new-api)
#   MODEL_* / GPUSTACK_* overrides for deploy-model.sh / deploy-gpustack.sh
#
# Usage:  GPUSTACK_ADMIN_PW=... bash scripts/deploy.sh
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"; repo="$(cd "$here/.." && pwd)"; cd "$repo"
: "${GPUSTACK_ADMIN_PW:?set GPUSTACK_ADMIN_PW}"
GPUSTACK_URL="${GPUSTACK_URL:-http://127.0.0.1}"

echo "== 1/6 build the router image =="
scripts/build-new-api.sh "${NEW_API_SRC:-$HOME/new-api}"

echo "== 2/6 host layer (prerequisites + guardrails + local credentials) =="
sudo bash scripts/bootstrap.sh

echo "== 3/6 gpustack (server + privileged worker) =="
scripts/deploy-gpustack.sh

echo "== 4/6 router (new-api) =="
docker compose -f compose/docker-compose.yml up -d

echo "== 5/6 model onto gpustack =="
scripts/deploy-model.sh

echo "== mint an inference key for the router to reach gpustack =="
GPUSTACK_KEY="$(GPUSTACK_URL="$GPUSTACK_URL" GPUSTACK_ADMIN_PW="$GPUSTACK_ADMIN_PW" python3 - <<'PY'
import json, os, urllib.request, urllib.parse, http.cookiejar
base = os.environ["GPUSTACK_URL"]; pw = os.environ["GPUSTACK_ADMIN_PW"]
cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.open(urllib.request.Request(base + "/auth/login",
    data=urllib.parse.urlencode({"username": "admin", "password": pw}).encode()), timeout=10)
r = op.open(urllib.request.Request(base + "/v2/api-keys",
    data=json.dumps({"name": "sudoedge-router"}).encode(),
    headers={"Content-Type": "application/json"}), timeout=10)
print(json.load(r)["value"])
PY
)"
export GPUSTACK_KEY

echo "== 6/6 wire channels + sudocode (cloud key injected if SUDOROUTER_KEY set) =="
scripts/configure.sh

echo "== done — try:  scode --auth api-key --model qwen3-local \"...\" =="
