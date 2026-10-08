# DGX Spark — sudo stack runbook

> SSH in? Read this first. Canonical box configuration lives here.
> **Architecture & rationale**: the design doc on ShareOne
> (`s.shareone.vip/s/sudo-stack-on-dgx-spark-she`). This runbook holds only
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

## Browser bring-up — 2026-10-02

- Browser: **http://localhost:12808** on the Windows laptop, forwarded over SSH
  to DGX loopback port 26808. `scripts/open-webui.ps1` installs the current-user
  `SudoEdge-WebUI-12808` scheduled task with sign-in startup and automatic SSH
  reconnect. The original temporary tunnel had exited; this caused the user's
  unreachable page. Killing the replacement SSH child and rechecking HTTP
  proved automatic recovery. Windows sign-out/reboot has not been tested.
  Password-agent entry: **SudoEdge DGX WebUI**, username `admin`.
- Deployment root: `~/sudo-dgx/bringup`. Local Moss dev `1925bbc` plus the
  WebSocket first-message fix uses mTLS to the primary Nexus on 22140 (vault
  and login) and a separate local mTLS identity to the cohost execution Nexus
  on 22141. With `MOSS_DEFAULT_RUNTIME=cohost`, browser sessions use
  `Moss → ManagedAgentService → in-process scode → Nexus /model → new-api →
  GPUStack`; no per-session scode process is launched. The primary and
  execution Nexus services are deliberately separate so the cohost acceptance
  can be restarted without interrupting Moss authentication.
- Sudowork base: `0c8a5bb9` plus the changes in the companion worktree
  `test/edge-webui-bringup`: server execution labels, artifact history schema,
  and removal of empty virtual chat rows. Image: `sudoedge-webui:edge-label`.
- Local model: Qwen3-30B-A3B-Thinking-2507-FP8, vLLM 0.22.1,
  context 65536, output limit 4096, GPU memory utilization 0.60,
  `--tool-call-parser hermes --reasoning-parser qwen3`. Router publishes these
  limits; `scode-with-catalog.py` supplies them explicitly to the released ACP
  runtime before its first request. This is a deployment compatibility fix.
- Service startup: user units `sudoedge-nexus` and `sudoedge-moss`, with user
  lingering enabled; WebUI/Postgres restart through Docker. The system
  `sudoedge-reconfigure` drop-in points at `bringup/edge/scripts` and refreshes
  the local Moss Router key using `sync-moss-router.py`. Whole-box cold boot
  has not been tested. The cloud Router key still requires provisioning after
  RAM-backed Router state is recreated.
- Operations: `sudoedge status`, `sudoedge webui status`, and
  `sudo sudoedge connectivity local|online`; current mode is
  `online`. The actual host and a Docker bridge container were unable to
  connect to the public cloud in local mode. LAN browser access and model
  inference continued; restarting the connectivity service retained local
  mode. IPv4/IPv6 behavior also passed the isolated namespace test. The
  installed entry point is `/usr/local/bin/sudoedge`; `sudoedge.service`
  restores its saved mode at boot.
- Qwen first-message fix, October 2: session
  `38c1af4f-fe66-4d86-aa29-9eb3c631557a` never received its first prompt.
  Moss completed the WebSocket handshake before attaching the runner and
  installing its message handler. The fix attaches the runner first. A real
  Node WebSocket regression failed before the fix and passed afterward;
  all six process lifecycle tests pass. Changed-file lint passes and the
  server typecheck remains at its existing 104-error baseline. The deployed
  fix returned `qwen3-30b` in browser session
  `deddc1f6-01a2-4be6-ac1b-cc5b09c67c69`. Fresh browser login and opening
  that conversation from the sidebar also restored both messages visibly.
  The original empty session is
  terminated and was not restored by this new-session check.
- Acceptance session: `78eb44be-6275-47e4-abce-482c6fb2e4de`. First browser
  turn created a CSV and a result file with total 50. Follow-up turns exposed
  model mistakes: a missing newline, then a stale result file despite claims
  that it had been updated. Natural-language multi-turn task reliability has
  **not passed**; file parsing is the acceptance check. A final explicit `awk`
  command sent through the browser agent updated the file to 60, verified by
  independently parsing the four CSV rows and reading the result file. This
  confirms tool execution, while leaving autonomous task quality unresolved.
  Session files remain under
  `moss-home/server/runtime/sessions/<id>/workspace` for inspection.
- Cloud production audit, October 2 evening (historical): Moss 0.1.46 and
  gVisor pods used `moss-runtime:scode-0.2.21-handoff` with separate scode
  processes, while cluster Nexus was 0.7.19. That audit predated the local
  mailbox migration recorded below; changing a runtime image alone was never
  sufficient.
- The current **Sudo SaaS Demo (腾讯云 moss-server)** password-agent entry
  successfully logs into cloud Moss through the DGX WebUI. Session
  `0be68ba5-05ce-4028-9cc2-3cde7c73c137` created and read `cloud-check.txt`,
  returning `CLOUD_OK_20261002`; reopening the browser restored the result.
  This validates the current cloud session path, before cohost migration.
- The shared session migration is actively owned by the Codex conversation
  in `nexus-codex` (`01a0f7f7-63e8-7fd3-948f-98e7ef3121b3`, active October 2,
  22:33 CST). Its worktrees include `moss-codex`,
  `sudocode-codex-session-mailbox` and `sudowork-codex-session-mailbox`.
  Its scope covers both hosts, streaming, tools, approvals, cancellation and
  recovery. Sudocode PR #849 and nexus-vfs PR #377 separately cover durable
  cohost resume. Coordinate deployment against those results.
- Model mount acceptance: ARM64 cohost built from sudocode mailbox support
  (nexus-vfs **0.8.0**, `nexusd-cohost` release binary) runs on loopback
  **22141** with separate data
  under `bringup/cohost-model-validation`. The existing browser Nexus on
  22140 remained unchanged. ManagedAgentService started embedded session
  `pid-e5a7915b14cf` (`os_pid: null`). Its Qwen config contains only
  `nexus:///model`; the mount owns the Router credential and uses backend
  `openai`, base URL `http://127.0.0.1:3000/v1`. The real agent replied through
  `send`, then read a VFS fixture and wrote
  `/agents/edge-model-agent/acceptance/result.json`. An independent read
  asserted `{"batch":"EDGE-20261002","total":96}` (7 * 13 + 5).
  Six completed model exchanges were observed in `/model/*.prompt` and
  `.reply`, using `chat/completions`, model `qwen3-30b` and real tool calls.
  This passes the embedded local model/file path. A fresh Moss browser session
  `9fd73394-f9f4-44eb-a89d-01dc73e3bfd1` then selected
  `runtime.type=cohost`, sent a WebSocket prompt, and returned
  `COHOST_MODEL_OK` with `result.status=success` and 8,473 input / 253 output
  tokens. The same turn produced a `POST /v1/chat/completions` entry in the
  `sudoedge-sudorouter-1` new-api log (model `qwen3-30b`, 7 seconds), proving
  the browser path reaches the local Router and GPUStack through `/model`.
  A second session `37de752c-20fc-4646-a04b-96009b9e0e0e` omitted the runtime
  field entirely; the persisted default `MOSS_DEFAULT_RUNTIME=cohost` selected
  the same path and returned `DEFAULT_COHOST_OK` with `result.status=success`.
  Browser cancellation/reconnect and policy deny/redact checks remain separate
  acceptance.
  Cancellation returned `cancelled: true`.
  On October 3, `sudoedge-cohost-model.service` made the 22141 acceptance
  runtime persistent, with an `ExecStartPost` hook that reattaches `/model`
  over mTLS. Restarting the service automatically restored the route; new
  embedded session `pid-96bddeeb6923` returned
  `EDGE_MODEL_RESTART_OK qwen3-30b` at 08:14 CST through new-api.
  `sudoedge-reconfigure.service` also refreshes the mount after provisioning
  Router credentials. This is appliance provisioning; generic Nexus mount
  replication/replay remains a component concern. The cohost service is
  installed by `scripts/install-cohost.sh`; Moss must point its cohost Nexus
  variables at 22141 and set `MOSS_DEFAULT_RUNTIME=cohost`.
  Whole-machine cold boot is still untested.

Next: complete browser multi-turn/cancel/reconnect acceptance; consume the
shared session migration for cloud and Edge and repeat the browser tasks;
verify whole-box cold boot and cloud credential recovery. Real agent A2A
and DLP follow these basic paths.

Script checks: `sudo bash tests/connectivity.sh`,
`python3 tests/model-config.py` and `python3 tests/router-config.py`.
Keep all generated credentials outside git.

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
  cloud channel in `default`. Channel base URL defaults to
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
