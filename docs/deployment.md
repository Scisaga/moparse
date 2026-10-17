# Deployment

The parser listens on port `12303`. Its image is CPU-only and uses Python 3.13
CPU wheels for PyTorch. Docling runs CPU inference in the parser; GLM GPU inference
runs in its separate model service.

## Prerequisites

- Docker Engine with Compose v2 (the current Compose specification is used).
- At least 8 GiB RAM for normal Docling conversion; complex/large PDFs may need
  more.
- Internet access on first use, or prefetched Docling artifacts.
- NVIDIA Container Toolkit for the bundled GPU service in the `glm` / `glm-sdk` profiles.

Copy configuration before changing defaults:

```bash
cp .env.example .env
```

Never place production secrets in a committed `.env` file.

On networks that require an outbound proxy, set `HTTP_PROXY` and
`HTTPS_PROXY`; Compose passes them to the parser and GLM model containers for
first-run model downloads. Keep internal service names in `NO_PROXY`. Document
source downloads and GLM API clients deliberately use `trust_env=False`,
so an ambient proxy cannot bypass their SSRF/backend routing controls.

## Mode 1: CPU parser only

This is the default and works for digital-native PDF/Office content without GLM.
Office embedded images are extracted directly; native PDF image assets depend on model
detection and cropping. These assets do not require OCR. Standalone image/video parsing
and optional asset text recognition require GLM-OCR. For PDFs containing scanned/mixed
pages without GLM, use `scan_policy=skip` to retain those pages as whole-page images:

```bash
docker compose up -d --build mosaicparse
docker compose ps
curl --fail http://127.0.0.1:12303/health
curl --fail http://127.0.0.1:12303/ready
```

Keep `GLM_OCR_ENABLED=0`. The first conversion may download
Docling 2.139.0 layout/table models to the persistent `docling-models` volume. The PDF
backend is PyPdfium, with TableFormer V1 Accurate and `DOCLING_DO_CELL_MATCHING=0`. Parser
health checks have a ten-minute startup grace period for that download and CPU
initialization. `DOCLING_COMPILE_MODELS=0` avoids a very slow first document
caused by `torch.compile`; enable it only after workload-specific benchmarking
and a controlled warm-up.

The parser first classifies source pages and sends native pages to Docling and scanned/mixed
pages to the SDK. `DOCLING_PAGE_WORKERS` can split Docling's selected native page set across
persistent converters when that set is one contiguous range, reaches
`DOCLING_PAGE_PARALLEL_MIN_PAGES`, and each page has sufficient native text. Discontinuous
native ranges are converted sequentially; SDK page requests are also submitted sequentially.
A PDF containing both kinds is therefore routed by page, not kept wholly on one converter.
Each converter uses `DOCLING_NUM_THREADS` CPU threads and loads during startup, not per request.
The product of `PARSER_WORKERS` and `DOCLING_PAGE_WORKERS` is capped at 32 because
each slot owns model state. A measured 12-core allocation can start with 3 page
workers and 4 threads per worker; re-benchmark on the target NUMA topology.

The service uses `DOCLING_LOCAL_ARTIFACTS_PATH=/models/docling` so its setting
does not collide with Docling's own `DOCLING_ARTIFACTS_PATH` environment
variable. Do not set the upstream variable to a fresh empty volume: upstream
interprets it as an offline artifact directory and disables automatic download.

The main image includes FFmpeg and FFprobe. Standalone video defaults are 200 MiB,
30 minutes, at most 24 keyframes, 7680×4320 source frames, two FFmpeg threads and
one concurrent FFmpeg process. Tune `VIDEO_MAX_FRAME_PIXELS`, `FFMPEG_THREADS`,
`FFMPEG_MAX_CONCURRENCY`, and `FFMPEG_TIMEOUT_SECONDS` only with matching container
CPU/memory limits and workload tests.

For offline hosts, prefetch on a connected machine and transfer the artifacts:

```bash
uv run python scripts/download_docling_models.py --output-dir models/docling
```

When using a bind mount instead of the named volume, mount that directory at
`/models/docling` and set `DOCLING_MODEL_DOWNLOAD=0` after verifying it.

## Mode 2: Parser plus bundled GLM-OCR on GPU 1

The repository pins the model server to `vllm/vllm-openai:v0.19.1`.
This patch release includes the Transformers 5 support required by GLM-OCR,
and its standard x86_64 image retains the `sm_75` kernels needed by RTX 20xx
GPUs. The `v0.19.0-ubuntu2404` variant omits `sm_75` and is therefore not a
safe default for the reference RTX 2080 Ti. `.env.example` defaults
`GLM_GPU_DEVICE_ID=1`.

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

The host binds GLM to `127.0.0.1:8001` by default, while the parser calls the
Compose-internal URL `http://glm-ocr:8000/v1/chat/completions`. GPU reservation
is explicit; the two GPUs are not treated as a shared memory pool. Set
`GLM_OCR_BIND_ADDRESS` deliberately if another host must reach the model API;
do not expose an unauthenticated vLLM endpoint to an untrusted network.

Before production use, verify the selected GPU and memory allocation:

```bash
nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv
docker inspect docling_glm_ocr --format '{{json .HostConfig.DeviceRequests}}'
curl --fail http://127.0.0.1:8001/health
```

The Compose default `GLM_GPU_MEMORY_UTILIZATION=0.40` was validated for a
single-concurrency workload on the 22 GiB development GPU. Increase it only
when higher concurrent context capacity is required and the GPU is dedicated to
this service. GPU 1 in the reference host is an RTX 2080 Ti (Turing), which
cannot execute BF16; the Compose baseline therefore passes
`--dtype half` for FP16. Change `GLM_DTYPE` only after verifying the target GPU.
`GLM_OCR_MAX_TOKENS` is the response budget and must remain below
`GLM_MAX_MODEL_LEN` so the image and prompt still fit in the context window.
OCR uses the fixed `Text Recognition:` prompt required by GLM-OCR; it is not a
configurable prose prompt.
Model-server startup includes a potentially large Hugging Face download and has
a five-minute health-check grace period.

## Mode 3: Bundled official GLM-OCR SDK page pipeline

The `glm-sdk` profile starts the same GPU model service plus a CPU-only SDK
sidecar for PP-DocLayoutV3 and region orchestration:

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

`scan_policy=auto` uses Docling for native-text pages and the SDK for scanned/mixed pages.
`GLM_SDK_ORIENTATION_ENABLED=1` rotates the SDK input upright before PP-DocLayoutV3
layout detection and regional GLM-OCR recognition. `GLM_SDK_RENDER_SCALE=2.7777777777777777`
renders at 200 DPI before orientation, within `GLM_SDK_MAX_IMAGE_PIXELS=8000000`; larger
images are downscaled to that budget. DPI is part of the tested pipeline configuration, not
a promise of higher accuracy for every PDF. Structure validation retains uncertain
cells and warnings rather than inventing missing text, periods, or numbers.

The SDK sidecar loads the pinned package's layout/task/queue defaults and overrides only local
self-hosting, OCR connection, CPU layout device, and listen settings. It reuses
`http://glm-ocr:8000` and must not receive a GPU reservation. The parser is also CPU-only.
The original page association is retained when oriented coordinates return to the page.

Direction preprocessing runs in the parser with the official PP-LCNet document-orientation
weights through CPU PyTorch/Transformers. `GLM_SDK_ORIENTATION_MODEL_PATH` points to
`/models/huggingface/PP-LCNet_x1_0_doc_ori_safetensors`; prefetch these weights and retain
their model revision and SHA when preparing an offline deployment. Paddle is not required.
`GLM_SDK_ENABLED=1` is effective only when `GLM_OCR_ENABLED=1`; the CPU-only default
does not contact an OCR service.

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
docker compose up -d --build mosaicparse
curl --fail http://127.0.0.1:12303/v1/backends
```

Image and video frame text recognition reuse `GLM_OCR_*` request limits. The public
`describe_images` parameter remains available, but its output is limited to visible text.
Video summaries list recognized text with sampled-frame timestamps and do not infer scenes.

Container DNS must resolve those hostnames. On Linux, `host.docker.internal` may require an
explicit `extra_hosts` entry. Use TLS and protected network paths when backends cross a trust boundary.

## Source checkout without Docker

```bash
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
DATA_DIR=./data STATIC_DIR=frontend/dist GLM_OCR_ENABLED=0 \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 12303
```

Python must be `>=3.13,<3.14`. The committed lock uses official CPU PyTorch
wheels; it does not install CUDA libraries into the parser environment.

## Data, upgrades, and cleanup

The current API was updated on 2026-10-17 at **17:46:28.801462 Beijing time**, using
`mosaic-parse:0.4.0-header-context-20261017-r3`, image
`sha256:f815766b71ed67229f995d864ca146ef68937a98012676316bc33c4a673405db`.
This revision strengthens source-caption, complete unit-declaration and inter-table context checks.
Its 53 application files match the accepted image; 329 backend tests passed and the
OpenAPI JSON is unchanged. The SDK still runs
`sha256:abe353926afba82931744bac4533f895c9e6ad6f768da4103a4ec40410c2e6cb`.
Only the API was replaced at 17:46; the SDK and GLM provider kept their existing instances.
The model configuration remains PyPdfium, V1 Accurate, matching off, 200 DPI SDK input,
and orientation on. Readiness and all three configured backends passed. The
[current deployment readback](../benchmark-results/clean-model-comparison-20261015/followup/20261017/selected-pipeline-deployment/independent-recheck-20261017T170704/unit-r3-production-deployment.json)
records the actual container, image, source hashes and configuration; use this revision
when restoring the current service.

The earlier **05:15** release used API image
`sha256:f9639d65ec922a1c300233e3ef5711af5a0d3de3b6b8d7909b9ea1776575e89a`.
That version completed all 10 PDFs / 502 pages through HTTP before deployment;
after its deployment, 3 PDFs / 59 pages were parsed again on the production endpoint.
Financial headers, funding-cell bindings and the matching-header continuation passed their
specified checks; all 30 source-page images and 32 downloaded assets passed pixel/SHA
verification. The previous 10 Markdown results and 195 assets retained their hashes.
Its 502-page scores, timing and original release manifest remain an immutable snapshot;
they are not a new full-cohort model run for a later API revision. The intermediate
**17:32 r2** image `sha256:dcf627bafa52f4786564ab1dcf9abdc3f05b18398d5829ed5e83300f8ea848ef`
has separate 316-test and 35-page production records; these do not count as r3 verification.
r3 also fixes a counterexample where two declarations, such as centimeters followed by meters,
were reduced to their last value. It retains all declarations and blocks ambiguous/empty values
within a declared unit dimension, while allowing repeated equal declarations and ordinary
continuation pages with no new declaration.

The r3 candidate completed the two original PDFs / 31 pages through HTTP. After the
17:46 r3 deployment, the production API independently completed those 31 pages again
through asynchronous Jobs, plus 4 pages through the synchronous
`/v1/content/parse` endpoint. Financial acceptance was 30/30, funding cells 31/31 with
7/7 row bindings, and continuation checks 33/33 with 10/10 header leaves; the direct
source comparison retained all 44 funding-grid positions, seven merged spans and
55 continuation-body positions. Both source-page images passed RGB verification and all
four assets passed SHA/size checks. The 31-page Markdown capture took 45.118937 seconds;
the extra synchronous response took 8.160285 seconds and matched the persisted and asynchronous
Markdown byte for byte. The
[r3 post-deployment direct comparison](../benchmark-results/clean-model-comparison-20261015/followup/20261017/selected-pipeline-deployment/independent-recheck-20261017T170704/production-unit-r3-http/direct-source-recheck.json)
and [r3 synchronous result readback](../benchmark-results/clean-model-comparison-20261015/followup/20261017/selected-pipeline-deployment/independent-recheck-20261017T170704/production-unit-r3-synchronous/summary.json)
record this new 35-page validation. The
[current release manifest](../benchmark-results/clean-model-comparison-20261015/followup/20261017/selected-pipeline-deployment/independent-recheck-20261017T170704/release-manifest.json)
links the final source/image identity and evidence. A missing closing parenthesis in the diluted-EPS
label remains a model-output defect; numerical acceptance does not establish exact label text.
These limits, the numerical and native-image cropping issues, and the additional checks are in the
[complete comparison and deployment evidence](../benchmark-results/clean-model-comparison-20261015/report.md).

Compose uses named volumes `mosaicparse-data`, `docling-models`, and
`huggingface-cache`. Do not use `docker compose down -v` unless deleting jobs,
results, and model caches is intentional.

0.4.0 intentionally does not convert older Job results. For the breaking upgrade,
stop the main service and run the guarded purge command with the exact confirmation
string. It deletes Job rows, inputs, results, media, keyframes, bundles and legacy
`jobs.sqlite3`, while preserving the current `jobs.db` schema and model volumes:

```bash
docker compose stop mosaicparse
docker run --rm --network mosaicparse_default \
  -v mosaicparse-data:/data \
  ghcr.io/scisaga/mosaic-parse:0.4.0 \
  python /app/scripts/purge_job_data.py \
  --health-url http://mosaicparse:12303/health \
  --data-dir /data \
  --confirm PURGE_MOSAICPARSE_JOBS_0_4_0
```

The command rejects a running service, root/relative/symlink targets and an incorrect
confirmation string, reports deletion counts, and can be rerun idempotently. This
upgrade has no Job backup or data rollback; back up the data volume yourself before
running it if that is required by your deployment policy.

Expired jobs can be removed through the protected admin API:

```bash
ADMIN_TOKEN='replace-me' uv run python scripts/cleanup_jobs.py
```

Use `/health` for liveness. Use `/ready` for traffic admission; readiness may be
false while storage or a backend required by the active default route is not
usable. `/v1/backends` reports individual backend capability.

## MCP reverse-proxy allowlist

MCP 2.x validates the request Host and browser Origin to mitigate DNS rebinding.
Defaults allow only localhost and the Compose-internal MosaicParse name. When exposing
`/mcp` through a domain, add its exact `host[:port]` to `MCP_ALLOWED_HOSTS` and
the exact scheme/host/port Origin to `MCP_ALLOWED_ORIGINS`, for example:

```dotenv
MCP_ALLOWED_HOSTS=localhost,127.0.0.1,[::1],mosaicparse,docs.example.com
MCP_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1,https://docs.example.com
```

Do not use `*` as the default. Preserve and validate the original Host header in
the reverse proxy configuration.
