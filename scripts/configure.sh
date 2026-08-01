#!/usr/bin/env bash
# Configure nova-gateway and wire sudocode — the runbook's manual steps as code.
# Assumes fresh router state (its /data is RAM-backed), so it runs on each deploy.
#
# Secrets come from the environment, never the repo:
#   GPUSTACK_KEY     local gpustack API key (required)
#   SUDOROUTER_KEY   cloud upstream key (optional; injected just-in-time)
#   ADMIN_PW         router admin password (default below)
set -euo pipefail
B="${NOVA_URL:-http://127.0.0.1:3000}"
GPUSTACK_KEY="${GPUSTACK_KEY:?set GPUSTACK_KEY}"
GPUSTACK_URL="${GPUSTACK_URL:-http://127.0.0.1/v1-openai}"
ADMIN_PW="${ADMIN_PW:-SudoRouter@26}"
MODEL="${MODEL:-qwen3-30b}"

echo "[configure] waiting for nova-gateway"
for _ in $(seq 1 30); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$B/api/status")" = "200" ] && break; sleep 2
done

login() { # $1=password → prints "session=..." or empty
  curl -s -D - -o /dev/null -H 'Content-Type: application/json' \
    --data "{\"username\":\"root\",\"password\":\"$1\"}" "$B/api/user/login" \
    | grep -i '^set-cookie:' | sed -E 's/.*(session=[^;]+).*/\1/' | tr -d '\r' || true
}

# The fork seeds root/sudosudo; adopt the desired admin password.
SC="$(login "$ADMIN_PW")"; [ -n "$SC" ] || SC="$(login sudosudo)"
AUTH=(-H "Cookie: $SC" -H "New-Api-User: 1")
curl -s "${AUTH[@]}" "$B/api/user/1" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];d['password']='$ADMIN_PW';open('/tmp/u.json','w').write(json.dumps(d))"
curl -s "${AUTH[@]}" -H 'Content-Type: application/json' -X PUT --data @/tmp/u.json "$B/api/user/" >/dev/null
SC="$(login "$ADMIN_PW")"; AUTH=(-H "Cookie: $SC" -H "New-Api-User: 1")

echo "[configure] self-use mode (local models serve without per-model pricing)"
curl -s "${AUTH[@]}" -H 'Content-Type: application/json' -X PUT \
  --data '{"key":"SelfUseModeEnabled","value":"true"}' "$B/api/option/" >/dev/null

echo "[configure] local gpustack channel"
curl -s "${AUTH[@]}" -H 'Content-Type: application/json' --data \
  "{\"mode\":\"single\",\"channel\":{\"type\":8,\"name\":\"gpustack-local\",\"key\":\"$GPUSTACK_KEY\",\"base_url\":\"$GPUSTACK_URL/chat/completions\",\"models\":\"$MODEL\",\"group\":\"default\",\"groups\":[\"default\"]}}" \
  "$B/api/channel/" >/dev/null

if [ -n "${SUDOROUTER_KEY:-}" ]; then
  echo "[configure] cloud channel (sudorouter.ai — key injected just-in-time)"
  CLOUD_URL="${SUDOROUTER_URL:-https://hk.sudorouter.ai/v1}"
  CLOUD_MODELS="${SUDOROUTER_MODELS:-claude-opus-4-8,gpt-5.5,gemini-3.5-flash,deepseek-v4-pro}"
  curl -s "${AUTH[@]}" -H 'Content-Type: application/json' --data \
    "{\"mode\":\"single\",\"channel\":{\"type\":1,\"name\":\"sudorouter-cloud\",\"key\":\"$SUDOROUTER_KEY\",\"base_url\":\"$CLOUD_URL\",\"models\":\"$CLOUD_MODELS\",\"group\":\"default\",\"groups\":[\"default\"]}}" \
    "$B/api/channel/" >/dev/null
fi

echo "[configure] relay token"
curl -s "${AUTH[@]}" -H 'Content-Type: application/json' --data \
  '{"name":"sudocode","expired_time":-1,"unlimited_quota":true,"model_limits_enabled":false,"group":"default"}' \
  "$B/api/token/" >/dev/null
TOK="sk-$(curl -s "${AUTH[@]}" "$B/api/token/?p=0&page_size=10" \
  | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];it=d['items'] if isinstance(d,dict) else d;print(next((t['key'] for t in it if t['name']=='sudocode'),''))")"

echo "[configure] wiring sudocode.json"
python3 - "$TOK" "$GPUSTACK_KEY" "$MODEL" "$GPUSTACK_URL" <<'PY'
import json,sys,pathlib
tok,gkey,model,gurl=sys.argv[1:5]
cfg={"auth_modes":{"api-key":{
      "nova-gateway":{"baseUrl":"http://127.0.0.1:3000/v1","apiKey":tok},
      "gpustack":{"baseUrl":gurl,"apiKey":gkey}}},
     "models":{
      "qwen3-local":{"alias":"qwen3-local","name":"Qwen3-30B via nova-gateway","input":["text"],
        "providers":{"api-key":{"provider":"nova-gateway","model":model,"api":"openai-completions"}}},
      "qwen3-direct":{"alias":"qwen3-direct","name":"Qwen3-30B direct gpustack","input":["text"],
        "providers":{"api-key":{"provider":"gpustack","model":model,"api":"openai-completions"}}}}}
d=pathlib.Path.home()/".nexus"/"sudocode"; d.mkdir(parents=True,exist_ok=True)
(d/"sudocode.json").write_text(json.dumps(cfg,indent=2,ensure_ascii=False))
c=d/"cache"; c.mkdir(exist_ok=True)
(c/"model-capabilities.json").write_text(json.dumps({"models":{model:{"context_window":32768,"max_output_tokens":8192}}},indent=2))
print("  sudocode: qwen3-local -> nova-gateway (primary), qwen3-direct -> gpustack (fallback)")
PY
echo "[configure] done"
