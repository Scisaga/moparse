# MO-Parse HTTP 与 MCP 契约

默认 Base URL 为 `http://localhost:12303`，在线定义以 `/openapi.json`、`/docs` 和 `/redoc` 为准。

本文说明当前 HTTP 与 MCP 行为；目标交付及实现差距统一见[输出规范](moparse-output-spec.md)，八组原生格式与适配设计见[逐管线说明](../pipelines/README.md)。文档正文使用 `result.md`、`text/markdown`，图片经资产接口交付；任务状态、错误和资产索引使用 JSON 控制协议。现有 bundle 尚未包含 Markdown 正文。

公开接口的最终要求由 MO-Parse 在接入解析结果后履行，不要求底层后端直接生成该格式。候选管线的原始结果和研究侧 Markdown 可以含表格及页面信息；其解析质量与成本按[研究框架](../research/research-framework.md)评价，不按本文最终格式评分。逐管线服务适配应先核对原生输出，现有公共接口不因此增加八组或模型选择参数，当前接入也不代表全部研究配置已实现。

## 认证

设置 `API_KEY` 后，`/v1/content/*`、`/v1/backends` 与 `/mcp` 接受：

```http
Authorization: Bearer <API_KEY>
```

也可使用 `X-API-Key`。管理端点只接受独立的 `X-Admin-Token`。资产 URL 与 bundle 不会绕过 API Key。

## 输入与参数

`POST /v1/content/parse` 和 `POST /v1/content/jobs` 使用 `multipart/form-data`； `file` 与 `source_url` 必须且只能提供一个。

| 字段 | 值 | 默认值 |
|---|---|---|
| `file` | PDF、DOCX、PPTX、常见图片及视频 | — |
| `source_url` | 通过 SSRF 校验的 HTTP(S) URL | — |
| `scan_policy` | `auto\|skip` | `auto` |
| `unit_range` | 一基页/幻灯片范围，如 `1-5,8` | 全部 |
| `language` | OCR 语言，逗号分隔 | `zh,en` |
| `describe_images` | 是否通过 GLM 识别已提取图片的可见文字；不改变已提取资产 | `false` |
| `description_language` | `zh-CN\|en\|auto` | `zh-CN` |
| `timeout_seconds` | `1..86400` | 服务默认值 |
| `prefer_async` | 仅 `/parse`；强制返回持久 Job | `false` |

`scan_policy=auto` 按页面自动处理扫描件；`skip` 不执行 PDF 扫描 OCR/表格抽取，保留 整页图像资产并输出明确的跳过状态。旧 `profile`、`mode`、`output_format`、`vlm_policy`、 `enable_vlm_fallback`、`preserve_page_breaks`、`include_pages`、 `include_diagnostics` 和 `include_renderings` 均返回 422。

`NATIVE_PARSER_BACKEND` 是服务端原生解析后端配置，不是公共请求参数。切换独立 Docling 后端与 Advanced＋TXT 后端保持相同 HTTP/MCP 输入、状态、Job ID、资产 URL 和 Markdown 媒体类型。MinerU 后的独立 Docling 二次复核已从实现中移除，运行配置和现场身份核验见[运行手册](../operations/runtime-recipes.md#5-检查升级与故障定位)。

`SEMANTIC_TABLE_OUTPUT_ENABLED` 是已有服务端开关，默认 `1`。当前仅转换部分完整来源网格及作用域，设为 `0` 会保留 GFM 显示，用于内部对照；两个值均不能证明满足完整最终契约。目标最终转换是正常交付步骤，不提供通过关闭语义转换获得合格最终结果的模式；本轮未新增参数或修改开关行为。

## 同步与异步

```bash
curl --fail-with-body http://localhost:12303/v1/content/parse \
  -H "Authorization: Bearer $API_KEY" \
  -F file=@report.pdf \
  -F scan_policy=auto
```

小输入成功时返回 HTTP 200：

```http
Content-Type: text/markdown; charset=utf-8
X-Content-ID: job_...
Location: /v1/content/jobs/job_.../result
```

响应体为当前服务生成的 Markdown；当前表格语义实现的格式和语义覆盖须单独核对。视频、`prefer_async=true` 或超过同步限制的输入 返回 HTTP 202 `JobResponse`。`POST /v1/content/jobs` 始终返回 202；调用方轮询任务 到 `completed` 或 `partial` 后读取：

```http
GET /v1/content/jobs/{id}/result
Accept: text/markdown
```

`?download=true` 增加 `.md` 的 `Content-Disposition`。旧 `/rendering/{markdown|text}` 已移除。

当前实现中，跳过的扫描 PDF 页不会输出失去行列归属的 OCR 数字，提示示例如下；其中物理页号属于现状，不是目标最终正文的格式：

```markdown
> 扫描页未处理（scan_policy=skip）：第 8 页，页面类型为 scanned。
```

对应整页图像可在结果末尾的“图片资产”列表或资产接口中取得。

## Markdown 输出

### 目标与当前实现

目标正文、数据表与网格排版的区分、图片交付、状态及完整输出包的要求统一见[输出契约](moparse-output-spec.md)，本文件不重复格式示例。图片语义化不在当前范围。

当前结果仍可能混合列表、GFM、物理页标记、页面家具和资产说明。具体缺口见[契约第 9 节](moparse-output-spec.md#9-当前实现差距与迁移)；HTTP 200、Job 终态或资产可下载不能单独证明契约通过。

来源作用域见[表格来源约定](table-source.md)，实际 GFM 显示语法和行映射见[架构说明](../engineering/architecture.md#表格显示映射)。显示行号不用于正文语义引用；历史结果保持原字节，不增加旧格式兼容分支。

### 表格关系与来源引用

本节描述当前表格关系引用与审计标记，不划分内部协议版本。它不定义另一份最终格式，也不支持凭 `converted` 或 `retained` 断言原件覆盖、图片交付或页面清理已完成。

`semantic-view` 开启描述作用域，声明视图身份、物理来源表身份和 `converted` 或 `retained` 状态。`semantic-source` 紧邻一条描述，引用其原始单元格及标题单元格；`table_id.rNcM` 的行列均从 0 起算，来自未插入语法表头的原始网格。跨页引用使用原页所属的表身份，不能按描述行号解释。

```markdown
<!-- semantic-view: id=example_t1; source-tables=example_t1; status=converted -->

<!-- semantic-source: cells=example_t1.r1c0,example_t1.r1c1,example_t1.r1c2; headers=example_t1.r0c1,example_t1.r0c2 -->

- 营业收入；2025 年度：1,234.50；2024 年度：1,100.00。
```

以上单元格引用为协议示例。真实输出的标签和值由引用读取，标题路径和单位、期间引用保存在内部关系记录；需要进一步核对时回到同一任务原件及内部审计。公开内容不携带完整坐标或重新生成的数值。

尚未转换的表格带 `table-fragment` 或 `logical-table`、`table-source` 和 `table-structure`，另给出 `status=retained` 以及“表格语义关系尚未确定，保留原表”的提示；这是未完成状态，不能按完整最终契约验收。成功转换的描述移除表格显示映射，段落只使用源格引用。

`semantic-summary` 声明已转换与保留的来源表片段数量，跨页逻辑组按各来源片段身份去重计数；结尾有可见的转换汇总。这是本次恢复出的表格片段计数，不证明原件真实表格均已检测，也不包含无法确定类型的隔离区域。Job 的 `completed` 或 `partial` 仍描述任务执行与来源处理状态，不能据此推定所有表格已完成语义转换。消费者必须分别读取语义覆盖。

内部 `logs/table-semantics.json` 使用用途标识 `mo-parse-table-semantics`，关系策略名为 `source-scoped-relations`；来源证据日志使用 `native-source-verification`，PDF 网格绑定策略名为 `vector-grid-glyph-binding`。这些名称不含协议版本，日志保存来源 SHA、显示与最终 Markdown SHA、关系引用、保留原因及阶段耗时，不作为公开结果或资产返回，也不替代原件内容正确性检查。

以下资产与识字说明属于当前实现；示例中的物理页展示不适用于目标最终正文。图片语义化明确不在当前范围，流程图和组织结构图按图片交付。Office 嵌图直接提取，原生 PDF 保留模型识别出的图片区域，扫描/混合页保留整页来源图；视频保留采样关键帧。已提取内容作为鉴权资产下载，原生 PDF 未检出的图片不会因此补齐。 `describe_images=true` 时，可见文字使用普通 Markdown 列表追加，不生成额外场景推断：

```markdown
## 图片资产

- **figure-1.png**（embedded_image，第 3 页，资产 ID：`asset_...`）：[下载](/v1/content/jobs/.../assets/asset_...)
  - 可见文字：图片内识别到的原文
```

独立图片和视频关键帧复用同一 GLM 识字服务。视频摘要按采样帧时间戳列出可见文字， 不推断未采样片段或无文字场景。独立图片/视频在 GLM 未启用或不可用时返回 `backend_unavailable`；文档已提取图片仍保留资产，按需识字失败以告警说明。

## Job、SSE、资产与 bundle

```text
POST   /v1/content/jobs
GET    /v1/content/jobs/{id}
GET    /v1/content/jobs/{id}/events
GET    /v1/content/jobs/{id}/result
GET    /v1/content/jobs/{id}/assets
GET    /v1/content/jobs/{id}/assets/{asset_id}
GET    /v1/content/jobs/{id}/bundle
POST   /v1/content/jobs/{id}/retry
DELETE /v1/content/jobs/{id}
```

SSE 是增量体验层，断线后以 Job JSON 为准。原生文档 worker 按整件返回结果， 中间阶段的页进度可能保持 0，Job 仍处于 `running`；它不提供逐页实时百分比。资产元数据含 MIME、SHA256、尺寸、角色、 状态和下载 URL，不含页位置或 bbox；视频支持单个 HTTP byte range。当前 bundle 仅包含 `manifest.json` 与资产文件，**不包含 `result.md`**，也没有可离线使用的 Markdown 图片引用。这是现有资产包行为；[目标输出包](moparse-output-spec.md#12-markdown-与图片的输出包)要求将同一正文与图片一起打包，尚待代码实现。

## MCP

`GET/POST /mcp` 暴露：

- `parse_content`
- `get_content_job`
- `get_content_result`
- `get_content_assets`

小结果在 MCP JSON 信封的 `content` 字段内携带 `text/markdown`；超过 MCP 字符限制 时返回同一个 HTTP 结果 URL。不存在单独的 rendering 工具。

## 错误协议

错误与任务控制仍使用 JSON：

```json
{
  "error": {
    "code": "validation_error",
    "message": "The request parameters are invalid",
    "request_id": "req_...",
    "details": {}
  }
}
```

常见状态：400（输入冲突/范围/URL）、401（认证）、404（Job/资产）、409（状态或旧 契约）、413（大小）、415（真实格式）、422（参数）、429（容量）、502（解析后端）、 504（超时）。

## Project name compatibility

The service name is `moparse`. HTTP routes, job IDs, result media types and asset URLs are unchanged by the rename. MCP uses `moparse://health`, `moparse://backends` and `moparse://usage`; existing `mosaicparse://` URIs continue to resolve to the same resources.
