# MO-Parse 部署配方

本文说明仓库维护的配置与启动方式，具体安装应读取实际镜像、模型、资源配额和容器参数。部署操作见[部署说明](deployment.md)，性能实验设计见[MinerU 调优计划](../benchmark/mineru-tuning.md)。

## 部署模式

| 模式 | 配置与启动 |
| --- | --- |
| CPU Docling | `NATIVE_PARSER_BACKEND=docling`、`GLM_OCR_ENABLED=0`；`docker compose up -d --build moparse` |
| Docling 加 GLM SDK | 开启 `GLM_OCR_ENABLED` 和 `GLM_SDK_ENABLED`；`docker compose --profile glm-sdk up -d --build` |
| MinerU Advanced 加 TXT、GLM SDK | 使用下方配方；`docker compose --profile mineru --profile glm-sdk up -d --build` |
| 已有远程模型服务 | 配置 GLM/MinerU 实际地址，只启动缺失的 CPU 服务 |

## 实现与部署状态

以下保存 2026-10-19 表格语义转换发布时读回的镜像与接口记录，不代表最新最终契约已实现。2026-10-20 的内部表示去版本化没有执行推理、变更配置或部署，历史镜像标签与校验值保持原样；判断当前实例身份仍须重新读取现场。新目标要求全部表格、PDF 流程图与组织图语义化并清理页码页眉页脚，具体见[最终契约](output-contract.md)。

2026-10-19 用户明确授权实验、实现和部署，解除本任务此前的暂停。表格语义转换 已部署至本机 `12303` 端口，API 版本为 `0.5.1`，镜像标签为 `moparse:0.5.1-semantic-v1-20261019`，实际镜像 ID 为 `sha256:2181097e7e363b63bcada547f7f9b425cd394696716732cd04b6c39a85a03670`。容器启动时间为 `2026-10-19T02:01:20.432708366Z`，即北京时间 10:01:20；镜像内全部 59 个应用 Python 文件的 SHA256 与验收工作区一致。

`/health` 状态为 `ok`，`semantic_table_output_enabled=true`；`/ready` 就绪后端为 `mineru-advanced-txt`、`glm-ocr-remote` 和 `glm-sdk-remote`。MinerU 后的独立 Docling 复核代码、初始化与就绪依赖已经从生产移除。原生 worker 及三个既有模型服务的实际镜像 ID 和启动时间在发布前后逐一核对，均未改变；本次只重建主 API。

| 既有服务 | 实际镜像 ID 的前 12 位 | 启动时间 UTC |
| --- | --- | --- |
| `moparse-native-worker` | `99495729433d` | `2026-10-18T20:15:09.699691808Z` |
| `moparse-mineru-vllm` | `ea407324215f` | `2026-10-18T15:07:50.906734475Z` |
| `docling_glm_ocr_sdk` | `abe353926afb` | `2026-10-16T21:15:08.695015459Z` |
| `docling_glm_ocr` | `df7be4c4d818` | `2026-10-10T18:50:15.890807408Z` |

生产真实接口处理五份完整原件，共 68 页。六页原件采用同步接口，其余采用异步接口；所有任务均为 `completed`。返回或任务结果、下载、持久化的 `output/result.md` 与语义审计清单中的最终 SHA256 一致，当时协议下的内部及正文物理页标记完整；这些正文标记按新最终契约应被清理，这次历史验收不证明清理已实现。混合原件、扫描原件及正文控制原件均实际下载图片并核对哈希。

| 原件 | 页数 | 任务 ID | 已转换来源片段 | 保留来源片段 | 图片数 |
| --- | ---: | --- | ---: | ---: | ---: |
| `1210860446.pdf` | 6 | `job_01M58Y8WWGQ03Z7B9N9J0Y45KW` | 5 | 5 | 0 |
| `1225474693.pdf` | 4 | `job_01M58YD71ZMBEVC2A3HA0Y49BF` | 2 | 4 | 0 |
| `1225473526.pdf` | 27 | `job_01M58YDH9HWNV668QRFMN01DNT` | 5 | 5 | 3 |
| `1225475333.pdf` | 28 | `job_01M58YF787TFA56GBFRFYM0325` | 0 | 12 | 28 |
| `1211290753.pdf` | 3 | `job_01M58YJ16JDKS5DZ9SXAZJTV11` | 0 | 1 | 1 |

片段计数只统计已恢复并进入来源视图的物理表格片段，不证明原件中全部表格都已检出。混合原件有一个保留视图包含两个来源片段，因此其 Markdown 中的保留视图数为 4、保留来源片段数为 5。六页原件最终 Markdown SHA256 为 `54299ad1e69f9e6e6d340a59617f7b9af17d30d26043b964814f5aef74ed1a3d`，与三次直接完整执行及候选镜像接口结果一致。

对部署输出重新核对冻结的 141 个关系目标：117 个正确转换、0 个已观察错绑、24 个保留原表。该结论限于实际标注目标，不能外推到全部 68 页内容、单位附注、扫描表或其他模板；完整研究边界见[实验记录](research-framework.md#101-2026-10-19-表格语义有界实验与实现)。HTTP、排队、轮询和持久化验收不是完整处理性能比较，P01 至 P08 尚无本轮主比较成绩；流程与组织关系、全部表格及最终页面清理也未因该记录获得验收。

发布检查为后端 `529 passed, 1 skipped`、前端 73 项通过、类型检查、静态检查、OpenAPI、生产前端构建和 Markdown 策略通过。跳过项是依赖真实 FFmpeg 的视频验收，不属于本轮 PDF 语义验收。生产核验完成时队列无活动任务；本机证据保存于 `data/research/semantic-20261019/production-acceptance.json`、`production-relation-acceptance.json`、`deployment-before.json` 和 `deployment-after.json`，各任务的实际下载 Markdown 保存在同目录的 `production-http-*` 子目录。

旧 API 镜像 `sha256:f5d5e007e3ed3338988b00184457d0f9ab8846a72234d0ebae60093ee53248c9` 保留标签 `moparse:rollback-before-semantic-v1-20261019`；发布前配置及任务数据库备份位于本机受限目录 `data/research/semantic-20261019/rollback/`。回退时恢复对应配置、选择该镜像并只重建 API；正常代码回退保留现有任务数据库，不用部署前备份覆盖发布后任务。

## MinerU 与表格转换配方

软件 `MinerU 4.0.12` 负责 PDF 分析与结构处理，视觉权重为 `opendatalab/MinerU2.5-Pro-2605-1.2B`，`mineru2.5-pro` 是服务别名。模型 revision 固定为 `08aaea840498d49ce16247b6263196cf02814885`，使用 FP16。

```dotenv
COMPOSE_PROJECT_NAME=moparse
MOPARSE_IMAGE=moparse:0.5.1-semantic-v1-20261019
MINERU_NATIVE_IMAGE=moparse-native-worker:0.5.1-request-control-20261019
NATIVE_PARSER_BACKEND=mineru
MINERU_NATIVE_BASE_URL=http://mineru-native:8010
MINERU_NATIVE_TIMEOUT_SECONDS=7200
CONTENT_TIMEOUT_SECONDS=7200
MINERU_VLM_CONCURRENCY=4
MINERU_INTRA_OP_NUM_THREADS=8
MINERU_INTER_OP_NUM_THREADS=1
MINERU_PROCESSING_WINDOW_SIZE=8
MINERU_MALLOC_TRIM=1
MOPARSE_CPU_MFR_BATCH_SIZE=1
SEMANTIC_TABLE_OUTPUT_ENABLED=1
GLM_OCR_ENABLED=1
GLM_SDK_ENABLED=1
GLM_SDK_ORIENTATION_ENABLED=1
GLM_SDK_RENDER_SCALE=2.7777777777777777
```

这些镜像标签是本机配置示例，不表示公开注册表已发布同名版本，也不凭标签证明内容质量或部署验收。全新安装先构建目标镜像；已有安装按真实镜像身份升级并保留数据卷。需要保留既有 API 网络别名的安装可设置 `COMPOSE_FILE=/opt/moparse/docker-compose.yml:/opt/moparse/docker-compose.compat.yml`；全新安装可仅使用 base。

Native worker 限 8 CPU、8 GiB，VLM 限 4 CPU、20 GiB。客户端并发和 vLLM `max_num_seqs` 均为 4，context 8192、batch tokens 2048、KV 预算 128 MiB；ORT intra 8/inter 1，OMP/OpenBLAS/MKL 各 4。API、native 和 SDK 不挂 GPU。参考主机两张卡功率上限各 200 W，整卡读数包含共享负载。

CUDA Graphs 必须启用并核对真实推理执行，`torch.compile` 与图执行分别配置：

```text
--compilation-config '{"mode":0,"cudagraph_mode":"FULL_DECODE_ONLY","cudagraph_capture_sizes":[1,2,3,4],"max_cudagraph_capture_size":4}'
--cudagraph-metrics
```

普通命令不带 `--enforce-eager`。启用后检查实际命令、捕获成功日志与请求期间 `Runtime Mode=FULL` 记录；仅配置正确或 `/ready` 成功不证明图回放。调优变量、重复次数和计时边界统一见[MinerU 调优计划](../benchmark/mineru-tuning.md)。

## 模型准备与启动

```bash
docker network create moparse_backend
docker compose --profile mineru build mineru-vllm mineru-native
docker volume create moparse-mineru-models
docker volume create moparse-mineru-small-models
docker run --rm --entrypoint python \
  -v moparse-mineru-models:/models/mineru \
  -v moparse-mineru-small-models:/models/mineru-native \
  moparse-native-worker:0.5.1-request-control-20261019 \
  scripts/download_mineru_models.py \
  --vlm-dir /models/mineru --native-home /models/mineru-native
docker compose --profile mineru --profile glm-sdk up -d --build
curl --fail http://127.0.0.1:12303/ready
curl --fail http://127.0.0.1:12303/v1/backends
```

网络和卷已存在时复用。下载器校验 [models.lock.json](../native_worker/models.lock.json) 中的固定 revision、大小和 SHA；增加 `--verify-only` 可离线核验而不加载模型。运行前在实际容器、用户和挂载中确认 PDF、模型与最终 symlink 目标可读，`/models/mineru-native/models/.locks` 的 4 MiB tmpfs 可写。

## 原件证据与任务控制

已有 `SEMANTIC_TABLE_OUTPUT_ENABLED` 默认开启，当前实现仅对部分完整来源矢量表生成描述，其余仍保留 GFM 或原图。设为 `0` 可做内部 GFM 对照，但不能作为符合新最终契约的生产交付模式；本轮不修改该配置行为。已有引用协议见[API](api.md#表格关系与来源引用)，历史记录见[历史实验](research-framework.md#101-2026-10-19-表格语义有界实验与实现)。

MinerU 管线不再运行独立 Docling 表头或来源冲突复核，没有第二解析器的初始化、额外页面解析或就绪依赖。原 PDF 格线、字形和样式只在满足严格对应条件时补充表头与来源作用范围；证据不足时现有实现保留完整分页表及未知状态；目标要求在内部保全这些来源并明确未完成范围，不能把保留原表算作最终转换成功。Docling 仍可通过原生后端配置独立选择，其线程设置不代表 MinerU 会调用 Docling。

SDK 坏表区域隔离保留邻接正文、表格、原页图和未知状态。收到响应或执行状态不明时不重 POST。任务各阶段共享剩余 deadline；取消保持 `running/cancellation.cleanup`，直到自己持有的底层请求完成清理。SDK 缺少服务端取消确认，其远端执行状态另记。

网页超时 `0` 表示采用服务端默认，已有浏览器保存值会保留。接入端持久保存任务 ID、断线后续取同任务，具体见[接入提示词](prompts/eventrail-moparse-integration-fix.md)。更多 GPU、远程地址、卷和反向代理设置见[部署说明](deployment.md)。

## 最终契约的后续发布门槛

当前镜像和开关均不保证全部表格、流程图与组织图的语义描述，也不保证页面家具已清理。不能仅开启转换开关、更新镜像标签或删去输出表格就宣称达到目标；具体缺口见[最终契约](output-contract.md#9-当前实现差距与迁移)。

后续服务实现验证后端结果读取及 MO-Parse 自身的关系转换，再按外部项目交接并明确纳入范围的完整原件与独立标注，对表格、图形和页面清理做内容与格式验收，检查语义未完成状态及响应、持久 Markdown、下载和资产一致。通过后按真实版本构建、发布并读回镜像与模型身份，保留回退依据；研究与服务配置继续分开，额外六份 PDF 暂不处理。

这些门槛针对服务发布，不是解析研究的准入条件。八组解析比较止于原始结果及忠实导出，服务语义转换、页面清理和接口组装另行测试与计时；无需为启动解析对照先部署统一最终转换。
