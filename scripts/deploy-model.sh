#!/usr/bin/env bash
# Deploy a model onto the local gpustack and expose it via a model-route.
# gpustack management uses the admin session (the API key is inference-scoped),
# so this needs the gpustack admin password.
#
# Env:
#   GPUSTACK_ADMIN_PW   (required) gpustack admin password
#   MODEL_NAME          served name + route name          (default qwen3-30b)
#   MODEL_SOURCE        model_scope | huggingface | local_path (default model_scope)
#   MODEL_ID            source id / repo / path           (default Qwen/Qwen3-30B-A3B-Thinking-2507-FP8)
#   MODEL_BACKEND       (default vLLM)
#   MODEL_MAX_LEN       context length                    (default 32768)
#   MODEL_BACKEND_PARAMS JSON array of vLLM flags
#   GPUSTACK_URL        (default http://127.0.0.1)  GPUSTACK_CLUSTER_ID (default 1)
set -euo pipefail
: "${GPUSTACK_ADMIN_PW:?set GPUSTACK_ADMIN_PW}"
python3 - <<'PY'
import json, os, sys, time, urllib.request, urllib.parse, http.cookiejar
base = os.environ.get("GPUSTACK_URL", "http://127.0.0.1")
pw   = os.environ["GPUSTACK_ADMIN_PW"]
name = os.environ.get("MODEL_NAME", "qwen3-30b")
src  = os.environ.get("MODEL_SOURCE", "model_scope")
ref  = os.environ.get("MODEL_ID", "Qwen/Qwen3-30B-A3B-Thinking-2507-FP8")
backend = os.environ.get("MODEL_BACKEND", "vLLM")
maxlen  = int(os.environ.get("MODEL_MAX_LEN", "32768"))
cluster = int(os.environ.get("GPUSTACK_CLUSTER_ID", "1"))
bparams = json.loads(os.environ.get("MODEL_BACKEND_PARAMS",
  '["--gpu-memory-utilization","0.60","--max-model-len","32768","--enable-auto-tool-choice","--tool-call-parser","hermes"]'))

cj = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def call(path, data=None, method=None):
    hdr = {"Content-Type": "application/json"} if data is not None else {}
    body = json.dumps(data).encode() if data is not None else None
    r = op.open(urllib.request.Request(base + path, data=body, headers=hdr, method=method), timeout=30)
    t = r.read().decode(); return json.loads(t) if t.strip() else {}
op.open(urllib.request.Request(base + "/auth/login",
    data=urllib.parse.urlencode({"username": "admin", "password": pw}).encode()), timeout=10)

# create (idempotent by name; the management registry is per-cluster)
m = next((x for x in call("/v2/models").get("items", []) if x["name"] == name), None)
if m:
    print("  model '%s' already registered (id=%s, replicas=%s)" % (name, m["id"], m["replicas"]))
else:
    spec = {"name": name, "source": src, "backend": backend, "replicas": 1,
            "categories": ["llm"], "backend_parameters": bparams, "cluster_id": cluster,
            "worker_selector": {}, "placement_strategy": "spread", "meta": {"max_model_len": maxlen}}
    spec[{"model_scope": "model_scope_model_id", "huggingface": "huggingface_repo_id",
          "local_path": "local_path"}[src]] = ref
    m = call("/v2/models", spec); print("  created model '%s' id=%s" % (name, m["id"]))

# poll to running (a cold model downloads weights first)
mid = m["id"]
for i in range(360):  # up to ~30 min
    states = [x.get("state") for x in call("/v2/model-instances?model_id=%s" % mid).get("items", [])]
    if "running" in states: print("  model '%s' RUNNING" % name); break
    if i % 6 == 0: print("  ...%s (%ds)" % (states or "no-instance", i * 5))
    time.sleep(5)
else:
    print("  WARN: '%s' not running after timeout" % name); sys.exit(1)

# ensure a model-route (auto-creation can be missed; the route matches by name)
if not any(r["name"] == name for r in call("/v2/model-routes").get("items", [])):
    call("/v2/model-routes", {"name": name}); print("  created route '%s'" % name)
print("  done: '%s' served on %s/v1-openai" % (name, base))
PY
