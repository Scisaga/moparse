# MO-Parse 运行手册

本手册集中说明仓库现有服务的配置、模型准备、启动和维护。配置依据为 [Compose](../../docker-compose.yml)、[环境变量示例](../../.env.example)、[应用设置](../../app/config.py)和各 Dockerfile，核对日期为 2026-10-21；不据此断言某台主机已经部署。最终内容与实现差距见[输出规范](../specs/moparse-output-spec.md#9-当前实现差距与迁移)。

## 1. 选择运行模式

先在 `.env` 中设置所选模式的开关和地址，再准备对应镜像与模型。以下是服务运行模式；P01–P08 的完整研究配置及就绪状态见[管线索引](../pipelines/README.md)。

| 模式 | `NATIVE_PARSER_BACKEND` | `GLM_OCR_ENABLED` / `GLM_SDK_ENABLED` | 本地服务及 profile |
| --- | --- | --- | --- |
| CPU Docling | `docling` | `0` / `0` | 仅 `moparse`，无 profile |
| Docling + GLM SDK | `docling` | `1` / `1` | `moparse`、`glm-ocr`、`glm-ocr-sdk`；`glm-sdk` |
| MinerU Advanced/TXT + GLM SDK | `mineru` | `1` / `1` | 上述三项及 `mineru-native`、`mineru-vllm`；`mineru` 与 `glm-sdk` |
| 复用远程后端 | 按已有后端选 `docling` 或 `mineru` | 使用扫描识别时为 `1` / `1` | 仅启动本地缺少的服务，远程 URL 必须能从容器内访问 |

CPU 模式用于原生 PDF 和 Office。遇到扫描、混合页且未配置 SDK 时，请求使用 `scan_policy=skip` 保留整页图与未处理状态；`auto` 需要 GLM 与 SDK 同时可用。PDF 内嵌图片的保全不要求启用 OCR。

只需要图片、视频或资产识字时，可设 `GLM_OCR_ENABLED=1`、`GLM_SDK_ENABLED=0`，使用 `glm` profile；这一模式不提供扫描 PDF 的 SDK 处理。图片内容范围见 [API](../specs/api.md)。

## 2. 服务与配置

### 服务依赖和端口

| 服务 | 执行内容及依赖 | 容器端口与默认宿主入口 | Compose 资源设置 |
| --- | --- | --- | --- |
| `moparse` | API、任务、原生路由、来源补充与当前转换；调用所选后端 | `12303`，由 `PORT` 同时改变内外端口 | CPU；未声明 CPU/内存硬上限；无 GPU |
| `glm-ocr-sdk` | CPU 布局与区域编排 → `glm-ocr` | `5002`，默认不映射宿主端口 | CPU；未声明 CPU/内存硬上限；无 GPU |
| `glm-ocr` | GLM-OCR vLLM | `8000` → `127.0.0.1:8001` | GPU；未声明宿主 CPU/内存硬上限 |
| `mineru-native` | PDF 与 ONNX → `mineru-vllm` | `8010` → `127.0.0.1:12432` | 8 CPU、8 GiB；无 GPU |
| `mineru-vllm` | MinerU 视觉模型 vLLM | `8000` → `127.0.0.1:12431` | 4 CPU、20 GiB 宿主内存、2 GiB shm；GPU |

两种模型服务的 GPU 编号默认均为 `1`，由 `GLM_GPU_DEVICE_ID` 和 `MINERU_GPU_DEVICE_ID` 分别选择；单卡机器需要改为实际设备编号。配额不是独占核心，显存需合计考虑两个模型及其他驻留进程；主 API、native worker 和 SDK 不挂 GPU。GLM 默认 FP16、显存利用率 `0.40`、上下文 `16384`；MinerU 默认 FP16、上下文 `8192`、并发 `4`、batch tokens `2048`、显式 KV cache `128 MiB`。显存利用率参数不是总显存硬上限。

### 配置由谁读取

Compose 的 `.env` 用于变量替换，API 还通过 `env_file` 读取它；Compose `environment` 中的固定值优先于 `env_file`。`.env` 不会自动导出到宿主 shell，也不会自动传给所有 sidecar。

| 设置 | 读取方及修改位置 | 生效方式 |
| --- | --- | --- |
| `NATIVE_PARSER_BACKEND`、`GLM_OCR_ENABLED`、`GLM_SDK_ENABLED` | API；`.env` | 重建 API 容器；SDK 开关仅在 OCR 开启时有效 |
| `MINERU_NATIVE_BASE_URL`、`GLM_OCR_API_URL`、`GLM_SDK_URL` | API；`.env` | 重建 API 容器；使用容器可达 URL |
| `GLM_SDK_ORIENTATION_*`、`GLM_SDK_RENDER_SCALE`、`GLM_SDK_MAX_IMAGE_PIXELS` | API；`.env` | 重建 API 容器；默认 CPU 旋正、200 DPI、800 万像素预算 |
| `GLMOCR_OCR_API_URL`、`GLMOCR_OCR_MODEL` | SDK；Compose `glm-ocr-sdk.environment` | 在 Compose 覆盖文件修改并重建 SDK 容器；API 的 OCR URL 不会改变 SDK 下游地址 |
| `MINERU_VLM_BASE_URL`、`MINERU_VLM_MODEL` | native worker；Compose `mineru-native.environment` | 使用覆盖文件并重建 worker 容器 |
| `MINERU_PROCESSING_WINDOW_SIZE`、`MINERU_MALLOC_TRIM`、`MOPARSE_CPU_MFR_BATCH_SIZE` | native worker；Compose 从 `.env` 替换 | 默认 `8`、`1`、`1`；重建 worker 容器 |
| `MINERU_VLM_CONCURRENCY`、`MINERU_INTRA_OP_NUM_THREADS`、`MINERU_INTER_OP_NUM_THREADS` | native worker；Compose 当前固定为 `4`、`8`、`1` | 修改 Compose 覆盖文件；只写进 `.env` 不会改变 worker |
| vLLM 并发、KV、batch、图执行参数 | 对应模型服务的 Compose `command` | 修改覆盖文件并重建模型容器；MinerU 客户端与模型调度并发配套修改 |
| GPU 编号、`GLM_DTYPE`、`GLM_GPU_MEMORY_UTILIZATION`、`GLM_MAX_MODEL_LEN` | Compose 设备与 GLM 命令；`.env` | 重建相应模型容器 |
| `CONTENT_TIMEOUT_SECONDS`、`MINERU_NATIVE_TIMEOUT_SECONDS`、`GLM_SDK_TIMEOUT_SECONDS` | API；`.env` | 示例分别为 `900`、`7200`、`120` 秒；总任务期限仍限制下游剩余时间 |
| `SEMANTIC_TABLE_OUTPUT_ENABLED` | API；`.env` | 当前仅控制有限表格转换；关闭它不能得到独立解析研究入口 |

Docling 默认每个 converter 使用 `DOCLING_NUM_THREADS=4`，`DOCLING_PAGE_WORKERS=1`，`PARSER_WORKERS=1`；总 converter 数上限由配置校验约束为 32。调整并行度时同时配置实际容器资源。Compose 固定 PyPdfium、CPU 和 `DOCLING_DO_CELL_MATCHING=0`；模型目录使用应用变量 `DOCLING_LOCAL_ARTIFACTS_PATH`，避免把空目录误设为上游离线专用的 `DOCLING_ARTIFACTS_PATH`。

MinerU 的 CUDA Graphs 参数已在 Compose 中显式设置为 `FULL_DECODE_ONLY`、capture sizes `[1,2,3,4]`，compile mode 为 `0`，并启用 `--cudagraph-metrics`。部署核对实际命令、捕获日志和已授权请求期间的 `Runtime Mode=FULL` 回放；GLM 按所用 vLLM 的有效图配置核对。图执行与 `torch.compile` 分开记录，执行约束见 [AGENTS.md](../../AGENTS.md#runtime-and-gpu-execution)，调优设计见 [MinerU 调优](../../benchmark/mineru-tuning.md)。

### 网络、存储和访问

所有服务接入外部网络 `moparse_backend`。API 的默认下游地址为 `http://glm-ocr:8000/v1/chat/completions`、`http://glm-ocr-sdk:5002/glmocr/parse`、`http://mineru-native:8010`；worker 再调用 `http://mineru-vllm:8000`。容器中的 `127.0.0.1` 指向自身，远程后端应使用可解析的实际地址。

| 物理卷 | 主要挂载 | 保存内容 |
| --- | --- | --- |
| `mosaicparse-data` | API `/data` | SQLite、任务、正文、资产和日志 |
| `mosaicparse-docling-models`，可由 `DOCLING_MODELS_VOLUME` 改名 | API `/models/docling` | Docling 模型 |
| `mosaicparse-huggingface-cache` | API/SDK `/models/huggingface`；GLM `/root/.cache/huggingface` | 方向模型及 GLM/SDK 缓存 |
| `moparse-mineru-models` | VLM `/models/mineru:ro` | MinerU 视觉权重 |
| `moparse-mineru-small-models` | worker `/models/mineru-native:ro` | MinerU ONNX 小模型 |

worker 的 `/models/mineru-native/models/.locks` 另挂 4 MiB 可写 tmpfs。已有安装保留实际卷名与挂载，应用升级不删除数据卷。需要旧网络别名的安装使用 [compat 文件](../../docker-compose.compat.yml)与 base 配置组合，并确认外部网络 `mosaicparse_default` 存在；新安装只用 base。

下载代理使用 `HTTP_PROXY`、`HTTPS_PROXY`，内部服务名保留在 `NO_PROXY`。原件 URL 下载与应用的模型 API 客户端不继承环境代理。API 的 `API_KEY` 与管理接口的 `ADMIN_TOKEN` 各自配置，鉴权形式见 [API](../specs/api.md)。MCP 经反向代理访问时，在 `MCP_ALLOWED_HOSTS` 加实际 `host[:port]`，在 `MCP_ALLOWED_ORIGINS` 加完整 Origin；例如 `docs.example.com` 和 `https://docs.example.com`，不使用默认通配符。

## 3. 首次准备

### 配置和镜像

从仓库根目录操作；已有 `.env` 时保留并按所选模式修改：

```bash
test -e .env || cp .env.example .env
docker network inspect moparse_backend >/dev/null 2>&1 || docker network create moparse_backend
```

源码构建示例在 `.env` 设置以下本地标签，避免覆盖历史发布标签；使用镜像仓库时改为已确认可用的镜像及 digest，并用 `pull` 替代相应构建：

```dotenv
MOPARSE_IMAGE=moparse:local
GLM_SDK_IMAGE=moparse-glm-sdk:local
MINERU_NATIVE_IMAGE=moparse-native-worker:local
MINERU_VLLM_IMAGE=moparse-mineru-vllm:local
```

先按第 1 节设置后端与 OCR 开关。校验配置并构建 API；SDK 镜像基于 API 镜像，因此按此顺序构建：

```bash
docker compose config -q
docker compose build moparse
```

使用本地 SDK 时再执行：

```bash
docker compose --profile glm-sdk build glm-ocr-sdk
```

原始 `.env` 和完整 `docker compose config` 可能含密钥，不纳入仓库。记录所选提交、实际镜像 ID、模型身份和有效配置；本地 `:local` 标签仅供构建选择，不充当部署证据。

### Docling、GLM 与方向模型

CPU Docling 可在初始化时下载模型，也可先下载到正式数据卷：

```bash
docker compose run --rm --no-deps moparse \
  docling-tools models download --output-dir /models/docling layout tableformer
```

离线机器先转移该卷，检查目标用户可读后设置 `DOCLING_MODEL_DOWNLOAD=0`。使用宿主目录时将完整目录挂到 `/models/docling`；源码环境也可运行 [Docling 下载脚本](../../scripts/download_docling_models.py)。

SDK 旋正所需方向模型按[固定 revision 下载器](../../scripts/download_orientation_model.py)写入 API 的共享缓存：

```bash
docker compose run --rm --no-deps --entrypoint python \
  -v ./scripts/download_orientation_model.py:/tmp/download_orientation_model.py:ro \
  moparse /tmp/download_orientation_model.py \
  --output-dir /models/huggingface/PP-LCNet_x1_0_doc_ori_safetensors
```

GLM 权重和 SDK 布局模型可在首次启动联网下载。当前生产 Compose 的 GLM 模型名没有固定权重 revision，SDK 布局缓存也没有与 MinerU 同等的完整文件锁；离线交接须保存实际模型 revision、文件哈希及 SDK 有效配置，不能据浮动模型名宣称已冻结。研究执行身份须依最新TTS观测策略重新预检冻结，不改变上述生产配置现状。SDK 的 `GLM_SDK_OFFLINE=1` 只切换 SDK 的离线读取；GLM 模型服务的离线环境及缓存路径需在其覆盖配置中单独设置。

### MinerU 模型

使用 MinerU 时，先构建两项镜像，再用一次性 CPU 准备容器将模型写入正式卷；CLI 挂载覆盖 worker 的同目标只读挂载：

```bash
docker compose --profile mineru build mineru-native mineru-vllm
docker volume create moparse-mineru-models
docker volume create moparse-mineru-small-models
docker compose --profile mineru run --rm --no-deps --entrypoint python \
  -v moparse-mineru-models:/models/mineru \
  -v moparse-mineru-small-models:/models/mineru-native \
  mineru-native /worker/scripts/download_mineru_models.py \
  --vlm-dir /models/mineru --native-home /models/mineru-native
```

[模型锁](../../native_worker/models.lock.json)记录视觉模型和 ONNX 小模型的固定 revision、文件大小及 SHA；worker 镜像还执行[依赖补丁校验](../../native_worker/patch_dependency.py)。离线转移两个卷后，使用同一镜像校验已有文件，不加载模型：

```bash
docker compose --profile mineru run --rm --no-deps --entrypoint python \
  -e HF_HUB_OFFLINE=1 \
  -v moparse-mineru-models:/models/mineru:ro \
  -v moparse-mineru-small-models:/models/mineru-native:ro \
  mineru-native /worker/scripts/download_mineru_models.py \
  --vlm-dir /models/mineru --native-home /models/mineru-native --verify-only
```

运行前核对实际容器用户、模型和输入路径、symlink 最终目标以及 lock tmpfs 可写性。文件哈希通过只说明文件一致；完整原生结果与媒体交接仍按[本组说明](../pipelines/README.md)验证。

## 4. 启动

### CPU Docling

设置 `NATIVE_PARSER_BACKEND=docling`、`GLM_OCR_ENABLED=0`、`GLM_SDK_ENABLED=0` 后启动：

```bash
docker compose up -d moparse
```

### Docling + 本地 GLM SDK

设置 `NATIVE_PARSER_BACKEND=docling` 和两项 GLM 开关为 `1`，完成模型准备后启动：

```bash
docker compose --profile glm-sdk up -d glm-ocr glm-ocr-sdk moparse
```

仅启用直接识字模式时关闭 SDK，改用 `docker compose --profile glm up -d glm-ocr moparse`。

### MinerU Advanced/TXT + 本地 GLM SDK

设置 `NATIVE_PARSER_BACKEND=mineru`、两项 GLM 开关为 `1`；总任务超时按工作负载配置，若仍为示例值 `900` 秒则会早于 worker 的 `7200` 秒上限。模型准备完成后启动：

```bash
docker compose --profile mineru --profile glm-sdk up -d \
  mineru-vllm mineru-native glm-ocr glm-ocr-sdk moparse
```

Compose 的健康依赖负责等待上游。启动失败先看第 5 节的后端状态与日志，不用延长总超时替代故障定位。

### 远程服务与现有安装

设置实际可达的后端地址；以下域名是待替换示例：

```dotenv
GLM_OCR_ENABLED=1
GLM_SDK_ENABLED=1
GLM_OCR_API_URL=http://gpu-host.example:8000/v1/chat/completions
GLM_SDK_URL=http://sdk-host.example:5002/glmocr/parse
# 只有选择 MinerU 时才需要：
MINERU_NATIVE_BASE_URL=http://native-host.example:8010
```

全部后端已在远端运行时不启用本地 profile：

```bash
docker compose up -d --no-deps moparse
```

远程 SDK 本身必须配置正确的 OCR 地址；API 的 URL 不会修改远端 SDK。复用同机既有服务时，先检查 `moparse_backend` 网络成员，仅为缺少的成员添加 `glm-ocr`、`glm-ocr-sdk` 等别名。使用 `--no-deps` 更新 API 可保留既有模型服务；本地仍有缺少的 worker 或模型时，先单独启动它们。

### 源码环境

Python 使用 `>=3.13,<3.14`；前端构建工具与版本见 [package.json](../../frontend/package.json)。源码 CPU 模式从仓库根目录启动：

```bash
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
DATA_DIR=./data STATIC_DIR=frontend/dist NATIVE_PARSER_BACKEND=docling \
  GLM_OCR_ENABLED=0 GLM_SDK_ENABLED=0 \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 12303
```

源码与 Docker 共用应用设置，但 GPU 模型服务仍需分别准备。FFmpeg/FFprobe 在 API 镜像中已安装；源码运行视频功能时由宿主提供。

## 5. 检查、升级与故障定位

### 启动检查与内容验收

下列 URL 按实际 `PORT` 调整；`/health` 与 `/ready` 无需 API Key：

```bash
docker compose ps -a
curl --fail-with-body http://127.0.0.1:12303/health
curl --fail-with-body http://127.0.0.1:12303/ready
docker inspect moparse --format '{{.Image}}'
docker inspect moparse --format '{{json .Mounts}}'
```

核对 `/health` 返回的状态、所选后端与公开配置，不能只看 HTTP 200；`/ready` 检查存储及当前默认处理所需后端，不就绪返回 503。`/v1/backends` 给出单项后端状态，配置了 API Key 时按 [API 认证](../specs/api.md#认证)携带它。GPU 服务另读实际设备、命令和模型 revision。

内容验收使用明确纳入范围的完整原件与独立标注，按[实施路线](../engineering/technical-route.md#4-验证与发布条件)核对适配、转换、正文、图片、输出包和状态。任务进入 `completed` 或后端就绪只说明对应运行阶段，不证明输出规范已全部实现；当前 bundle 的具体缺口见[输出规范](../specs/moparse-output-spec.md#9-当前实现差距与迁移)。

### 只升级 API 与回退

先记录旧容器身份，将旧镜像保留为独立回退标签，并在仓库外保存私有恢复资料。以下针对 Compose 中的 `moparse`；已有安装若容器名不同，使用实际名称：

```bash
backup_dir="$(mktemp -d /var/tmp/moparse-backup.XXXXXX)"
rollback_tag="moparse:rollback-$(date +%Y%m%d%H%M%S)"
cp .env "$backup_dir/runtime.env"
docker inspect moparse > "$backup_dir/api-container.json"
docker image tag "$(docker inspect moparse --format '{{.Image}}')" "$rollback_tag"
printf '%s\n' "$rollback_tag" > "$backup_dir/api-image-tag"
```

另外备份实际使用的 Compose 与覆盖文件，检查项目标签、网络和物理卷归属。构建目标 API 镜像后暂停接入，确认队列和底层清理均结束，再停止 API 并复制完整数据；不要在线直接复制正在写入的 SQLite：

```bash
docker compose build moparse
docker compose stop moparse
docker cp moparse:/data "$backup_dir/data"
docker compose up -d --no-deps --no-build moparse
```

按启动检查读回新镜像、挂载和就绪状态，并核对既有任务与资产。需要代码回退时，将 `.env` 的 `MOPARSE_IMAGE` 改为记录的回退标签，恢复匹配的运行配置，再执行 `docker compose up -d --no-deps --no-build --pull never moparse`；正常代码回退保留现有数据卷，不用部署前数据库覆盖新任务。模型或 SDK 也需变更时，按所需服务另定替换范围，不把 API 更新扩展为全部服务重建。

停止或改名的旧容器仍可能保留 Compose 标签，普通 `up` 会按标签选择容器；保留可恢复镜像、挂载及私有恢复资料后再处理自己拥有的旧容器，并用 `docker compose --dry-run up -d --no-deps moparse` 核对计划。历史发布身份见[既有发布记录](../research/research-framework.md#102-2026-10-19-服务发布记录)，不作为当前回退默认值。

### 常见故障

| 现象 | 优先检查 |
| --- | --- |
| CPU 正常，扫描 PDF 失败 | 两项 GLM 开关、SDK 是否启动及可达；无 SDK 时用 `scan_policy=skip` 明确保留扫描页 |
| API 可达模型，SDK 仍报连接失败 | SDK 的 `GLMOCR_OCR_API_URL` 与容器网络；它不继承 API 的 OCR URL |
| MinerU 启动即失败 | 模型锁校验、目标容器内路径与读取权限、`.locks` tmpfs、worker 与模型服务日志 |
| 修改线程或并发后无变化 | 是否修改了真正的 worker 环境或模型 `command`，而非只在 `.env` 增加未引用的变量 |
| `/ready` 返回 503 | 返回的 `checks`、后端状态，再看 `docker compose logs --tail=100 <服务名>`；分别排查存储、native、GLM、SDK |
| GPU OOM 或捕获失败 | 实际 GPU、共同驻留模型、KV/并发/图捕获设置及总显存；按记录的失败条件处理，调优见独立计划 |
| 请求断线或任务仍在清理 | 按原 Job ID 续取，核对 deadline 与底层清理；任务协议见 [API](../specs/api.md)，不重新提交执行状态未知的请求 |
| ZIP 缺 Markdown 或离线图片引用不可用 | 当前已知交付缺口，按输出规范落实打包与组装；重启或切换模型不能补齐 |

清理过期任务使用受保护的管理接口，操作方式见 [API](../specs/api.md)。应用停止用 `docker compose stop moparse`；需要保留任务和模型时不执行 `docker compose down -v`。

## Paddle 研究执行器的线程生命周期

本节适用于 `moparse_eval.paddle_server` 私有研究服务。2026-10-25 的执行修复默认使用 `paddle_execution_mode: "persistent-owner-v1"`，原生模型初始化、SDK推理和关闭均由一条长期非daemon线程执行。HTTP处理线程只提交和等待；状态查询保持可用。提交锁限制为一个已提交原生工作，关闭等待已发调用返回，再关闭SDK并join线程，不取消、重试或提前解除GPU所有权。

逐页SDK调用默认 `paddle_use_queues: false`，映射官方 `predict(..., use_queues=False)`。已渲染的一张图片在同一调用中依次完成布局和VLM，避免SDK每次创建内部输入、CV及VLM线程。显式 `true` 只保留为受控诊断开关，不能据此宣称采用了内存修复。预处理、原生区域、Markdown和资产导出的职责仍由[管线专文](../pipelines/README.md)维护。

线程修复保持声明的镜像、模型revision、FP16、解码参数和4 CPU/20 GiB宿主内存限制，不依赖增加内存上限、逐页重启服务或通过GC清缓存。CUDA Graphs须按实际捕获与使用范围记录，不能把局部捕获作为全部生成计算使用Graphs的证明。缺陷、受控验证与未验证范围见[工程诊断](../../benchmark/diagnostics/README.md)。

线程生命周期配置只处理对应的研究执行问题，不构成P03/P04质量或效率验收。研究修复与工程预检02之后，本轮八组各完成quality800一次和perf80三轮，统一评分、首版报告及原MO服务恢复完成；结果只见[当前统一评测报告](../../benchmark/reports/lite/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS仅观测不控制，先前撤回测量不恢复，生产Compose、部署环境和现有服务配置不因研究配置而改变。

受测进程合计16 GiB自有显存预算及TTS共驻观测口径以[评测标准](../../benchmark/evaluation-tasks.md)为准；20 GiB仍是GPU推理侧宿主内存预算。按2026-10-26最新授权，TTS不由评测启动、停止、重启或改配置，身份和活动只观测，不控制负载，也不因变化或unknown阻断执行、评分或报告，无需等待TTS维护确认。维护窗口只暂停授权的原MO-Parse模型容器，退出时按原配置和身份恢复，不能用研究配置覆盖原生产GLM或MinerU服务；工程预检不构成部署验收。

## GLM MRoPE 运行配置

GLM-OCR采用GPT-J相邻配对；固定版vLLM 0.19.1的融合rotary算子使用另一种配对，需为GLM选择native rotary。2026-10-28更新的[生产Compose](../../docker-compose.yml)显式传入 `--compilation-config '{"custom_ops":["all","-rotary_embedding"]}'`，只切换该算子，保留其他custom ops、CUDA Graphs策略、FP16及既有资源和解码参数，不把这个修复应用到MinerU模型。缺陷依据及受控验证边界见[工程诊断](../../benchmark/diagnostics/README.md)。

这次配置修改完成了合成命令检查和Compose静态检查，没有重建容器、执行模型请求或改变TTS。检查时运行中的GLM镜像身份为 `sha256:df7be4c4d818e250a8c80f78d110571e92e72a1fefec06fed82a2e37e473cd48`，其启动命令尚未包含上述修复；源码配置通过检查不代表线上已经生效或完成部署验收。

P05及P01/P02/P06/P07共享GLM研究分支通过冻结配置的 `inference_services` 字段 `rotary_embedding: "native"` 选择同一修复；下例只示意字段位置，其余镜像、模型、资源与端点字段沿用声明。研究启动器据此增加上述 `custom_ops`，继续使用 compile mode 0、`FULL_DECODE_ONLY` 和 capture sizes `[1,2,3,4]`，保留 `glmocr 0.1.5`、`--dtype half`、重复惩罚1.1以及声明的token、KV、并发和资源预算。研究执行身份、结果及资源条件由[评测索引](../../benchmark/reports/README.md)维护，不能将这些记录当作服务客户端或生产GLM部署验收。

```json
{
  "inference_services": [
    {
      "role": "glm",
      "family": "glm",
      "rotary_embedding": "native"
    }
  ]
}
```
