<p align="center">
  <img src="assets/moparse-logo-1024.png?v=mo-parse-terminal-20261019-2" alt="MO-Parse 蓝青色立式文档终端标志" width="132" />
</p>

# MO-Parse

**探索如何在消费级 GPU 和 CPU 上实现高质量文档内容解析。**

MO-Parse 提供可自托管的内容解析服务，最终目标是生成便于下游信息抽取的语义 Markdown：所有表格、PDF 流程图和组织结构图转换为描述，优先使用多层列表；去掉页码、页眉和页脚。这由 MO-Parse 在接入解析结果后完成；底层管线可以输出含表格的 Markdown、XML 区域定义或其他结构，不负责服务的最终格式。完整要求见[最终语义输出契约](docs/output-contract.md)。

当前表格语义实现仅转换部分来源表格，仍有原表、页面家具和未恢复的图形关系，尚未满足完整目标。2026-10-20 已统一表格来源、显示映射和语义标记的当前定义，取消内部协议版本；GFM 仅作为具体显示格式，来源规则见[表格来源与证据约定](docs/table-source.md)。本次整理没有启动推理或部署。

| 项目组成 | 内容 | 入口 |
| --- | --- | --- |
| 最终输出契约 | 全部表格和两类图形的语义描述、页面家具清理、中间表示与最终结果边界 | [最终契约](docs/output-contract.md) |
| 研究与技术路线 | 解析质量与成本研究、方法选择及 MO-Parse 工程边界 | [研究框架](docs/research-framework.md) · [技术路线](docs/technical-route.md) |
| 评测任务 | 外部语料与独立标注的交接要求、解析内容和结构指标 | [评测任务](benchmark/evaluation-tasks.md) |
| 待测试管线 | 八个固定解析组合、忠实导出及资源条件 | [待测试管线](benchmark/pipelines-to-test.md) |
| MinerU 调优 | 路线内性能实验与质量验收 | [MinerU 调优](benchmark/mineru-tuning.md) |
| 自托管服务 | API、Web UI、MCP 与运行配置 | [快速开始](#快速开始) · [部署](docs/deployment.md) |

## 数据与研究

Benchmark 仅保留评测任务、待测试管线、MinerU 调优三份规划文档。八条解析管线按相同原件、独立标注、忠实导出规则和资源预算比较原始解析质量与处理成本，不沿用旧成绩。计时包含必要渲染、声明的解析工作、忠实导出和必要资产；MO-Parse 的语义转换与页面清理另行测试和计时，HTTP、排队、轮询、下载及纯持久化也不计入解析耗时。

解析预期结果与语料的生成已在其他项目开展，本仓库不再维护原本地样本目录，也不重复生成语料与金标。后续评测接收外部项目交接的完整原件、独立标注和版本清单，实际范围需另行明确；没有样本或未标注的类别记录为未覆盖。额外六份公开原件位于 [pdf_sample_extra/](pdf_sample_extra/README.md)，**暂不处理**，不用于解析、评测、调优、预热或上线判断。

## 研究框架与技术路线

解析研究回答各方法在不同来源和版式上恢复了什么、哪里出错、花费多少，再据证据决定方法选择。MO-Parse 将解析结果转成下游所需格式，是另外的服务开发工作；不能要求候选管线直接完成它。具体方法见[研究框架](docs/research-framework.md)，交接与工程顺序见[技术路线](docs/technical-route.md)。

![八步解析研究：问题、来源、条件、执行、质量成本、选择、调优和结论](docs/assets/research-decision-flow.svg)

1. **明确问题与范围。** 确认外部交接的原件与标注版本，固定解析任务、关键错误、资源和计时边界。
2. **原件分层与低成本观测。** 独立标注来源和版式，研究可在解析前取得的廉价特征及其费用。
3. **固定对照条件。** 确定八组身份、允许输入、前处理、忠实导出、指标、资源和失败规则。
4. **执行固定完整管线。** 同字节完整 PDF 输入，保存各方法原始结果、研究侧 Markdown 和处理记录。
5. **分类别分析质量与成本。** 在相同原件上配对比较内容、结构、覆盖、失败和费用；分报文档与类别，先核对关键质量与资源，再比较成本。
6. **决定固定方法或研究选择策略。** 来源类别不直接等于方法优劣；有稳定差异才验证运行前选择、误判、切换和跨页上下文的净收益。
7. **路线内调优与复验。** 保持解析质量与预算，分别研究线程、并发和执行方式，分开预热并至少三次正式性能测量。
8. **形成研究结论。** 说明方法适用类别、质量代价、资源条件、未覆盖范围和接入建议。

原始解析和研究侧导出可以保留表格、源图、页码及页眉页脚，不要求统一语义接口或多层列表。服务转换完成与否不作为八组研究准入条件，服务发布也不作为解析研究的第八步。现有服务入口还混有来源补充、资产和语义处理，现有耗时字段也不满足统一研究边界；实际调用与计时缺口见[技术路线](docs/technical-route.md#61-现有调用与计时字段)。

## MO-Parse 服务处理目标

下图是服务工程流程。第 2 步得到后端解析结果，后续的语义转换、清理、组装与接口交付由 MO-Parse 完成。该边界不预选 MinerU、Docling 或其他方法，也不把整段服务耗时当作解析管线耗时。

![七步服务流程：接收任务、调用解析、读取结果、转换清理、组装、验收和返回保存](docs/assets/workspace-pdf-pipeline.svg)

1. **接收原文件与任务。** 保留原件身份、范围及内部来源。
2. **调用选定解析后端。** 获得本方法原始文字、结构与资产，输出可为含表格的 Markdown、HTML、XML 或其他结构。
3. **读取已有解析结果。** 接入代码读取已有信息，保留缺失与失败，不在读字段时制造事实。
4. **转换内容并清理。** MO-Parse 处理表格完整标题和限定关系、流程方向与条件、组织层级及交叉联系，区分页面家具和业务内容。
5. **组装文档正文。** 核对顺序、跨页范围、标题单位附注与内容去向，生成语义 Markdown；无原表、页码页眉页脚及调试信息。
6. **验收接口结果。** 分报格式、内容覆盖、语义正确性、未解决范围与完成状态，核对资产和来源。
7. **返回并保存同一结果。** 同步响应、异步结果、落盘与下载使用同一份 `result.md`。

原表与原图可以是合格解析产物，内部保全却不等于服务已完成最终语义描述。表格/图形转换和页眉页脚清理单独测试及计时，最终契约仅约束 MO-Parse 对外文档。

## 现有实现与缺口

| 能力 | 已有情况 | 距离最终契约的工作 |
| --- | --- | --- |
| 来源解析、任务与资产 | 已有 API、Web UI、MCP 及多种解析后端 | 保真读取已有结果，补齐服务区域清点与覆盖 |
| 表格语义转换 | 部分完整矢量网格、标题作用域与字段模式可展开为列表 | 所有表格类型、混合区、跨度、限定语和跨页关系 |
| 流程图与组织图 | 当前图片能力主要是可见文字识别 | 节点、边、方向、条件、层级与最终多层列表 |
| 页面家具清理 | 当前来源结果仍带页码、页眉和页脚 | 区分页面家具与业务内容，在最终转换中清理 |
| 最终格式与状态 | 仍混合描述、GFM 和保全提示 | 无原表和分页信息的最终正文，完整覆盖及状态联动 |

已有表格语义实现的有界实验与发布记录见[历史实验记录](docs/research-framework.md#101-2026-10-19-表格语义有界实验与实现)和[运行配方](docs/runtime-recipes.md)。这些记录不证明新的完整最终契约通过，八条主管线仍无本轮正式比较结果。

![MO-Parse Web界面](docs/assets/mo-parse-web-desktop.png?v=mo-parse-terminal-20261019-2)

当前服务还支持 Office 嵌图、独立图片和视频关键帧识字，本轮不自动扩大其研究范围。实体消歧、指标归一、业务事件抽取、Embedding、索引与问答由下游负责；来源明确的字段、流程和组织关系由 MO-Parse 表达。

## 快速开始

CPU模式可独立处理数字原生PDF和Office文档：

```bash
cp .env.example .env
docker network create moparse_backend
docker compose up -d --build moparse
```

打开Web UI：<http://localhost:12303/>；API文档：<http://localhost:12303/docs>；MCP：<http://localhost:12303/mcp>。

首次解析可能下载Docling模型，初始化期间`/ready`可能暂未就绪。模型保存在命名卷中。离线模型、扫描OCR、MinerU/GLM模型服务、显卡配置与远程模型地址见[部署文档](docs/deployment.md)和[运行配方](docs/runtime-recipes.md)。

```bash
curl --fail-with-body http://localhost:12303/v1/content/parse \
  -F file=@tests/fixtures/native-report.pdf \
  -F scan_policy=auto \
  -F language=zh,en \
  -o result.md
```

大输入和视频返回202及Job身份，按Job查询并下载最终结果。网页超时`0`表示采用服务端时限。正式展示名为MO-Parse；仓库、Python包、Compose服务和既有配置标识继续使用`moparse`。

## API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/v1/content/parse` | 同步解析或返回异步Job |
| `POST` | `/v1/content/jobs` | 创建异步任务 |
| `GET` | `/v1/content/jobs/{job_id}` | 查询状态 |
| `GET` | `/v1/content/jobs/{job_id}/events` | SSE进度 |
| `GET` | `/v1/content/jobs/{job_id}/result` | 下载Markdown |
| `GET` | `/v1/content/jobs/{job_id}/assets` | 列出图片、视频和帧资产 |
| `GET` | `/v1/content/jobs/{job_id}/bundle` | 下载结果与资产包 |
| `POST` | `/v1/content/jobs/{job_id}/retry` | 重试任务 |
| `DELETE` | `/v1/content/jobs/{job_id}` | 取消或删除任务 |
| `GET` | `/v1/backends` | 后端能力状态 |
| `GET` | `/health`, `/ready` | 健康与就绪检查 |
| `GET/POST` | `/mcp` | MCP Streamable HTTP |

参数、鉴权、状态机和完整路由见[API文档](docs/api.md)，在线Schema以`/openapi.json`为准。API Key与独立Admin Token分别配置；MCP经反向代理访问时显式配置允许的Host和Origin，见[部署说明](docs/deployment.md)。

## 开发与验证

需要Python`>=3.13,<3.14`、uv和Node20。主服务的PyTorch依赖锁定CPU wheel；GPU模型通过独立服务部署。

```bash
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
DATA_DIR=./data STATIC_DIR=frontend/dist GLM_OCR_ENABLED=0 \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 12303
```

```bash
uv lock --check
uv run ruff check .
uv run mypy app
uv run pytest
uv run python scripts/export_openapi.py --check
uv run python scripts/generate_fixtures.py --check
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

CI 使用生成夹具和模拟后端验证接口与错误处理，不能代替真实模型评测。新评测的输入、标注和评分要求见[评测任务](benchmark/evaluation-tasks.md)。Markdown 普通自然段保持一个物理行，编辑器使用软换行。

## 文档与许可证

- [最终语义输出契约](docs/output-contract.md)
- [研究框架与方法](docs/research-framework.md) · [技术路线与实现依赖](docs/technical-route.md)
- [评测任务](benchmark/evaluation-tasks.md) · [待测试管线设置](benchmark/pipelines-to-test.md) · [MinerU 调优](benchmark/mineru-tuning.md)
- [架构](docs/architecture.md) · [API](docs/api.md) · [部署](docs/deployment.md) · [运行配方](docs/runtime-recipes.md)
- [品牌与图标](docs/brand.md) · [夹具与来源许可](tests/fixtures/README.md)

本项目原创代码使用[Apache License 2.0](LICENSE)。文档原件、模型权重、上游框架、容器和源码夹具分别遵循其许可证；评测任务说明原件来源与使用范围。
