# Deployment

The public API listens on `12303`. The API image uses Python 3.13 and CPU PyTorch;
it is never given a GPU. The separate Python 3.12 native worker uses ONNX/CPU and
contains no Torch. MinerU visual inference and GLM-OCR run in separate GPU services.

The deployable recipes are Advanced＋TXT with Docling header/source verification and
the standalone Docling baseline. The comparison also retains earlier candidates. A recipe
is not a deployment observation. The single current comparison is
[benchmark/report.md](../benchmark/report.md); its release proof identifies any
`live_selected` method, actual image/model hashes and post-deployment acceptance.
The examples below prepare a configuration; they do not assert that a candidate has
already been promoted.

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

Compose declares `moparse_backend` as an **external** network. Create it once before
starting any profile; if it exists, reuse it. All profiles use this network, including
CPU-only mode. Never place production secrets in a committed `.env` file.

On networks that require an outbound proxy, set `HTTP_PROXY` and
`HTTPS_PROXY`; Compose passes them to the parser and GLM model containers for
first-run model downloads. Keep internal service names in `NO_PROXY`. Document
source downloads and GLM API clients deliberately use `trust_env=False`,
so an ambient proxy cannot bypass their SSRF/backend routing controls.

## Mode 1: Standalone CPU Docling baseline

Set `NATIVE_PARSER_BACKEND=docling`, `MINERU_HEADER_VERIFIER=off`,
`MINERU_SOURCE_VERIFIER=off` and
`GLM_OCR_ENABLED=0`. This is the conservative fresh-install default and works for
digital-native PDF/Office content without GLM.
Office embedded images are extracted directly; native PDF image assets depend on model
detection and cropping. These assets do not require OCR. Standalone image/video parsing
and optional asset text recognition require GLM-OCR. For PDFs containing scanned/mixed
pages without GLM, use `scan_policy=skip` to retain those pages as whole-page images:

```bash
docker compose up -d --build moparse
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

`scan_policy=auto` uses the configured native backend for native-text pages and the
SDK for scanned/mixed pages. Modes 1–4 use Docling unless explicitly switched to MinerU.
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
docker compose up -d --build moparse
curl --fail http://127.0.0.1:12303/v1/backends
```

Image and video frame text recognition reuse `GLM_OCR_*` request limits. The public
`describe_images` parameter remains available, but its output is limited to visible text.
Video summaries list recognized text with sampled-frame timestamps and do not infer scenes.

Container DNS must resolve those hostnames. On Linux, `host.docker.internal` may require an
explicit `extra_hosts` entry. Use TLS and protected network paths when backends cross a trust boundary.

## Mode 5: Advanced＋TXT with GPU concurrency 2

This is the primary candidate, not an implicit production promotion. It combines
MinerU 4.0.12 Advanced＋TXT and `mineru-vl-utils==2.0.7` for native pages with the
existing GLM-OCR＋SDK/200-DPI/CPU-orientation path for scanned and mixed pages.
TXT uses PDF source text for body blocks; Advanced table structure and cell text
still come from GPU visual recognition. TXT does not make all page text source-derived.
The API assembles public GFM, source mappings, jobs and assets.

| Image | Dockerfile | Role |
|---|---|---|
| `ghcr.io/scisaga/moparse:0.5.0` | `Dockerfile` | Public API, source routing and GFM; CPU |
| `ghcr.io/scisaga/moparse-native-worker:0.5.0` | `Dockerfile.native-worker` | PDF text/geometry, ONNX small models; CPU, no Torch |
| `ghcr.io/scisaga/moparse-mineru-vllm:0.5.0` | `Dockerfile.mineru-vllm` | FP16 visual layout/table model; GPU |

Image overrides are `MOPARSE_IMAGE`, `MINERU_NATIVE_IMAGE` and `MINERU_VLLM_IMAGE`.
Use published version/SHA tags or build from the accepted source. CI publishes the
main image first, then both dependent images from the same verified commit; hosted
import checks do not claim GPU model inference.

### Prepare and verify locked models

[`native_worker/models.lock.json`](../native_worker/models.lock.json) fixes two
repositories and 25 ordinary files, totaling 3,186,232,095 bytes (3.19 GB):

- `opendatalab/MinerU2.5-Pro-2605-1.2B`, revision
  `08aaea840498d49ce16247b6263196cf02814885`;
- `opendatalab/MinerU-4_models_onnx`, revision
  `358310b4f64b95f9fefc372ad899356e4111f376`.

The lock records each file's size/SHA and upstream licensing evidence. The helper
[`scripts/download_mineru_models.py`](../scripts/download_mineru_models.py) is copied
to `/worker/scripts/` in the CPU worker image. It prepares ordinary offline files,
without symlinks back to a Hub cache, and checks bytes before installation.

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

If `MINERU_NATIVE_IMAGE` points to a local build, use that exact image instead of the
GHCR name. Pass download credentials/proxy environment explicitly when required;
the preparation container has no GPU. Transfer these two volumes for offline hosts,
then verify with no network and read-only mounts:

```bash
docker run --rm --network none --entrypoint python \
  -v moparse-mineru-models:/models/mineru:ro \
  -v moparse-mineru-small-models:/models/mineru-native:ro \
  ghcr.io/scisaga/moparse-native-worker:0.5.0 \
  /worker/scripts/download_mineru_models.py \
  --vlm-dir /models/mineru --native-home /models/mineru-native --verify-only
```

`--verify-only` uses the standard library and does not load models. The runtime
mounts both model volumes read-only; only `/models/mineru-native/models/.locks` is a
small writable tmpfs because the upstream model reader uses file locks.

The worker build applies the reviewed native-writing-axis dependency fix and verifies
MinerU 4.0.12 plus patched source SHA
`616f44e2a1749f4b82074df36c3da852694a9401828c6c36aad62553b2a182cf`.
A different source/version fails validation. This fixes character ownership from
source geometry; it does not supply document-specific words or numbers.

### Configure and start

Set `.env`:

```dotenv
NATIVE_PARSER_BACKEND=mineru
MINERU_NATIVE_BASE_URL=http://mineru-native:8010
MINERU_NATIVE_TIMEOUT_SECONDS=7200
CONTENT_TIMEOUT_SECONDS=7200
MINERU_HEADER_VERIFIER=docling
MINERU_SOURCE_VERIFIER=docling
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

The native worker calls `http://mineru-vllm:8000`; host-only diagnostic bindings are
`127.0.0.1:12431` (vLLM) and `127.0.0.1:12432` (native worker). The GPU model uses
FP16, `max_num_seqs=2`, `max_model_len=8192`, an explicit 128-MiB KV budget,
`max_num_batched_tokens=2048`, eager execution and `MinerULogitsProcessor`. The SDK
client also limits requests to 2. `gpu_memory_utilization=0.16` is not a hard limit
on total GPU memory when an explicit KV budget is supplied. Read the selected GPU's
free memory and existing services before starting another resident model.

Main API, native worker and GLM SDK receive no GPU device reservation. The two model
services default to GPU 1; their memory is shared with other applications on that card,
not pooled across two cards. CPU worker limits are 4 cores/8 GiB in Compose.

### Docling header and source verification

`MINERU_HEADER_VERIFIER=docling` is a separate candidate requiring its own complete
HTTP acceptance before promotion. It requires `NATIVE_PARSER_BACKEND=mineru` and the
CPU Docling models. Docling evaluates only cross-page candidates: complete header
bands, source spans, unique geometric correspondence, column boundaries, caption/unit
and surrounding context must agree on both sides before verified roles can transfer.
It does not replace any MinerU body text or cell values. Unproven or conflicting roles
remain unknown; complete printed headers and typed furniture remain visible.
The ordinary cross-page merge guards and `table-source` row mappings still apply.

`MINERU_SOURCE_VERIFIER=docling` additionally requires the header verifier above. On
native MinerU pages, source-witnessed letter/number occurrence conflicts trigger an
independent Docling region-type check. When the model table conflicts with a source
picture and there is no overlapping independent table candidate, the API preserves
the exact source region as an image plus PDF literal text, marked `structure: unknown`.
Original model HTML, glyphs and verification reasons remain in job-private logs and
are not included in public asset manifests or bundles. This catches some unsupported
generation; a character budget does not establish complete or correct recognition.

Such source preservation leaves the actual job `partial`. A benchmark may separately
record successful HTTP/result/asset capture, but must preserve that status and the
unresolved structure. Accept it only after validating the original glyphs, text bytes,
source image, page coverage and every partial reason; unrelated warnings or failed
units do not qualify. Existing fixed source scores remain separate.

To return to the standalone baseline, set `NATIVE_PARSER_BACKEND=docling` and
both `MINERU_HEADER_VERIFIER=off` and `MINERU_SOURCE_VERIFIER=off`; scanned/mixed GLM
settings can remain the same. The
public request contract and persisted results do not depend on this backend setting.

### Reuse already-running GLM/SDK services during migration

A fresh deployment uses the profiles above. For an existing installation whose GLM
and SDK containers are already healthy, they can join the new network with aliases
without a restart. Inspect network membership first; connect only missing members:

```bash
docker network inspect moparse_backend
docker network connect --alias glm-ocr moparse_backend docling_glm_ocr
docker network connect --alias glm-ocr-sdk moparse_backend docling_glm_ocr_sdk
docker compose --profile mineru up -d mineru-vllm mineru-native
```

Back up SQLite/storage and record old job/result/asset hashes; verify no queued or
running jobs before replacing the old API. Stop the recorded old API container (named
`mosaicparse` in the pre-rename reference deployment), then recreate only the API:

```bash
docker compose --profile mineru up -d --no-deps --build moparse
```

`--no-deps` here is a migration choice that keeps the existing GLM/SDK instances;
it is not required for a fresh installation. Retain the original physical data and
model volumes, verify readiness and backend identities, re-read old jobs/assets, and
perform the accepted full-PDF HTTP checks again. Neither `/health` nor a configuration
label alone establishes quality or the actual deployed model revision.

## Source checkout without Docker

```bash
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
DATA_DIR=./data STATIC_DIR=frontend/dist NATIVE_PARSER_BACKEND=docling \
  MINERU_HEADER_VERIFIER=off MINERU_SOURCE_VERIFIER=off GLM_OCR_ENABLED=0 \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 12303
```

Python must be `>=3.13,<3.14`. The committed lock uses official CPU PyTorch
wheels; it does not install CUDA libraries into the parser environment.

## Project rename compatibility

The project and Compose application are named `moparse` from 2026-10-18. The source
repository is <https://github.com/Scisaga/moparse>, and new images use
`ghcr.io/scisaga/moparse`. `MOPARSE_IMAGE` takes precedence; the previous
`MOSAICPARSE_IMAGE` variable remains supported during migration. Python imports
continue to use `app`.

The physical job/data and model volume names are intentionally unchanged. Existing
SQLite jobs, results and assets require no schema conversion or purge for this rename.
Before moving an existing installation, record its resolved volumes with
`docker compose config`, stop its old API, and connect the renamed API to those same
physical volumes. Use `/opt/moparse` as the reference checkout path, update `origin`
to `https://github.com/Scisaga/moparse.git`, and update service or bind-mount references
to the actual new path. During migration retain `/opt/mosaic-parse` as a compatibility
symlink and verify both paths resolve to the same checkout. Verify old result and asset
hashes and readiness before admitting new traffic. Leave frozen experiment manifests
and their historical source paths unchanged.

HTTP routes, job IDs, GFM output and authenticated asset URLs are unchanged. MCP
resources are now `moparse://health`, `moparse://backends` and `moparse://usage`;
the corresponding `mosaicparse://` resource URIs remain aliases. Browser API keys
and parse options saved under the previous name are read during migration. The old
`PURGE_MOSAICPARSE_JOBS_0_4_0` confirmation below is a retained safety token for the
separate historical breaking upgrade; it is not part of project rename deployment.

## Release acceptance and live selection

The current report is [benchmark/report.md](../benchmark/report.md). The registered
main corpus contains 14 complete inputs/543 pages: 504 regression pages plus a
39-page cohort with 36 source-reviewed assertions. After its first failed IRS run,
that cohort is a development retest. A separate three-document, seven-page addendum
has 28 source-reviewed assertions, sealed before either method processed it. The
recognition recipe was frozen before those outputs; the final adapter revision
followed the baseline output and changed source-comment ordering using an earlier
regression document. The report retains both exposure boundaries. Unannotated
content is not assumed correct. Reuse of historical outputs preserves
its original pipeline, hardware/power and timing boundary.

Promotion to `live_selected` requires complete HTTP requests (`scan_policy=auto`,
no `unit_range`), final and persisted GFM, source/header/span/unit and `table-source`
checks, old-data integrity, actual code/image/model identities, resource measurements
and a deployment readback. A 202 response is polled to the same job's final result;
component FULL Markdown and a successful health check do not substitute for this.
Keep request/result hashes, method fingerprint, model lock and release proof together.
The report links that proof; this document does not hardcode a candidate as live.

<details>
<summary>Archived deployment observations from 2026-10-17</summary>

The accepted API snapshot was updated on **2026-10-17 at 21:51 Beijing time**, using
`mosaic-parse:0.4.0-source-content-20261017-r2`, image
`sha256:07a5df326885a6f83cf48aab766f6dd47fad5175066703fe6fa224380d86f9d4`.
This revision keeps visible native furniture and attached business notes in source order.
It preserves the existing header/unit/context guards and source-row mapping; it does not
change Docling, TableFormer, PyPdfium, GLM weights, SDK input or orientation settings.
OpenAPI JSON and all 53 accepted source-file hashes were checked against the running API.
Only the API was recreated; the SDK and GLM instances remained running, and all 314 old
output/asset files retained their hashes. Private environment and SQLite backups are kept
outside the repository. See the [archived deployment readback](../benchmark-results/clean-model-comparison-20261015/followup/20261017/content-preservation-mineru/production-deployment.json).

Before this release, 10 complete PDFs / 502 pages plus the exact two-page Eventrail input
completed through the candidate HTTP API. The fixed scores remain 209/209 core values,
209/209 periods, 372/402 value/unique-row checks, 326/402 public-structure header checks,
and 31/31 funding cells. The 502-page Markdown capture took 22.50 minutes; 79 assets
and all 69 routed source-page RGB images passed verification. The image passed 352 backend
tests. After deployment, fresh jobs for the two-page input and original 4/27-page cases
completed again: securities identity, financial headers, funding cells and row sources passed.
The 36/134-page native PDFs were then rerun in full, bringing post-deployment HTTP validation
to 203 pages; the policy note was recovered while the five remaining 134-page issue classes
stayed open, as recorded in the then-current report.
The [archived detailed report](../benchmark-results/clean-model-comparison-20261015/report.md#正文遗漏与替代管线实测2026-10-17)
separates export recovery from remaining upstream recognition errors and model-component trials.
One extra continuation is now conservatively split because adjacent page counters have
inconsistent source classifications; source cells and pages remain present. Remaining native
long-cell, superscript, sideways-table and picture-classification defects are disclosed there.

The previous API was updated on 2026-10-17 at **17:46:28.801462 Beijing time**, using
`mosaic-parse:0.4.0-header-context-20261017-r3`, image
`sha256:f815766b71ed67229f995d864ca146ef68937a98012676316bc33c4a673405db`.
This revision strengthens source-caption, complete unit-declaration and inter-table context checks.
Its 53 application files match the accepted image; 329 backend tests passed and the
OpenAPI JSON is unchanged. The SDK still runs
`sha256:abe353926afba82931744bac4533f895c9e6ad6f768da4103a4ec40410c2e6cb`.
Only the API was replaced at 17:46; the SDK and GLM provider kept their existing instances.
The model configuration remains PyPdfium, V1 Accurate, matching off, 200 DPI SDK input,
and orientation on. Readiness and all three configured backends passed. The
[r3 deployment readback](../benchmark-results/clean-model-comparison-20261015/followup/20261017/selected-pipeline-deployment/independent-recheck-20261017T170704/unit-r3-production-deployment.json)
records the actual container, image, source hashes and configuration; use this revision
when investigating that historical revision.

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
[r3 release manifest](../benchmark-results/clean-model-comparison-20261015/followup/20261017/selected-pipeline-deployment/independent-recheck-20261017T170704/release-manifest.json)
links the final source/image identity and evidence. A missing closing parenthesis in the diluted-EPS
label remains a model-output defect; numerical acceptance does not establish exact label text.
These limits, the numerical and native-image cropping issues, and the additional checks are in the
[complete comparison and deployment evidence](../benchmark-results/clean-model-comparison-20261015/report.md).

</details>

## Data, upgrades, and cleanup

Compose volume keys `mosaicparse-data`, `docling-models`, and `huggingface-cache`
map to the existing physical volumes `mosaicparse-data`,
`${DOCLING_MODELS_VOLUME:-mosaicparse-docling-models}`, and
`mosaicparse-huggingface-cache`. Do not use `docker compose down -v` unless deleting jobs,
results, and model caches is intentional.

### Historical 0.4.0 purge

This destructive operation belongs only to the earlier breaking 0.4.0 upgrade.
Project rename and the compatible 0.5.0 backend change preserve existing jobs and do
not require a purge. The example requires an available 0.4.0 archival image.

0.4.0 intentionally does not convert older Job results. For that breaking upgrade,
stop the main service and run the guarded purge command with the exact confirmation
string. It deletes Job rows, inputs, results, media, keyframes, bundles and legacy
`jobs.sqlite3`, while preserving the current `jobs.db` schema and model volumes:

```bash
docker compose stop moparse
docker run --rm --network moparse_backend \
  -v mosaicparse-data:/data \
  "${MOPARSE_ARCHIVED_040_IMAGE:?Set an available archived 0.4.0 image}" \
  python /app/scripts/purge_job_data.py \
  --health-url http://moparse:12303/health \
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
Defaults allow only localhost and the Compose-internal moparse name (and the legacy mosaicparse name). When exposing
`/mcp` through a domain, add its exact `host[:port]` to `MCP_ALLOWED_HOSTS` and
the exact scheme/host/port Origin to `MCP_ALLOWED_ORIGINS`, for example:

```dotenv
MCP_ALLOWED_HOSTS=localhost,127.0.0.1,[::1],moparse,mosaicparse,docs.example.com
MCP_ALLOWED_ORIGINS=http://localhost,http://127.0.0.1,https://docs.example.com
```

Do not use `*` as the default. Preserve and validate the original Host header in
the reverse proxy configuration.
