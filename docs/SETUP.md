# DGX Spark — sudo stack runbook

> SSH in? Read this first. Canonical box configuration lives here.
> **Architecture & rationale**: the design doc on ShareOne
> ([sudo-cloud-plan](https://s.shareone.vip/md/sudo-cloud-plan)). This runbook holds only
> box-specific configuration; it references the design doc rather than repeating it.

## The box
NVIDIA **DGX Spark (GB10 Blackwell)**, aarch64, Ubuntu 24.04, kernel 6.17, GPU
driver 580, **CUDA 13.0** (`/usr/local/cuda-13.0`). Borrowed machine, in China.
- **Unified memory**: 121 GiB shared by CPU and GPU — one physical pool; a served model occupies this.
- **Disk**: 3.7 TB NVMe (`/`); model weights cache at `/var/lib/gpustack/cache/...` and persist across restarts. Loaded into memory on demand (cold start reads tens of GB from NVMe).
- Footprint stays minimal (borrowed); credentials live in the password-agent vault and `~/sudo-dgx/*`.

## Access
- user `taolei` (sudo), host `spark-07dc`. Reachable at `192.168.1.12` (ethernet) and `192.168.1.11` (WiFi).
- Passwordless SSH key from Ethan's Windows box is installed.
- sudo over a non-TTY SSH session: `echo "$PW" | sudo -S -p "" <cmd>`.
- `source ~/sudo-dgx/env.sh` sets cargo env, CUDA PATH, and mirror vars.

## Package & image sources (regional mirrors)
- **Rust/crates**: rsproxy.cn (in `~/.cargo/config.toml`; rustup installed via `RUSTUP_DIST_SERVER=https://rsproxy.cn`).
- **Docker images**: quay.io and nvcr.io (NGC) reach directly. For Docker Hub images, pull from `docker.1ms.run/library/<img>` and retag to the canonical name so `docker build` finds them locally (leaves the docker daemon untouched → running containers stay up).
- **PyPI**: `https://pypi.tuna.tsinghua.edu.cn/simple`. **Go**: goproxy.cn. **npm/pnpm**: registry.npmmirror.com.
- **Source repos**: arrive over the LAN from the VPN box — `git bundle create x.bundle HEAD` (or `git archive`) → `scp` → clone/extract here.
- Detached long jobs: `setsid bash job.sh </dev/null >/dev/null 2>&1 &`, then tail a log.

## gpustack — local inference
Image `quay.io/gpustack/gpustack`; GPU reaches containers via the nvidia container runtime (`--gpus all`; GB10 visible in-container). OpenAI-compatible endpoint `http://127.0.0.1/v1-openai`; API key in vault "GPUStack API key (DGX Spark)" and `~/sudo-dgx/gpustack-key.json`.
- The **worker** also needs `--gpus all`; a previously running model does not prove the worker can detect the GPU and schedule its replacement. Verify both worker GPU inventory and the runner process arguments after changes.
- Each model gets a **model-route** to be exposed on the gateway: `POST /v2/model-routes` (name → target `model_id`). If `/v1-openai/models` is empty for a running model, create its route.
- Model `backend_parameters`:
  - `--enable-auto-tool-choice --tool-call-parser hermes` (hermes = Qwen family) so `tool_choice:auto` is served.
  - `--gpu-memory-utilization <f>` sizes the KV cache against unified memory; choose per model so weights + KV fit with OS headroom.
  - `--max-model-len <N>` bounds context.
  - New `backend_parameters` take effect after `DELETE /v2/model-instances/{id}` (the scheduler recreates the instance from the spec).

## Browser deployment and acceptance — 2026-10-09

- Browser: **http://localhost:12808** on Windows, forwarded over SSH to DGX
  loopback 26808. `scripts/open-webui.ps1` installs `SudoEdge-WebUI-12808`
  with sign-in startup and automatic reconnect. Reconnect after killing its
  SSH child and after DGX reboot passed. Actual Windows sign-out/reboot remains
  untested. Password-agent entry: **SudoEdge DGX WebUI**, username `admin`.
- Deployment root: `~/sudo-dgx/bringup`. Local Moss uses mTLS to primary Nexus
  22140 for vault/login and separately to cohost execution Nexus 22141.
  `MOSS_DEFAULT_RUNTIME=cohost` selects
  `WebUI → Moss → ManagedAgentService → in-process scode → Nexus /model →
  new-api → GPUStack`. Real browser answers and the corresponding Router
  request passed. No per-session scode process is launched. The primary and
  execution services have separate data/identity directories, so execution
  restarts do not interrupt authentication.
- Moss [#347](https://github.com/sudoprivacy/moss/pull/347),
  [#348](https://github.com/sudoprivacy/moss/pull/348) and
  [#349](https://github.com/sudoprivacy/moss/pull/349) are merged;
  deployed ARM64 bundle source: `0ac91283`. Bundle SHA-256:
  `69fb888e45012660834d32e9eef100304f4b03ca72682795ce1c0d47b3e672a2`.
  It persists the native cohost ID in
  `.moss/cohost-session.json`, resumes through ACP `session/load`, and routes
  owner-verified workspace I/O through Nexus. Fresh repositories use
  `/agents/{agent}/workspaces/{Moss-session-id}`, independent of managed PID.
  Older sessions without this locator retain their recorded repository identity.
- Complete WebUI server/client image: `sudoedge-webui:handoff-73957978`, source
  `73957978ddfa5c6fd3b192fedcc213bdf60ac915`, image ID
  `sha256:695de69b2cc0584e56e42e18d4e51c021acf0d582e46a44d6b83bff604bd05ef`.
  This includes the upstream reconnect fix; replacing only the frontend does
  not update the server's session-lock behavior.
- Execution uses the green ARM64 release-build artifact of
  [sudocode #903](https://github.com/sudoprivacy/sudocode/pull/903), source
  `ae5cd369`, carrying Nexus **v0.8.2**, plugin ABI 7 and the egress gate.
  SHA-256: `ded18b089bbba15adab73e0e4b96afa20c1334ba064bd3c0029175be6c81b727`.
  Installed path:
  `~/sudo-dgx/shared-assembly/cohost-ae5cd369682f/ci-release/nexusd-cohost-linux-arm64/nexusd-cohost`.
  This is a PR build of merged code, not a new numbered cohost release.
- Local model: Qwen3-30B-A3B-Thinking-2507-FP8, vLLM 0.22.1, context 65536,
  output limit 4096, GPU memory utilization 0.60, `--tool-call-parser hermes`
  and `--reasoning-parser qwen3`. Router advertises these capabilities. Execution
  names `qwen3-30b` with `baseUrl=nexus:///model`; the mount owns the local-only key.
- User units `sudoedge-nexus`, `sudoedge-cohost-model` and `sudoedge-moss` start
  with lingering enabled. WebUI/Postgres and Presidio use Docker restart policies.
  Root `sudoedge-reconfigure` provisions RAM-backed new-api state, refreshes
  Moss's local Router key and restores the model mount.
- Actual reboot `2026-10-08T16:00:05Z` restored services, online connectivity,
  local credentials and the mount. Boot ID: `5c027e7c-152e-4759-b8de-64f5c07c87cc`.
  [sudoedge #4](https://github.com/sudoprivacy/sudoedge/pull/4) fixes the early-boot
  nftables temporary-file failure; its real IPv4/IPv6 namespace test passed.
  A second reboot of the latest deployment changed the boot ID to
  `2d1c9f28-7ae0-48cd-b31e-383f6d7f3b7a`. Local Qwen, WebUI, Moss, cohost,
  Router credentials and model mount recovered automatically. In existing
  session `9fad0824-7713-4584-9165-23d2096d65cc`, managed PID changed from
  `pid-fadfd9668c0f` to `pid-a05e23c1db18`, native session ID stayed
  `session-1791482406416-2`, and a fresh question answered `7397` from the
  pre-reboot remembered `7395`. Browser reads returned the original 18-byte
  `proof.txt` and 19-byte `uploaded.txt`, both HTTP 200. Evidence:
  `~/sudo-dgx/shared-assembly/reboot-latest-20261009/`.
  Cloud credential restoration remains untested because no cloud key is installed.
- Operations: `sudoedge status`, `sudoedge webui status`,
  `sudo sudoedge connectivity local|online`, `sudoedge model restore`.
  Saved connectivity restores at boot. Real host/Docker WAN blocking, LAN WebUI,
  local inference and IPv4/IPv6 regression passed. Current mode: `online`.
- Last direct cloud-session acceptance: October 2. DGX WebUI logged into production
  Moss and session `0be68ba5-05ce-4028-9cc2-3cde7c73c137` created/read `cloud-check.txt`,
  returning `CLOUD_OK_20261002`. That audit used external scode. Re-audit the
  deployed cloud route before claiming cohost migration complete.
- Earlier local browser checks passed arithmetic across turns, visible history
  after reload, cancellation and a fresh answer afterward. The CSV task in
  `78eb44be-6275-47e4-abce-482c6fb2e4de` exposed model mistakes: a missing newline
  and an unchanged result file. An explicit browser-issued `awk` command fixed
  actual files to total 60. Autonomous task quality remains separate from
  transport/tool execution acceptance.
- Latest real browser checks passed multi-turn answers, tool approval, file
  preview, page reload and cancellation followed by a fresh answer. The captured
  WebSocket sequence includes `stop`, upstream result and return to an idle
  writer. Canonical Nexus paths passed agent Write/Read and authenticated WebUI
  upload/read APIs. The upload API check does not cover the file-picker UI.
  **Open filesystem defect:** writing through
  `/proc/{pid}/workspace/{repo-alias}/...` can report success while no file is
  created. Native alias resolution, kernel miss error propagation and model
  workspace context must be fixed before declaring basic file tasks complete.
- gVisor is not installed on the box. Real agent A2A, artifact export governance
  and Windows sign-in startup remain follow-up acceptance.

## Content gate deployment

Shared implementation/assembly lives in
[`sudostack/security/egress-gate`](https://github.com/sudoprivacy/sudostack/tree/main/security/egress-gate),
merged in [#31](https://github.com/sudoprivacy/sudostack/pull/31).
Box-specific wiring and evidence live here.

The installed execution cohost carries the gate. Its service drop-in sets
`NEXUS_EGRESS_GATE_MODEL_MOUNTS=/cloud-model`, Presidio URL
`http://127.0.0.1:59080`, entities `PERSON,LOCATION,ORGANIZATION`, timeout
10000 ms. Container `sudoedge-presidio` uses `sudo-presidio-zh:local`, loopback
binding, a 4 GiB cap and `restart=unless-stopped`; health returned 200.
The cloud mount is not provisioned. These settings alone do not establish
production cloud-prompt acceptance.

The **same installed cohost artifact** passed all 40 shared harness assertions
in isolation: real new-api/Qwen replies, redacted cloud-mount wire bytes,
JSON-escaped Chinese input, intact local-mount bytes, stored redacted prompts
and no raw fixtures in daemon audit logs. Evidence:
`~/sudo-dgx/shared-assembly/egress-acceptance-ae5cd369-20261009/`.
This run did not repeat the earlier CC red controls. A separate real-driver
negative-control run verified deny and analyzer outage against controlled
loopback HTTP upstreams: denied cloud requests produced zero upstream calls;
analyzer outage also blocked cloud calls; local PII remained intact and allowed.
Evidence: `~/sudo-dgx/shared-assembly/egress-negative-r3-20261009/acceptance.json`.
These controls do not establish production cloud-model acceptance.

Next: fix the native file alias and misleading write-success behavior, then
configure the cloud-only mount with encrypted bootstrap credentials and
verify allow/redact/deny and analyzer outage. Cross-domain A2A must enter this
box's kernel before federation to receive the gate; direct external-broker
writes bypass it. Artifact exports also need a governed route. Neither path
is accepted by the model-plane harness.

Script checks: `sudo bash tests/connectivity.sh`,
`python3 tests/model-config.py` and `python3 tests/router-config.py`.
Keep generated credentials outside git.

## new-api — local SudoRouter

October 6 read-only check: the Router still runs revision `41868d6f` with
the expected source label and `/new-api` entry point. WebUI, Moss, the browser
Nexus and the separate cohost model service are active; connectivity is online.
The first diagram in [the shared architecture](https://s.shareone.vip/md/sudo-cloud-plan)
now includes the Edge WebUI/Moss, cohost, Router, GPUStack and optional cloud
paths. The local browser path has now passed the cohost acceptance recorded
above; the cloud production migration remains a separate deployment.

The appliance and sudorouter.ai use **sudoprivacy/new-api**. DGX currently
runs production branch `sudo/rc24`, revision `41868d6f`, built for ARM64.
Container `sudoedge-sudorouter-1` runs `/new-api`, image
`sudoedge-new-api:41868d6f` (also tagged `sudoedge-new-api:local`), on port 3000.
The image records source/revision labels. Source snapshot: `~/new-api`.
The October 3 deployment cross-compiled the Go binary and embedded the
frontend built from the same revision, then packaged it with the upstream
Debian runtime dependencies and license files. Cloud was not redeployed.

Build from a checkout and deploy:

```bash
ROUTER_IMAGE=sudoedge-new-api:local bash scripts/build-new-api.sh ~/new-api
docker compose -f compose/docker-compose.yml up -d
# GPUSTACK_KEY is supplied by the deployment credential store.
bash scripts/configure.sh
```

- Database `/data/one-api.db` is in container tmpfs. `sudoedge-reconfigure`
  provisions it at boot and refreshes local Moss and Nexus credentials.
- Administrator: `root`, password file `~/sudo-dgx/router-admin-pw.txt`,
  mode 0600. Provisioning uses new-api setup and bearer access-token APIs.
- Channel `gpustack-local`: type 8, endpoint
  `http://127.0.0.1/v1-openai/chat/completions`, model `qwen3-30b`.
  Local inference has model ratio zero; GPU calls do not consume Router credit.
- `/v1/models` advertises context 65536, output 4096, tool calling enabled,
  vision disabled. Full relay credentials come from `POST /api/token/:id/key`;
  list responses contain masked values and cannot provision clients.
- `~/.nexus/sudocode/sudocode.json` has providers `sudorouter` and `gpustack`:
  `qwen3-local` selects `http://127.0.0.1:3000/v1`; `qwen3-direct` selects GPUStack.
  Run `scode --auth api-key --model qwen3-local "<prompt>"` from a project directory.
- Set `SUDOROUTER_KEY` and explicit `SUDOROUTER_MODELS` to configure an enabled
  cloud channel in `external`; the GPUStack channel is in `local`. Provisioning
  creates separate `sudocode-local` and `sudocode-cloud` tokens with cross-group
  retry disabled. The local token cannot select a cloud-only model, and a
  failing GPUStack route cannot fall through to a cloud channel. Channel base URL defaults to
  `https://hk.sudorouter.ai` (the Router adds `/v1`). DGX currently has only
  the local channel. Cloud credentials and their cold-boot recovery remain open.
- Acceptance: both a migrated database copy and fresh tmpfs initialization
  passed model catalog, real Qwen SSE completion and a `record_result`
  tool call with `total: 96`. Production provisioning and credential refresh
  also passed. Migration snapshots are private and held only in RAM.
- Browser session `47ad86d2-97f6-4f05-a6d6-02a82d32f3e5` passed two turns
  (`42`, then `50`), page reload with visible history, cancellation of a long
  generation over WebSocket, and a fresh same-session answer (`63`) afterward.
  The earlier CSV autonomous file-update quality case remains separate.

October 9: the separate groups and tokens passed a real new-api integration
check with the same model name in both channels. A local upstream failure
produced zero cloud requests; a local token selecting a cloud-only model was
rejected; the external token reached its designated cloud fixture. Evidence:
`~/sudo-dgx/shared-assembly/router-separated-20261009/acceptance.json`.

For the actual Qwen3.8 load/inference result and reproduction parameters, see
[QWEN38.md](QWEN38.md). The experiment has stopped and the normal Qwen3 service
is restored.

## Restore Nexus model mounts

Nexus owns `/model`; Router owns the upstream model route. The Edge startup
hook waits for Nexus over mTLS, reads the current Router credential and
applies the OpenAI backend. A failed hook fails the service start. The same
hook runs after Router reprovisioning, so a regenerated token replaces the
mount's old credential.

Build the helper on a development machine:

```bash
cd scripts/nexus
bun install --frozen-lockfile
bun build mount-model.mjs --target=node --outfile mount-model.bundle.mjs
```

Prepare a private JSON configuration using the deployed paths:

```json
{
  "endpoint": "127.0.0.1:22141",
  "protoRoot": "/home/taolei/sudo-dgx/bringup/grpc-client/proto",
  "tlsDir": "/home/taolei/sudo-dgx/bringup/cohost-model-validation/data/tls",
  "routerConfig": "/home/taolei/.nexus/sudocode/sudocode.json",
  "mountPath": "/model",
  "zoneId": "model",
  "blobRoot": "/home/taolei/sudo-dgx/bringup/cohost-model-validation/model-cache"
}
```

Install for the owning user service (use its target name when migrating):

```bash
SUDOEDGE_NODE_BINARY=/home/taolei/sudo-dgx/bringup/node/node \
  bash scripts/install-model-mount.sh sudoedge-cohost-model.service \
  /path/to/model-mount.json /path/to/mount-model.bundle.mjs
systemctl --user restart sudoedge-cohost-model.service
sudoedge model restore
```

Installed config: `~/.config/sudoedge/model-mount.json`; helper and Node path:
`~/.local/lib/sudoedge`. Replacing the target unit requires removing the old
unit's `model-mount.conf` drop-in. After restarting, start a real embedded
session and verify a new model answer. Old transient reply streams are not
a valid recovery assertion.

## Memory safety (unified-memory machine)
One physical pool (RAM = GPU = 121 GiB): a served model's weights + KV cache + preprocessing all draw from it. Guardrails keep the box remotely recoverable and turn an over-allocation into a cheap clean kill.
- cgroup **MemoryMin** reservations persist across reboot: `system.slice=12G`, `ssh.service=512M` → SSH and the OS stay responsive under memory pressure (verify: `systemctl show -p MemoryMin ssh.service`).
- systemd service **`sudo-mem-guard`** (root, `OOMScoreAdjust=-900`, `Restart=always`, enabled): `/usr/local/bin/sudo-mem-guard.sh`, log `/var/log/sudo-mem-guard.log`.
  1. Caps each vLLM container cgroup `memory.max = RAM−14G` (~108G), re-applied to the ephemeral `/system.slice/docker-*.scope` (defense-in-depth for host-side allocations).
  2. Tripwire: when system `MemAvailable` stays below 6G for ~15s, reclaims the largest vLLM process. This covers GPU/unified allocations (which are charged outside per-cgroup accounting), making the tripwire the effective backstop.
  Tuned to act only at genuine near-OOM (a clean kill), well above any single sane model.
- Operate: `systemctl status sudo-mem-guard`; `sudo tail -f /var/log/sudo-mem-guard.log`. If the guard and gpustack cycle (kill → restart → kill), set that model's `replicas=0` via the gpustack API and resize.
- Sizing: one resident model at a time (others on disk); size by **peak** (weights + KV + preprocessing) with OS headroom.

## External trust material on DGX

The earlier cross-organization bootstrap used trust domain `sudoedge-dgx-dev`.
Its CA certificate remains at
`~/nexus-v070/nexusd-cluster-linux-aarch64/dgx-dev/tls/ca.pem`; the agent bundle
remains in `~/wbundle` (`agent.pem`, `agent-key.pem`, `ca.pem`). Both locations
were checked on October 2. Keep the CA private key on the appliance.

The broker endpoint is `broker.sudoprivacy.com:8443`, with server name
`nexus-node`. The bundle's `ca.pem` verifies the cloud broker; the agent leaf
uses the appliance's external CA. This is distinct from the local browser
bring-up's `bringup/nexus-data` identity. Recheck the broker's current public
CA registration and caller stamping with a real cohost agent before accepting
cross-domain collaboration for the new deployment. Existing certificate files
alone do not establish that acceptance.

Shared design: [Nexus authentication](https://s.shareone.vip/s/nexus-auth-architecture)
and [federation runbook](https://s.shareone.vip/s/federation-cross-machine-runbook).
