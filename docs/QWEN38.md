# Qwen3.8 Flash Next on DGX Spark

## Result — October 9, 2026

One GB10 loaded and served **nvidia/Qwen3.8-Flash-Next-NVFP4**. The original
Qwen BF16 checkpoint is approximately 335 GiB and does not fit this machine.
The successful run used NVIDIA's mixed NVFP4 export, file-backed PLE embedding
offload to NVMe, an 8,192-token context and at most two running requests.

| Request | Actual result | Wall time |
| --- | --- | --- |
| Chinese arithmetic | 17 + 25 = 42 | 3.169 s |
| Follow-up relying on earlier context | 7319 + 1 = 7320 | 3.365 s |
| OpenAI tool call | `get_weather({"city":"北京"})`, `finish_reason=tool_calls` | 4.125 s |

All three requests returned HTTP 200. Weight loading took 549.5 seconds;
startup took approximately ten minutes. The runtime reported 81.5 GB model
memory and 18.26 GB KV allocation. Minimum host `MemAvailable` was 13.19 GiB.
These are short functional checks; long-context quality, sustained concurrency,
MTP and overnight stability have not been accepted.

## Pinned inputs

- Checkpoint: `nvidia/Qwen3.8-Flash-Next-NVFP4`, revision
  `fc694b54fb0174e0913e6adf86691ef85a4ead47`.
- Downloaded checkpoint: 132,734,505,212 bytes; all 11 safetensor shards checked
  against the official SHA-256 values.
- Runtime: `lmsysorg/sglang:dev-qwen38-next-local`, ARM64 manifest
  `sha256:a1e17bbf0e9618364dc6395a4de5f9c3e8dfc9f43d603995b7a6aebc83de6e06`.
  Image config:
  `sha256:cdd9649ba1cf472344fd1e11e7cbaa7161a0624329b522931646537cc1c15701`.
- Official setup: [SGLang Qwen3.8 Flash Next cookbook](https://docs.sglang.io/cookbook/autoregressive/Qwen/Qwen3.8-Flash-Next).

## Reproduce

Pause the existing model through the GPUStack API by saving its model spec and
setting `replicas=0`. Wait for its model instance and GPU process to stop.
Keep the previous spec for restoration. Run one resident model at a time.

Set `CHECKPOINT`, `PLE_DIR` and `KERNEL_CACHE` to absolute paths on local NVMe.
The accepted launch used a new, empty PLE directory:

```bash
docker run --name qwen38-acceptance --network host --gpus all \
  --memory 110g --memory-swap 110g --shm-size 2g --ulimit memlock=-1 \
  -v "$CHECKPOINT:/model:ro" -v "$PLE_DIR:/ple" \
  -v "$KERNEL_CACHE:/root/.cache" \
  -e SGLANG_QWEN4_PLE_FILE_RSS_BUDGET_GB=8 \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e HF_HUB_OFFLINE=1 \
  lmsysorg/sglang:dev-qwen38-next-local \
  python3 -m sglang.launch_server \
  --model-path /model --host 127.0.0.1 --port 30938 \
  --served-model-name Qwen3.8-Flash-Next \
  --tp 1 --moe-runner-backend flashinfer_cutlass \
  --ple-offload-embedding --ple-offload-backend file --ple-offload-dir /ple \
  --mem-fraction-static .85 --context-length 8192 --max-running-requests 2 \
  --max-mamba-cache-size 10 --chunked-prefill-size 2048 \
  --reasoning-parser auto --tool-call-parser auto
```

Let the runtime select `modelopt_mixed` from the checkpoint; do not override
`--quantization`. The model emits reasoning, so include those tokens in the
output budget. The acceptance run also sampled host memory every two seconds
and would stop only its own experiment container below 8 GiB available.

Check `/v1/models`, then make a fresh `/v1/chat/completions` request. Test a
follow-up with the earlier messages and a tool schema, rather than treating
the model catalog as inference acceptance.

Stop the experiment before restoring GPUStack's saved model spec. On this
machine the original Qwen3 model returned to `running` and answered through
the Sudowork WebUI after restoration. Qwen3.8 is currently stopped and has
not been made the default Router model.

## Evidence on the box

`/home/taolei/sudo-dgx/experiments/qwen38-flash-next-20261008/` contains:

- `checkpoint-ready.json`: checkpoint revision and verified files.
- `launch.json`: exact container arguments and image identity.
- `memory-samples.jsonl`: host memory observations.
- `inference-results.json` and `inference-summary.json`: real responses and timings.
- `gpustack-replicas-before.json`: private model specs needed for restoration.

Keep the checkpoint, cache and evidence for repeat runs. Do not publish model
specs or credentials from the private deployment directory.
