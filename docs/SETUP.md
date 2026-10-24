# DGX Spark — sudo stack runbook

> SSH in? Read this first. Canonical box configuration lives here.
> **Architecture & rationale**: the design doc on ShareOne
> ([sudo-cloud-plan](https://s.shareone.vip/s/sudo-cloud-plan)). This runbook holds only
> box-specific configuration; it references the design doc rather than repeating it.

## Existing-runtime maintenance

The appliance consumes the source-pinned sudostack deploy actions through
`scripts/stack-action.py`; it does not carry a second checkpoint or installer.
For a controller/cohost upgrade, prepare an owner-only device plan containing
the actual units in controller-first stop order, executable hashes, durable
paths and configuration pins. Then run:

```sh
SUDOSTACK_DEPLOY_ROOT=/verified/stack python3 scripts/stack-action.py \
  checkpoint inspect --plan /private/device-checkpoint.json --output /private/new-checkpoint
```

Replace `inspect` with `checkpoint` only at the product's maintenance point.
The common action stops the selected services, copies the cold state, and
restores their original executables in reverse order. Include Moss's durable
home, cohost data/identity/config, controller identity, selected unit files and
drop-ins, plus the Moss application entry pin. Keep model weights and the
independent vault/login service out of the stop set. Inspect actual native
Agent/attempt activity before maintenance; addressability and old reader
registers do not prove idle. Verify authenticated product readiness afterward.

Use producer offline checks on the private checkpoint before an upgrade.
Do not run a duplicate live Node identity, replace model/content-gate settings,
or restore the old database over newer accepted writes. Checkpoint success is
not a new-runtime, session-recovery, domain-join or seven-party acceptance.

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

## Browser deployment and acceptance — 2026-10-10

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
  [#348](https://github.com/sudoprivacy/moss/pull/348),
  [#349](https://github.com/sudoprivacy/moss/pull/349) and
  [#352](https://github.com/sudoprivacy/moss/pull/352) are merged;
  deployed ARM64 bundle source: `2ff81bb3a9d2f7fdefd013c88335ef225b9ab7bf`.
  Server bundle SHA-256:
  `f1b8b1b5fcfebf4f4c0a80fb7be9526cd220da251ca80caf8bf88b14980b9eb4`.
  It persists the native cohost ID in
  `.moss/cohost-session.json`, resumes through ACP `session/load`, and routes
  owner-verified workspace I/O through Nexus. Fresh repositories use
  `/agents/{agent}/workspaces/{Moss-session-id}`, independent of managed PID.
  Older sessions without this locator retain their recorded repository identity.
  The execution prompt uses the Nexus repository instead of the host transcript
  directory. Live and stored tool results retain actual output and error status;
  transcript appends are ordered and drained before transport close. All seven
  PR checks and the post-merge branch checks passed. Deployment backup:
  `~/sudo-dgx/shared-assembly/moss-workspace-context-20261010/deployment-backup-20261009T171026Z/`.
- Complete WebUI server/client image: `sudoedge-webui:handoff-73691345`, source
  `73691345f20032ec8d5d23ca6244552a45bee68f`, image ID
  `sha256:5cba7445991475547907237f7edf884df46f62e88e5be72a53fe3f86c3b70683`.
  [Sudowork #1222](https://github.com/sudoprivacy/sudowork/pull/1222) merged after
  all latest checks passed: 32 successful and one expected skip. It forwards
  actual tool results and artifact events, retains failed status, and preserves
  whitespace in streamed text. Desktop tests: 3149 passed, 36 conditional skips;
  Linux WebUI tests: 219 unit, 44 contract and 81 real PostgreSQL integration.
  The deployed container's effective image and module exports were checked.
  Upgrade started with zero active browser writers and backed up PostgreSQL:
  `~/sudo-dgx/shared-assembly/webui-cohost-events-20261010/deployment-backup-20261009T183520Z/`.
  Its dump SHA-256 is
  `3f25c7d427aa836b29947a7505c9965dd1e06f2f912c1f9f144640c3d91b450e`.
  Replacing only the frontend does not update the server's session-lock behavior.
- Execution uses the green ARM64 release-build artifact of
  [sudocode #916](https://github.com/sudoprivacy/sudocode/pull/916), source
  `592c7cb8`, carrying Nexus **v0.8.3**, plugin ABI 7 and the egress gate.
  SHA-256: `09049e4a43a797544afa035232e82b6dbf04b547b65d3c8f8795a6d22fb61674`.
  Installed path:
  `~/sudo-dgx/shared-assembly/cohost-592c7cb8e839/ci-release/nexusd-cohost-linux-arm64/nexusd-cohost`.
  This is a PR build of merged code, not a new numbered cohost release.
  Verified `/proc/1275447/exe` bytes at `2026-10-09T16:07:51Z` match that hash.
  A stale `ExecStart` override had kept the old binary active despite the main
  unit changing. The override was backed up and removed; execution state was
  backed up without restoring or clearing it. Evidence:
  `~/sudo-dgx/shared-assembly/cohost-592c7cb8e839/effective-upgrade-backup-20261009T160751Z/`.
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
- **Relative file tools passed with explicit model tool parameters:** real
  browser session `6ac0536e-8962-4b4c-8adf-264c68afcc52` used Write/Read/Edit/Read
  on `workspace/proof-r6-20261010.txt`. Owner-authenticated independent reads of
  both the canonical repository and the managed process alias returned the same
  15 bytes, `r6-revised-7400`. Native session: `session-1791565875461-3`;
  managed PID: `pid-e52ff500b710`. The first natural-language request chose the
  wrong filename and empty content; that remains a model task-quality failure.
  The tools correctly reported the actual missing-file error and empty write.
  Nexus v0.8.3 resolves the directory alias; #916 rejects unhandled kernel writes.
- Browser cancellation reached a terminal result, and a following question
  recalled the revised file content. Reloading the idle session retained history.
  A separate cancellation after actual text deltas arrived also reached a
  terminal result. These checks cover user cancellation and idle reconnect;
  running-process crash recovery remains open. Browser text lives in Markdown
  Shadow DOM, so acceptance reads that DOM and inspects screenshots rather than
  relying on the outer document's text alone.
  Native/path evidence:
  `~/sudo-dgx/shared-assembly/moss-workspace-context-20261010/file-r6-native-and-paths.jsonl`.
  Browser evidence on the Windows workstation:
  `%LOCALAPPDATA%/Temp/sudoedge-handoff-20261008/file-r6-explicit-browser.json`,
  `file-r6-cancel-resume-browser.json` and `file-r6-active-cancel-browser.json`.
- **Live tool output display passed after the WebUI upgrade:** the same browser
  session resumed and actually read the fixture, then a deliberately absent file.
  WebSocket results matched the rendered Output panels byte for byte. The first
  displayed `r6-revised-7400` inside the tool's file-result JSON; the second
  displayed `FileNotFound` with the failed status. Both remained visible after
  opening the tool details. The turn reached a successful terminal result.
  Managed PID for this resumed turn: `pid-54544c84d065`. This idle-session resume
  does not establish recovery of an uncertain writer. Evidence:
  `%LOCALAPPDATA%/Temp/sudoedge-handoff-20261008/file-r6-tool-output-acceptance.json`,
  `file-r6-tool-output-browser.json` and `file-r6-tool-output-browser.png`.
- Existing `proof.txt`, `uploaded.txt` and all session history remain intact.
  Older runners with dead cohost connections and `LOCK_UNCERTAIN` sessions still
  need authenticated recovery. Recovery must prove the previous writer stopped
  or is fenced before releasing its lock, and must not replay prompts. No
  uncertain lock was cleared manually. Earlier canonical-path upload/read API
  checks do not cover the browser file-picker UI.
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
10000 ms. Container `sudoedge-presidio` uses `sudo-presidio-zh:startup-e52035e`, loopback
binding, a 4 GiB cap and `restart=unless-stopped`; health returned 200.
The cloud mount is not provisioned. These settings alone do not establish
production cloud-prompt acceptance.

The **#903 cohost artifact** passed all 40 shared harness assertions
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

[sudostack #33](https://github.com/sudoprivacy/sudostack/pull/33) merged after
all five latest CI checks passed, including real analyzer tests. It fixes
organization scores being reduced to `0.34`, below the gate's default `0.5`
threshold. The old deployed analyzer missed both synthetic company names; the
corrected analyzer passes six cases covering people, companies, a location and
ordinary technical prose. The existing shared contract suite passes 139 tests.
[sudostack #34](https://github.com/sudoprivacy/sudostack/pull/34) fixes the
Gunicorn 25.1.0 worker startup deadlock found in #33's post-merge analyzer CI.
It disables the unused control socket in the shared image and tests three fresh
starts with six real recognition checks each. All five latest PR checks passed
before merge; 139 local contract tests and 18 ARM startup/recognition checks
passed. The exact final-head image is deployed; effective image ID:
`sha256:41f2043a9610d7e75291a899a8fe47dc0e7c49ee13da888d8d0e6dc6ea4e3e31`.
Its configuration hashes match commit `e52035e7bd3b978b50a5814de8d95d23e7ae6426`,
the control socket is absent, and six checks passed against the active loopback
service. This upgrade kept the memory limit and restart policy and did not
restart Moss or cohost. Deployment and rollback records:
`~/sudo-dgx/shared-assembly/ner-scores-release-16a1325-20261010/deployment.json`
and `~/sudo-dgx/shared-assembly/analyzer-startup-e52035e-20261010/deployment.json`.

An isolated test using the currently installed #916 cohost binary checked actual
OpenAI-driver wire bytes: the old analyzer forwarded a synthetic company name,
the corrected one redacted it, denial made zero requests for the blocked company,
and analyzer outage made zero cloud-fixture requests. A separately allowed
`Hello` request passed under deny policy. Local-mount bytes stayed intact.
This upstream was a controlled loopback HTTP fixture. Evidence:
`~/sudo-dgx/shared-assembly/ner-scores-20261010/wire-v2/acceptance.json`.

The 40 assertions use a small set of synthetic prompts. The test mount named
as a cloud route still reaches local Qwen; it does not call a production cloud
provider. Chinese business-text precision/recall, artifact exports, OCR and
real cross-domain agent traffic remain unaccepted. No Yige Cloud API adapter
is installed. Nexus owns the gate; the loopback Presidio service supplies
Chinese named entities, and `sudostack/security/egress-gate/` owns the shared
assembly and test contract. new-api owns model routes and token groups.

Next: finish safe session recovery, then configure the cloud-only mount with
encrypted bootstrap credentials and
verify allow/redact/deny and analyzer outage. Cross-domain A2A must enter this
box's kernel before federation to receive the gate; direct external-broker
writes bypass it. Artifact exports also need a governed route. Neither path
is accepted by the model-plane harness.

The cohost placement implementation now comes from the exact-pinned sudostack
action in `scripts/sudostack.lock.json`. The appliance wrapper supplies paths,
unit, bind address and zone only. Set `SUDOSTACK_DEPLOY_ROOT` to that checkout or
an offline source bundle containing its locked files, and supply the producer's
authenticated `SUDOEDGE_COHOST_SOURCE` (full commit) and
`SUDOEDGE_COHOST_SHA256` (executable hash). No floating download is performed.

`SUDOEDGE_DEPLOY_COMMAND=inspect` performs a read-only current-process/source
check; `stage` publishes a hash-named executable without changing a service.
The default `install` starts only a fresh unit, or reports an identical running
executable without restart. A different existing unit is refused before changes,
including an inactive one; its original paths, identity, model and policy
drop-ins require a reviewed owner-controlled drain/adoption step. Process hash
verification alone is not authenticated readiness or cross-domain join acceptance.

The real DGX execution target remains the existing Moss/cohost product runtime.
An additional standalone Agent is not a substitute for deploying that path.
Shared sequence, authentication/authorization boundaries and current missing
native contracts are documented in sudostack's
`docs/design/cohost-deploy-and-domain-join.md`. Cloud consumes the same native
contracts and shared sequence with its Kubernetes placement adapter.

Script checks: `SUDOSTACK_DEPLOY_ROOT=/pinned/stack python3 tests/cohost-install.py`, `sudo bash tests/connectivity.sh`,
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

## Shared business DLP acceptance — October 12

The shared business-policy assembly is [sudostack #37](https://github.com/sudoprivacy/sudostack/pull/37),
candidate `ea94c85047b45c380005eb970e86b2c930c3322c`. Its deployment and reproducible
acceptance commands live in `security/egress-gate/COMPOSITION.md` there. Presidio
remains upstream; customer lists and public-company exceptions are deployment
configuration loaded at analyzer startup. The tested policy is synthetic, not a
customer configuration.

On DGX, the candidate analyzer image is `sudo-presidio-zh:business-ea94c85`, image
ID `sha256:788955afbad55428d73bb87b9fbda2071ad9ae7e1ffec5e2ad23239fde9dc9e4`.
Its policy identity was
`776b61df5338bf37bbc6c6232f57302a393508722db376ac6fb585ca318f36e1`.
The test daemon was the accepted ARM64 cohost build from sudocode #916, SHA-256
`09049e4a43a797544afa035232e82b6dbf04b547b65d3c8f8795a6d22fb61674`.

The isolated test used actual mTLS VFS writes, the real Nexus gate, a recording
endpoint, production `https://api.sudorouter.ai`, and cloud `gpt-4.1-mini`.
The local control used local new-api/GPUStack `qwen3-30b`. Each accepted write
waited for a model completion. No model credential was printed or included in
captures.

| Mode | Cloud requests | Accepted behavior |
|---|---:|---|
| Redact | 5 | Customer terms and marked customer records were redacted in ordinary/escaped JSON; public company and clean requests were allowed |
| Deny | 2 | Only public-company and clean requests reached the cloud; three sensitive writes emitted zero requests |
| Analyzer unavailable | 0 | The cloud write was refused before any request |

All three modes retained the original synthetic terms on the local GPU route.
Shared Compose deployment and forced container recreation also passed policy
identity and business behavior checks. The test containers/units were stopped;
the existing WebUI, Moss, cohost and production analyzer were preserved.

Evidence is under
`~/sudo-dgx/shared-assembly/dlp-business-ea94c85-20261012/`:
`source-pins.json`, `wire-router-cloud/acceptance.json`, the synthetic wire
captures and `compose-acceptance.json`. Earlier runs also exercised a synthetic
model endpoint and the local Router/model; the final candidate above was retested
against the real cloud model after policy-file validation changed.

This proves the candidate's **model write path in isolated daemons**. It does
not establish a persistent production `/cloud-model` mount, external Router
credential recovery, a browser session selecting that cloud mount, actual A2A,
or artifact export. The existing general Chinese NER baseline remains below an
acceptable quality bar; business policy fixtures do not establish corpus recall.
Continue to use the shared public corpus evaluation plus independently annotated
business positives/negatives before admitting general DLP.

The final acceptance of both business families used the corrected credential
and visible-reply runner from [sudostack #39](https://github.com/sudoprivacy/sudostack/pull/39),
revision `4cc0cc39c327078a11f5d21092ff2d72325ddfce`. It passed the appliance Router hop:
`cohost/Nexus gate → new-api external group → production SudoRouter → gpt-4.1-mini`.
The local control used the same temporary new-api instance's `local` group and
real GPUStack/Qwen, through a node-local forwarding proxy. Configuration came
from sudoedge `62a931253bb60d974eafad142d6f118c826d8d58` (the startup-reset fix in
#12), with distinct local/external tokens and cross-group retry disabled.
Using the local token for the cloud-only model returned HTTP 400. The model
mounts used their own credentials; the recording proxy verified and forwarded
Authorization unchanged. Deliberately mounting the external credential on the
local route failed before cloud traffic. Redact, deny and analyzer-outage yielded
8, 2 and 0 cloud requests, respectively. Each allowed write produced visible
reply text. Every local control retained the original customer/contact terms
and synthetic credential. The thinking Qwen channel used the existing production
output budget of 4096; an earlier 256-token test cap produced an empty length
termination, which correctly failed the strengthened acceptance.

Fourteen analyzer fixtures cover customer/contact/contract data and internal
source/design records, with public-company, source-example and ordinary-discussion
negatives. A source credential without a classification marker is also tested on
the actual wire. The new synthetic policy identity is
`2dc2c5ae8d512ce15bb521be31de23fac1ed9e68b758fdbce17c28807cdba929`;
the analyzer image above is unchanged. Explicit classification fixtures remain
distinct from statistical recognition quality on unlabelled business content.

This used a loopback-published new-api container with `/data` on tmpfs and
its generated credential configuration in `/dev/shm`; both were cleaned up.
The existing production Router was preserved. The Router image ID was
`sha256:09e2e013908973a1eea98f059c5843f5eab5fe10a4501b10b31579faf455643d`.
Evidence: `two-tier-router-acceptance-v4.json`, `wire-two-tier-router-v4/`,
`wire-two-tier-router-miswired-v4/` and `wire-fixture-both-business-v4/` in the
same assembly directory above. Final source pins are in
`wire-both-business-families-v4/source-pins.json`; the original source pins and
earlier evidence remain immutable. Runner SHA-256:
`37d8c6b79b61a2586116de2a7c9b0050ba3b4745b4a56579460aecb3909db369`.
The audit checked 1342 owned files up to 32 MiB, excluding symlinks, and found no
literal current upstream cloud key. This is not a cold-boot credential-recovery
acceptance. The persistent browser cloud path remains the next integration step.
