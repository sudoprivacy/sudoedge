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
- Each model gets a **model-route** to be exposed on the gateway: `POST /v2/model-routes` (name → target `model_id`). If `/v1-openai/models` is empty for a running model, create its route.
- Model `backend_parameters`:
  - `--enable-auto-tool-choice --tool-call-parser hermes` (hermes = Qwen family) so `tool_choice:auto` is served.
  - `--gpu-memory-utilization <f>` sizes the KV cache against unified memory; choose per model so weights + KV fit with OS headroom.
  - `--max-model-len <N>` bounds context.
  - New `backend_parameters` take effect after `DELETE /v2/model-instances/{id}` (the scheduler recreates the instance from the spec).

## sudocode → local model
`~/.nexus/sudocode/sudocode.json` uses `api-key` auth with two providers (nova-gateway, gpustack) and two models:
- `qwen3-local` → nova-gateway (through the local router) — primary
- `qwen3-direct` → gpustack (`http://127.0.0.1/v1-openai`) — direct
Run from a project directory (scode wants a scoped cwd; else `--allow-broad-cwd`):
`scode --auth api-key --model qwen3-local "<prompt>"` → full agent loop incl. tool calls.
Model limits live in `<config_home>/cache/model-capabilities.json` = `{"models":{"<model>":{"context_window":N,"max_output_tokens":M}}}` (sudocode otherwise assumes `max_tokens=64000`).

## nova-gateway — local sudorouter
Fork of **New API** (one-api family: Go + React + SQLite), container `sudorouter:latest` (arm64). Single local endpoint that aggregates the local gpustack channel and the cloud channel. Architecture: design doc §5.
- **Build**: source at `~/nova-gateway`; `docker build -t sudorouter:latest .` (base images node/golang/alpine staged from the docker.1ms.run mirror + retagged; the Dockerfile uses goproxy.cn and registry.npmmirror.com).
- **Run** (single container; SQLite, host network):
  ```
  docker run -d --name sudorouter --network=host --restart=always \
    -e GENERATE_DEFAULT_TOKEN=true -e TZ=Asia/Shanghai -e ERROR_LOG_ENABLED=true \
    -e TEE_ADDR="" -e TEE_KEY="<b64 EC key>" -e TEE_UID="0" \
    -v ~/nova-gateway-data:/data sudorouter:latest
  ```
  - `TEE_KEY` is a DER-base64 EC key (`openssl ecparam -name prime256v1 -genkey -noout -outform DER | base64 -w0`); the TEE path (Sudo channel type 52 → sudorouter.ai) parses it at startup.
  - Data (SQLite) lives in `~/nova-gateway-data` (RAM-backed for credential hygiene; see the design doc §7).
- **Admin** `http://127.0.0.1:3000`, `root` / pw in `~/sudo-dgx/nova-gateway-admin-pw.txt` (fork seeds `root/sudosudo` via InitRootUser).
  - Admin API auth: session cookie **plus** header `New-Api-User: 1`.
  - `SelfUseModeEnabled` is on, so local models serve without per-model pricing.
  - Channel `gpustack-local`: type 8 (Custom), base_url `http://127.0.0.1/v1-openai/chat/completions`, models `qwen3-30b`, key = gpustack key. AddChannel body is wrapped: `{"mode":"single","channel":{...}}`.
- **Clients** use the OpenAI endpoint `:3000/v1` with the relay token in `~/sudo-dgx/nova-gateway-token.txt`.
- **Cloud channel** (`sudorouter.ai`, `https://hk.sudorouter.ai/v1`): an OpenAI-compatible channel injected at deploy time; the key stays off persistent disk.

## Memory safety (unified-memory machine)
One physical pool (RAM = GPU = 121 GiB): a served model's weights + KV cache + preprocessing all draw from it. Guardrails keep the box remotely recoverable and turn an over-allocation into a cheap clean kill.
- cgroup **MemoryMin** reservations persist across reboot: `system.slice=12G`, `ssh.service=512M` → SSH and the OS stay responsive under memory pressure (verify: `systemctl show -p MemoryMin ssh.service`).
- systemd service **`sudo-mem-guard`** (root, `OOMScoreAdjust=-900`, `Restart=always`, enabled): `/usr/local/bin/sudo-mem-guard.sh`, log `/var/log/sudo-mem-guard.log`.
  1. Caps each vLLM container cgroup `memory.max = RAM−14G` (~108G), re-applied to the ephemeral `/system.slice/docker-*.scope` (defense-in-depth for host-side allocations).
  2. Tripwire: when system `MemAvailable` stays below 6G for ~15s, reclaims the largest vLLM process. This covers GPU/unified allocations (which are charged outside per-cgroup accounting), making the tripwire the effective backstop.
  Tuned to act only at genuine near-OOM (a clean kill), well above any single sane model.
- Operate: `systemctl status sudo-mem-guard`; `sudo tail -f /var/log/sudo-mem-guard.log`. If the guard and gpustack cycle (kill → restart → kill), set that model's `replicas=0` via the gpustack API and resize.
- Sizing: one resident model at a time (others on disk); size by **peak** (weights + KV + preprocessing) with OS headroom.
