# Deployment

The public API listens on `12303`. The API image uses Python 3.13 and CPU PyTorch; it is never given a GPU. The separate Python 3.12 native worker uses ONNX/CPU and contains no Torch. MinerU visual inference and GLM-OCR run in separate GPU services.

The deployment recipes include MinerU Advanced + TXT and standalone Docling. Configuration examples describe how to start these services; actual image identities, resource limits and model revisions must be read from the target installation. The concise configuration reference is [runtime recipes](runtime-recipes.md). Performance experiment design belongs in the independent [MinerU tuning plan](../benchmark/mineru-tuning.md).

## Final output and implementation status

The [final semantic output contract](output-contract.md) requires every table and every PDF flowchart and organizational chart to become source-backed descriptions, preferably nested lists. Physical page numbers, headers, footers and pagination/debug markers are removed from the final extraction text. Intermediate Markdown, HTML, XML region definitions and source grids remain permitted; they do not define the final public format.

The existing table semantics is incomplete: it still retains some GFM tables and page furniture, and image text recognition does not recover diagram relations. Neither a deployment recipe, a semantic feature flag nor readiness proves this final contract has passed. The [runtime recipes](runtime-recipes.md#实现与部署状态) preserve the earlier table-conversion deployment evidence; the [final contract](output-contract.md#9-当前实现差距与迁移) identifies the remaining implementation work. This documentation update changes no runtime configuration and starts no inference or deployment.

## Prerequisites

- Docker Engine with Compose v2 (the current Compose specification is used).
- At least 8 GiB RAM for normal Docling conversion; complex/large PDFs may need
more.
- Internet access on first use, or prefetched Docling artifacts.
- NVIDIA Container Toolkit for the model services used by the `mineru`, `glm` and
`glm-sdk` profiles. The SDK sidecar itself is CPU-only.
- For Advanced＋TXT, space for the pinned 3.19 GB model files and the separate images;
the vLLM image is about 22.6 GB unpacked on the reference build.

Copy configuration before changing defaults:

```bash
cp .env.example .env
docker network create moparse_backend
```

Compose declares `moparse_backend` as an **external** network. Create it once before starting any profile; if it exists, reuse it. All profiles use this network, including CPU-only mode. Never place production secrets in a committed `.env` file.

On networks that require an outbound proxy, set `HTTP_PROXY` and `HTTPS_PROXY`; Compose passes them to the parser and GLM model containers for first-run model downloads. Keep internal service names in `NO_PROXY`. Document source downloads and GLM API clients deliberately use `trust_env=False`, so an ambient proxy cannot bypass their SSRF/backend routing controls.

## Mode 1: Standalone CPU Docling baseline

Set `NATIVE_PARSER_BACKEND=docling` and `GLM_OCR_ENABLED=0`. This is the conservative fresh-install default and works for digital-native PDF/Office content without GLM. Office embedded images are extracted directly; native PDF image assets depend on model detection and cropping. These assets do not require OCR. Standalone image/video parsing and optional asset text recognition require GLM-OCR. For PDFs containing scanned/mixed pages without GLM, use `scan_policy=skip` to retain those pages as whole-page images:

```bash
docker compose up -d --build moparse
docker compose ps
curl --fail http://127.0.0.1:12303/health
curl --fail http://127.0.0.1:12303/ready
```

Keep `GLM_OCR_ENABLED=0`. The first conversion may download Docling 2.139.0 layout/table models to the persistent `docling-models` volume. The PDF backend is PyPdfium, with TableFormer V1 Accurate and `DOCLING_DO_CELL_MATCHING=0`. Parser health checks have a ten-minute startup grace period for that download and CPU initialization. `DOCLING_COMPILE_MODELS=0` keeps this CPU Docling configuration from invoking `torch.compile`.

The parser first classifies source pages and sends native pages to Docling and scanned/mixed pages to the SDK. `DOCLING_PAGE_WORKERS` can split Docling's selected native page set across persistent converters when that set is one contiguous range, reaches `DOCLING_PAGE_PARALLEL_MIN_PAGES`, and each page has sufficient native text. Discontinuous native ranges are converted sequentially; SDK page requests are also submitted sequentially. A PDF containing both kinds is therefore routed by page, not kept wholly on one converter. Each converter uses `DOCLING_NUM_THREADS` CPU threads and loads during startup, not per request. The product of `PARSER_WORKERS` and `DOCLING_PAGE_WORKERS` is capped at 32 because each slot owns model state. Configure converters and threads within the installation's combined CPU and memory limits.

The service uses `DOCLING_LOCAL_ARTIFACTS_PATH=/models/docling` so its setting does not collide with Docling's own `DOCLING_ARTIFACTS_PATH` environment variable. Do not set the upstream variable to a fresh empty volume: upstream interprets it as an offline artifact directory and disables automatic download.

The main image includes FFmpeg and FFprobe. Standalone video defaults are 200 MiB, 30 minutes, at most 24 keyframes, 7680×4320 source frames, two FFmpeg threads and one concurrent FFmpeg process. Tune `VIDEO_MAX_FRAME_PIXELS`, `FFMPEG_THREADS`, `FFMPEG_MAX_CONCURRENCY`, and `FFMPEG_TIMEOUT_SECONDS` only with matching container CPU/memory limits and workload tests.

For offline hosts, prefetch on a connected machine and transfer the artifacts:

```bash
uv run python scripts/download_docling_models.py --output-dir models/docling
```

When using a bind mount instead of the named volume, mount that directory at `/models/docling` and set `DOCLING_MODEL_DOWNLOAD=0` after verifying it.

## Mode 2: Parser plus bundled GLM-OCR on GPU 1

The repository pins the model server to `vllm/vllm-openai:v0.19.1`. This patch release includes the Transformers 5 support required by GLM-OCR, and its standard x86_64 image retains the `sm_75` kernels needed by RTX 20xx GPUs. The `v0.19.0-ubuntu2404` variant omits `sm_75` and is therefore not a safe default for the reference RTX 2080 Ti. `.env.example` defaults `GLM_GPU_DEVICE_ID=1`.

Set:

```dotenv
GLM_OCR_ENABLED=1
GLM_GPU_DEVICE_ID=1
GLM_DTYPE=half
GLM_OCR_MAX_TOKENS=4096
```

Then start the optional profile:

```bash
docker compose --profile glm up -d --build
docker compose --profile glm ps
docker compose logs -f glm-ocr
```

The host binds GLM to `127.0.0.1:8001` by default, while the parser calls the Compose-internal URL `http://glm-ocr:8000/v1/chat/completions`. GPU reservation is explicit; the two GPUs are not treated as a shared memory pool. Set `GLM_OCR_BIND_ADDRESS` deliberately if another host must reach the model API; do not expose an unauthenticated vLLM endpoint to an untrusted network.

Before production use, verify the selected GPU and memory allocation:

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv
docker inspect docling_glm_ocr --format '{{json .HostConfig.DeviceRequests}}'
curl --fail http://127.0.0.1:8001/health
```

The Compose default is `GLM_GPU_MEMORY_UTILIZATION=0.40`; check total model, cache and graph memory against the target GPU and other resident services before changing it. The reference RTX 2080 Ti uses FP16 because it cannot execute BF16. Change `GLM_DTYPE` only after verifying the target GPU. `GLM_OCR_MAX_TOKENS` is the response budget and must remain below `GLM_MAX_MODEL_LEN` so the image and prompt still fit in the context window. OCR uses the fixed `Text Recognition:` prompt required by GLM-OCR; it is not a configurable prose prompt. Model-server startup includes a potentially large Hugging Face download and has a five-minute health-check grace period.

## Mode 3: Bundled official GLM-OCR SDK page pipeline

The `glm-sdk` profile starts the same GPU model service plus a CPU-only SDK sidecar for PP-DocLayoutV3 and region orchestration:

```dotenv
DOCLING_PDF_BACKEND=pypdfium
DOCLING_TABLE_MODE=accurate
DOCLING_DO_CELL_MATCHING=0
GLM_OCR_ENABLED=1
GLM_SDK_ENABLED=1
GLM_SDK_ORIENTATION_ENABLED=1
# 200 DPI = scale 200/72; preserve the tested SDK input resolution.
GLM_SDK_RENDER_SCALE=2.7777777777777777
GLM_SDK_MAX_IMAGE_PIXELS=8000000
```

```bash
docker compose --profile glm-sdk up -d --build
docker compose --profile glm-sdk ps
docker compose logs -f glm-ocr-sdk
```

`scan_policy=auto` uses the configured native backend for native-text pages and the SDK for scanned/mixed pages. Modes 1–4 use Docling unless explicitly switched to MinerU. `GLM_SDK_ORIENTATION_ENABLED=1` rotates the SDK input upright before PP-DocLayoutV3 layout detection and regional GLM-OCR recognition. `GLM_SDK_RENDER_SCALE=2.7777777777777777` renders at 200 DPI before orientation, within `GLM_SDK_MAX_IMAGE_PIXELS=8000000`; larger images are downscaled to that budget. DPI is part of the tested pipeline configuration, not a promise of higher accuracy for every PDF. Structure validation retains uncertain cells and warnings rather than inventing missing text, periods, or numbers.

The SDK sidecar loads the pinned package's layout/task/queue defaults and overrides only local self-hosting, OCR connection, CPU layout device, and listen settings. It reuses `http://glm-ocr:8000` and must not receive a GPU reservation. The parser is also CPU-only. The original page association is retained when oriented coordinates return to the page.

Direction preprocessing runs in the parser with the official PP-LCNet document-orientation weights through CPU PyTorch/Transformers. `GLM_SDK_ORIENTATION_MODEL_PATH` points to `/models/huggingface/PP-LCNet_x1_0_doc_ori_safetensors`; prefetch these weights and retain their model revision and SHA when preparing an offline deployment. Paddle is not required. `GLM_SDK_ENABLED=1` is effective only when `GLM_OCR_ENABLED=1`; the CPU-only default does not contact an OCR service.

## Mode 4: Remote GLM-OCR and SDK

Do not enable the bundled profile. Point the parser at services reachable from its container:

```dotenv
GLM_OCR_ENABLED=1
GLM_OCR_API_URL=http://gpu-host.example:8000/v1/chat/completions
GLM_OCR_MODEL=zai-org/GLM-OCR
GLM_SDK_ENABLED=1
GLM_SDK_URL=http://sdk-host.example:5002/glmocr/parse
GLM_SDK_ORIENTATION_ENABLED=1
# 200 DPI = scale 200/72; preserve the tested SDK input resolution.
GLM_SDK_RENDER_SCALE=2.7777777777777777
GLM_SDK_MAX_IMAGE_PIXELS=8000000
```

```bash
docker compose up -d --build moparse
curl --fail http://127.0.0.1:12303/v1/backends
```

Image and video frame text recognition reuse `GLM_OCR_*` request limits. The public `describe_images` parameter remains available, but its output is limited to visible text. Video summaries list recognized text with sampled-frame timestamps and do not infer scenes.

Container DNS must resolve those hostnames. On Linux, `host.docker.internal` may require an explicit `extra_hosts` entry. Use TLS and protected network paths when backends cross a trust boundary.

## Mode 5: Advanced + TXT with GPU concurrency 4

This recipe combines MinerU 4.0.12 Advanced + TXT and `mineru-vl-utils==2.0.7` for native pages with GLM-OCR + SDK at 200 DPI and CPU orientation for scanned and mixed pages. Client concurrency and vLLM `max_num_seqs` are both 4. TXT uses PDF source text for body blocks; Advanced table structure and cell text still come from GPU visual recognition. The existing API assembles partial semantic lists, retained GFM, source mappings, jobs and assets; complete final semantic conversion remains pending. The MinerU framework version is separate from the pinned MinerU2.5-Pro model revision below.

| Image | Dockerfile | Role |
|---|---|---|
| `ghcr.io/scisaga/moparse:0.5.0` | `Dockerfile` | Public API, source routing and current Markdown; CPU |
| `ghcr.io/scisaga/moparse-native-worker:0.5.0` | `Dockerfile.native-worker` | PDF text/geometry, ONNX small models; CPU, no Torch |
| `ghcr.io/scisaga/moparse-mineru-vllm:0.5.0` | `Dockerfile.mineru-vllm` | FP16 visual layout/table model; GPU |

Image overrides are `MOPARSE_IMAGE`, `MINERU_NATIVE_IMAGE` and `MINERU_VLLM_IMAGE`. Select an available registry image by digest or build all required images from the intended source commit. Record the actual image IDs rather than inferring compatibility or quality from a tag.

### Prepare and verify locked models

[`native_worker/models.lock.json`](../native_worker/models.lock.json) fixes two repositories and 25 ordinary files, totaling 3,186,232,095 bytes (3.19 GB):

- `opendatalab/MinerU2.5-Pro-2605-1.2B`, revision
`08aaea840498d49ce16247b6263196cf02814885`;
- `opendatalab/MinerU-4_models_onnx`, revision
`358310b4f64b95f9fefc372ad899356e4111f376`.

The lock records each file's size/SHA and upstream licensing evidence. The helper [`scripts/download_mineru_models.py`](../scripts/download_mineru_models.py) is copied to `/worker/scripts/` in the CPU worker image. It prepares ordinary offline files, without symlinks back to a Hub cache, and checks bytes before installation.

```bash
docker compose --profile mineru build mineru-native mineru-vllm
docker volume create moparse-mineru-models
docker volume create moparse-mineru-small-models
docker run --rm --entrypoint python \
  -v moparse-mineru-models:/models/mineru \
  -v moparse-mineru-small-models:/models/mineru-native \
  ghcr.io/scisaga/moparse-native-worker:0.5.0 \
  /worker/scripts/download_mineru_models.py \
  --vlm-dir /models/mineru --native-home /models/mineru-native
```

If `MINERU_NATIVE_IMAGE` points to a local build, use that exact image instead of the GHCR name. Pass download credentials/proxy environment explicitly when required; the preparation container has no GPU. Transfer these two volumes for offline hosts, then verify with no network and read-only mounts:

```bash
docker run --rm --network none --entrypoint python \
  -v moparse-mineru-models:/models/mineru:ro \
  -v moparse-mineru-small-models:/models/mineru-native:ro \
  ghcr.io/scisaga/moparse-native-worker:0.5.0 \
  /worker/scripts/download_mineru_models.py \
  --vlm-dir /models/mineru --native-home /models/mineru-native --verify-only
```

`--verify-only` uses the standard library and does not load models. The runtime mounts both model volumes read-only; `/models/mineru-native/models/.locks` needs a separate writable tmpfs because the upstream model reader uses file locks. The runtime uses a 4-MiB tmpfs at that path; a read-only model hash check alone does not verify this runtime write requirement.

Run path and dependency preflight inside the actual execution image with its intended mounts, user and network. A matching host-side SHA does not establish that a PDF, model or symlink target is visible inside the container. Check the final target and lock-directory writability without loading models or issuing inference requests. If input files live outside a mount, explicitly expose them read-only or copy the exact bytes into an accessible input directory and verify their hashes.

The worker build applies the reviewed native-writing-axis dependency fix and verifies MinerU 4.0.12 plus patched source SHA `616f44e2a1749f4b82074df36c3da852694a9401828c6c36aad62553b2a182cf`. A different source/version fails validation. This fixes character ownership from source geometry; it does not supply document-specific words or numbers.

### Configure and start

The repository software version is 0.5.1. The versioned image names below are local build examples; build the selected source and read back the resulting image digest. Registry image availability and deployment acceptance must be checked on the target installation. See [runtime recipes](runtime-recipes.md) for the maintained configuration summary.

Set `.env`:

```dotenv
COMPOSE_PROJECT_NAME=moparse
MOPARSE_IMAGE=moparse:0.5.1-semantic-v1-20261019
MINERU_NATIVE_IMAGE=moparse-native-worker:0.5.1-request-control-20261019
# Reference host migration: retain the existing API network aliases.
COMPOSE_FILE=/opt/moparse/docker-compose.yml:/opt/moparse/docker-compose.compat.yml
NATIVE_PARSER_BACKEND=mineru
MINERU_NATIVE_BASE_URL=http://mineru-native:8010
MINERU_NATIVE_TIMEOUT_SECONDS=7200
CONTENT_TIMEOUT_SECONDS=7200
MINERU_GPU_DEVICE_ID=1
GLM_OCR_ENABLED=1
GLM_SDK_ENABLED=1
GLM_SDK_ORIENTATION_ENABLED=1
GLM_SDK_RENDER_SCALE=2.7777777777777777
GLM_SDK_MAX_IMAGE_PIXELS=8000000
```

```bash
docker compose --profile mineru --profile glm-sdk up -d --build
curl --fail http://127.0.0.1:12303/ready
curl --fail http://127.0.0.1:12303/v1/backends
```

Before replacement, compare the resolved Compose project, physical network and volume names, existing container labels and selected image identity. Preserve writable layers and restore specifications, keep private environment data outside the repository, and read back the resulting image, source hashes, mounts, readiness and ordinary Compose dry-run. On the migrated reference host, use the maintained [base recipe](../docker-compose.yml) plus [network compatibility file](../docker-compose.compat.yml); the latter retains API aliases without overriding the image. New installations can use the base file alone.

The native worker calls `http://mineru-vllm:8000`; host-only diagnostic bindings are `127.0.0.1:12431` (vLLM) and `127.0.0.1:12432` (native worker). The selected GPU model uses FP16, `max_num_seqs=4`, `max_model_len=8192`, an explicit 128-MiB KV budget, `max_num_batched_tokens=2048`, `MinerULogitsProcessor`, and the decode-only CUDA Graphs configuration below with capture sizes 1 through 4. The native SDK client also limits model requests to 4. `gpu_memory_utilization=0.16` is not a hard limit on total GPU memory when an explicit KV budget is supplied. Read the selected GPU's free memory and existing services before starting another resident model.

Main API, native worker and GLM SDK receive no GPU device reservation. The two model services default to GPU 1; their memory is shared with other applications on that card, not pooled across two cards. The native worker has an **8-CPU/8-GiB** limit and the VLM server a **4-CPU/20-GiB** limit in Compose; these are quotas, not exclusive pinned cores. The reference host's two GPU power limits are **200 W** each; read back both configured and enforced limits, the selected device UUID, and other resident processes in every deployment or performance record.

The base recipe sets client concurrency 4, ORT intra 8/inter 1, window size 8, CPU formula microbatch 1 and malloc trim. OMP/OpenBLAS/MKL remain at 4. Native worker and VLM quotas are not exclusive pinned cores. Runtime parameters are summarized in [runtime recipes](runtime-recipes.md); independent performance experiments are defined in the [MinerU tuning plan](../benchmark/mineru-tuning.md).

### Required CUDA Graphs configuration and evidence

Enable CUDA Graphs on supported GPU inference backends within their allocated resources. The MinerU recipe keeps `torch.compile` disabled and enables decode-only graphs with capture sizes 1 through 4:

```text
--compilation-config '{"mode":0,"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[1,2,3,4],"max_cudagraph_capture_size":4}'
--cudagraph-metrics
```

The ordinary command must not include `--enforce-eager`. Compilation and graph execution are separate settings: `mode=0` disables compilation, while `FULL_DECODE_ONLY` enables full decode graph replay. Keep these explicit flags rather than relying on framework defaults.

During deployment, inspect the resolved container command, effective graph mode and capture sizes, successful capture logs, and actual request-time replay such as nonzero `Runtime Mode=FULL` counts. A health/ready response, configuration label, or capture log alone does not prove replay. Check total model-process resident memory against the available GPU budget; capture-reported graph memory is only part of that total.

Disable graphs only for an explicitly named eager control or a demonstrated execution failure, memory-budget violation or output regression, with a condition for re-enabling them. Keep new backend support trials bounded and do not silently fall back.

Concurrency, thread and graph experiments belong in the [MinerU tuning plan](../benchmark/mineru-tuning.md).

### Source evidence and request control

The 2026-10-19 [deployment record](runtime-recipes.md#实现与部署状态) includes removal of independent Docling header and source-conflict verification after MinerU. It does not establish acceptance of the newer full semantic contract. Read actual image and model identities before describing a current deployment; this documentation-only audit does not run inference or replace services. Direct PDF grid, glyph, text and span correspondence can supply source-backed table metadata; incomplete evidence keeps physical tables separate and preserves unknown structure. Parser disagreement is not used to certify values or replace table content in the target implementation.

SDK malformed-region isolation and acknowledged native cancellation remain active. SDK cleanup owns the original HTTP operation until return, but the SDK exposes no verified remote cancellation or idempotency acknowledgement. Unresolved source regions and failed pages retain their partial or unknown status and original assets.

To select the standalone CPU Docling backend, set `NATIVE_PARSER_BACKEND=docling`; scanned/mixed GLM settings can remain the same. The public request contract and persisted results do not depend on this backend setting. See [runtime recipes](runtime-recipes.md) for deployment configuration.

### Reuse already-running GLM/SDK services during migration

A fresh deployment uses the profiles above. For an existing installation whose GLM and SDK containers are already healthy, they can join the new network with aliases without a restart. Inspect network membership first; connect only missing members:

```bash
docker network inspect moparse_backend
docker network connect --alias glm-ocr moparse_backend docling_glm_ocr
docker network connect --alias glm-ocr-sdk moparse_backend docling_glm_ocr_sdk
docker compose --profile mineru up -d mineru-vllm mineru-native
```

Back up SQLite/storage and record old job/result/asset hashes; verify no queued or running jobs before replacing the old API. Stop the recorded old API container (named `mosaicparse` in the pre-rename reference deployment), then recreate only the API:

```bash
docker compose --profile mineru up -d --no-deps --build moparse
```

`--no-deps` here is a migration choice that keeps the existing GLM/SDK instances; it is not required for a fresh installation. Retain the original physical data and model volumes, verify readiness and backend identities, re-read old jobs/assets, and perform the accepted full-PDF HTTP checks again. Neither `/health` nor a configuration label alone establishes quality or the actual deployed model revision.

## Source checkout without Docker

```bash
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
DATA_DIR=./data STATIC_DIR=frontend/dist NATIVE_PARSER_BACKEND=docling \
  GLM_OCR_ENABLED=0 \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 12303
```

Python must be `>=3.13,<3.14`. The committed lock uses official CPU PyTorch wheels; it does not install CUDA libraries into the parser environment.

## Project rename compatibility

The project and Compose application are named `moparse` from 2026-10-18. The source repository is <https://github.com/Scisaga/moparse>, and new images use `ghcr.io/scisaga/moparse`. `MOPARSE_IMAGE` takes precedence; the previous `MOSAICPARSE_IMAGE` variable remains supported during migration. Python imports continue to use `app`.

The physical job/data and model volume names are intentionally unchanged. Existing SQLite jobs, results and assets require no schema conversion or purge for this rename. Before moving an existing installation, record its resolved volumes with `docker compose config`, stop its old API, and connect the renamed API to those same physical volumes. Use `/opt/moparse` as the reference checkout path, update `origin` to `https://github.com/Scisaga/moparse.git`, and update service or bind-mount references to the actual new path. During migration retain `/opt/mosaic-parse` as a compatibility symlink and verify both paths resolve to the same checkout. Verify old result and asset hashes and readiness before admitting new traffic.

HTTP routes, job IDs, Markdown media type and authenticated asset URLs are unchanged by the rename. Rename compatibility does not freeze final content as GFM; the final semantic contract governs future output conversion. MCP resources are now `moparse://health`, `moparse://backends` and `moparse://usage`; the corresponding `mosaicparse://` resource URIs remain aliases. Browser API keys and parse options saved under the previous name are read during migration.

## Deployment acceptance

After deployment, read back the actual API image, model revision, runtime limits, mounts and backend readiness. Submit a complete source PDF with its input SHA; poll a 202 response through the same persistent job, then inspect final Markdown, assets and statuses. Readiness, transport completion and content quality are separate outcomes. Use the [evaluation tasks](../benchmark/evaluation-tasks.md) to define content checks; this deployment guide does not certify a build's content accuracy. Preserve complete source tables internally when continuation is uncertain. Target acceptance must separately verify every table and required diagram relation, nested-list output, page-furniture removal and preservation of business notes, signatures and dates; a retained source table is not complete final semantic conversion.

## Data, upgrades, and cleanup

Compose volume keys `mosaicparse-data`, `docling-models`, and `huggingface-cache` map to the existing physical volumes `mosaicparse-data`, `${DOCLING_MODELS_VOLUME:-mosaicparse-docling-models}`, and `mosaicparse-huggingface-cache`. Do not use `docker compose down -v` unless deleting jobs, results, and model caches is intentional.

Expired jobs can be removed through the protected admin API:

```bash
ADMIN_TOKEN='replace-me' uv run python scripts/cleanup_jobs.py
```

Use `/health` for liveness. Use `/ready` for traffic admission; readiness may be false while storage or a backend required by the active default route is not usable. `/v1/backends` reports individual backend capability.

## MCP reverse-proxy allowlist

MCP 2.x validates the request Host and browser Origin to mitigate DNS rebinding. Defaults allow only localhost and the Compose-internal moparse name (and the legacy mosaicparse name). When exposing `/mcp` through a domain, add its exact `host[:port]` to `MCP_ALLOWED_HOSTS` and the exact scheme/host/port Origin to `MCP_ALLOWED_ORIGINS`, for example:

```dotenv
MCP_ALLOWED_HOSTS=localhost,127.0.0.1,[::1],moparse,mosaicparse,docs.example.com
MCP_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1,https://docs.example.com
```

Do not use `*` as the default. Preserve and validate the original Host header in the reverse proxy configuration.

## Recoverable backups and Compose membership

Stopping or renaming a Compose container retains its project/service labels, so ordinary `up` can still select that backup. Preserve writable layers, actual named and anonymous volume bindings, and private restore specifications before removing an explicitly owned stopped container. Verify detached backup labels and an ordinary no-op dry-run. Raw environment and restore payloads belong in root-only storage outside this repository. Do not delete volumes as part of an application replacement.
