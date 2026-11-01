# P01：Docling TableFormer V1 + GLM SDK

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

## 1. 配置与执行边界

原生页使用 Docling 2.139.0 TableFormer V1；扫描和混合页使用共享 GLM SDK。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

原生页的 Docling V1 文档对象、转换状态、错误与可用媒体，加上扫描/混合页的 GLM SDK 布局 JSON、Markdown 和实际可取得的图片。两部分保持各自结构，关联共同页清单、分支选择与方向变换；研究 Markdown 是按物理页关联后的忠实导出，不是 MO-Parse `result.md`。

### 2.1 Docling 文档

核对了项目安装的 `DoclingDocument` 及表格、图片、来源类型，并对照[官方文档](https://docling-project.github.io/docling/concepts/docling_document/)和[对应类型源码](https://github.com/docling-project/docling-core/blob/v2.101.1/docling_core/types/doc/document.py)。本地类型已拆分至多个模块，不能只看一个文件或一个 Markdown 示例。仓库接法见 [Docling 适配器](../../app/parsers/docling_standard.py)。

以下均为类型与访问路径示意，不是实际模型输出、完整 JSON Schema 或可直接反序列化的样本：

```text
ConversionResult
├── status / errors
└── document: DoclingDocument
    ├── body.children[] / groups[] -> 对象引用
    ├── texts[] -> label / text / prov[]
    ├── tables[].data -> table_cells[] / num_rows / num_cols
    ├── pictures[] -> 来源 / 图题 / 媒体引用
    └── pages[page_no] -> 页面尺寸
```

| 内容 | 原生载体与含义 |
| --- | --- |
| 文档及顺序 | `ConversionResult.document` 是 `DoclingDocument`；`body`、`groups` 和对象引用组织内容，`texts`、`tables`、`pictures` 是对象集合；集合排列不能代替阅读树 |
| 正文与角色 | 项的 `label`、文字、层级和 `content_layer`；正文与 furniture 可分别表达，角色是后端观测 |
| 来源 | `prov` 中的 `page_no`、`bbox`、`charspan`；页尺寸来自 `pages`，坐标必须读取 `coord_origin` 后转换，不一律按左上原点 |
| 表格 | `TableItem.data` 的 `num_rows`、`num_cols`、`table_cells`；源格有行列起止索引、`row_span`、`col_span`、文字、可选 bbox 及列头、行头和区段角色标记 |
| 图片及说明 | `PictureItem` 的来源、图题和继承的媒体引用；实际图片是否生成取决于导出与渲染配置，存在图片项不等于已有可下载文件 |
| 导出与失败 | `export_to_dict()`、`export_to_markdown()` 等派生视图；转换状态与错误另在转换结果中，不能只保存 `.document` 后丢弃状态 |

逐格跨度和角色从原生表读取，Markdown 只作对应显示。保留原生格式自带的 schema、版本及来源字段，不将它们改成 MO-Parse 的内部协议版本。现有 MO-Parse 服务适配器未启用 `generate_picture_images`，按位置生成图片候选后由服务裁图；研究执行器另行启用了原生图片生成与忠实导出，两者不是同一入口，图片候选也不等于已导出的图片字节。工程验证与图片内容验收边界见第 5 节。

### 2.2 GLM-OCR SDK 页结果

核对了安装的 `glmocr/parser_result/pipeline_result.py`、`postprocess/result_formatter.py` 和 `server.py`，并对照[官方 SDK 说明](https://github.com/zai-org/GLM-OCR)及[0.1.5 结果类型](https://github.com/zai-org/GLM-OCR/blob/v0.1.5/glmocr/parser_result/pipeline_result.py)。当前客户端见 [GLM SDK 接入](../../app/parsers/glm_sdk_remote.py)。

```text
PipelineResult
├── json_result -> JSON 字符串或结构，其中包含页面区域
├── markdown_result -> Markdown 文本
├── image_files -> 图片名到图像对象的映射，可选
└── original_images / raw_json_result 等已有信息

HTTP response
├── json_result / layout_details -> 同内容字段，不重复计入
├── markdown_result / md_results -> 同内容字段，不重复计入
└── 元数据字段；当前回包没有 image_files 图片对象
```

| 内容 | 原生载体与含义 |
| --- | --- |
| Python 结果 | `PipelineResult` 含 `json_result`、`markdown_result`、`original_images`，可带 `image_files`、原始结果和布局可视化 |
| HTTP 回包 | `json_result`/`markdown_result`，并提供 `layout_details`/`md_results` 同内容字段；`data_info.pages` 和 `usage` 可为空，不能借空值推算页数或成本 |
| 页面与区域 | 布局 JSON 可为序列化字符串；按页组织区域列表，区域含 `index`、`label`、`native_label`、`content`、`bbox_2d`，图片可有 `image_path` |
| 坐标与顺序 | SDK 区域框按 0–1000 表达，页与原 PDF 的对应由调用页清单确定；原生 `index` 表示该输出的顺序，不是全 PDF 页码 |
| 表格 | `content` 可以是 HTML 表格或 Markdown；HTML 中已有的单元格、跨度和角色可读取，Markdown 未提供的源格位置与表头关系不能猜补 |
| 媒体与失败 | Python 的 `image_files` 是图片名到图像对象的映射；本次检查的 HTTP 返回只传 JSON/Markdown，没有传这些图片字节，也未暴露全部原始阶段状态 |

这是 SDK 后处理后的产物，格式器本身会清理内容、合并部分块并跳过部分空或失败内容；这些行为属于声明的 SDK，不能将 MO-Parse 再次清理计作同一能力。原始阶段数据若未从所用入口提供，明确记不可得，不根据最终文本推造。现有服务客户端以均分区域宽度构造的列边界只是显示几何，不能充当 SDK 识别出的真实单元格坐标或表头证据。研究执行器直接调用 Python SDK，分别保存 `json_result`、`raw_json_result`、`markdown_result` 和实际取得的媒体，绕开现有 HTTP 回包缺少图片对象的限制；调用入口提供这些字段并不证明本次样本已有媒体保全，见第 5 节。

### 2.3 表格字段补读

2026-10-28评分读回补齐TableCell已有的起止offset、行列标题角色、row_section与fillable，并保存表的尺寸和方向；通过唯一原生路径及所属表关联，不覆盖冻结执行观察。RichTableCell.ref的明确引用保留节点、边、文字项及媒体证据，唯一纯文字叶子另存native_rich_text，不改原cell.text，也不自动拼合混合内容。本轮候选原生产物未出现含ref的格，当前字段匹配不消费该补充文字，因此不能用引用补读解释本轮成绩变化。修复与评分边界见[本轮评分说明](../../benchmark/reports/lite/appendix.md#共同评分与目标覆盖)。

### 2.4 标题角色与级别来源

2026-10-27追踪正式worker内Docling 2.139.0和docling-core 2.101.1：readingorder_model调用add_heading时未传level，原生SectionHeaderItem因此使用默认level=1；官方Markdown序列化将该级别显示为二级标题。HeadingHierarchyOptions.enabled默认关闭，本轮执行器未开启该额外阶段。标题角色、默认显示级别和真实多级层次预测必须区分，不能因存在level或Markdown井号便认定恢复了文档标题树。GLM分支的固定类别格式化见[P05标题来源](p05-glm-sdk.md#22-标题角色与级别来源)。评分器只据已声明级别和原生顺序读取作用域，本轮heading_of成绩不单独证明模型具有多级树恢复能力。

## 3. 研究侧读取与导出

按 Docling 阅读树读取正文、表格和图片，GLM 按已确认的区域列表读取；保留原表、页面家具、图题和失败，不在拼接时额外执行服务的跨页合表或原件补值。序列化原生对象和媒体，不能只保留当前适配器转换后的页面 Markdown。

GLM 固定以 `json_result` 为主要评分视图，`raw_json_result` 是独立审计视图，不能按答案或样本择取更有利阶段。SDK formatter 会重编号并合并部分区域，未提供稳定的跨视图区域身份，因此完整 raw 阶段按自身原生顺序保存至 `views/pNNNN-glm-raw.md`，并在 `faithful.md` 明示为独立阶段；跨视图阅读顺序未知，不按几何接近或内容相似删重。官方完整 YAML 的 `skip` 保留图片，`abandon` 带来的识别覆盖限制照实记录；已有的 raw 文字和实际图片字节保留，未识别内容不从原件或 Gold 补入。

## 4. MO-Parse 适配逻辑

1. 验证每个原始物理页恰由声明分支处理一次；区域引用带上分支和原生项身份，隔离局部索引冲突。
2. Docling 读取源格与角色观测，GLM 读取 HTML/Markdown 和区域信息；两者分别做坐标变换，不将 GLM 显示列边界当源格。
3. 将来源支持的内容交给用途判定和表格关系转换，布局正文按顺序保留；图片及其出现位置交给组装，原图不做语义化。
4. 保留分支失败、角色未知和媒体缺失；后续补充来自原 PDF 时，单记服务来源及费用，不能改写本组原生结果。

## 5. 实现状态与验证项

P01研究执行路径已修复，[P01工程预检02](../../benchmark/runs/lite/preflight/)独立完成同一清单的11个任务并提供本次冻结依据。本组已完成quality800一次和perf80三轮，八组统一评分、首版报告及原MO服务恢复完成；结果只见[当前统一评测报告](../../benchmark/reports/lite/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS只观测不控制，先前撤回测量不恢复；执行和自动评分完成不构成内容、Gold或图片内容验收。

研究执行器显式使用 TableFormer V1，Docling 阅读树、表格、媒体和共享 GLM 分支分别保存，与 P02 的模型选择不同。共享 GLM 已显式采用 native rotary，避开 vLLM 0.19.1 的 GPT-J MRoPE CUDA 配对缺陷；研究路径的旋转坐标交接和原生结果先行保全、局部导出错误隔离已修复。机制证据与修复边界见[执行层诊断](../../benchmark/diagnostics/README.md)，不据工程修复推定具体语料影响或解析成绩。

本组预检与产物保留分支页序、方向、完整 ContentLayer、媒体和局部失败记录，供原生对象及忠实导出追溯；预检任务完成不等于逐项内容或图片内容已验收。MO-Parse生产GLM路径、服务适配及最终转换仍需独立修复和验收，未知表头关系和未标注结构不能由运行完成状态补认。

## 6. 格式核对依据

格式依据为已核对的安装包定义：`docling==2.139.0`、`docling-core==2.101.1`；`glmocr==0.1.5`。上述树形结构是类型与字段示意，不是完整 JSON Schema；实际运行身份由各次配置和工程预检原生产物记录，正式运行前须完成新一轮预检冻结，验证边界见第 5 节。

实现参考：[Docling 接入](../../app/parsers/docling_standard.py)；[GLM SDK 接入](../../app/parsers/glm_sdk_remote.py)。官方格式与源码链接在本页相应分支说明中列出。

以下为已核对源码文件的 SHA256，用于复查格式依据；模型权重及运行身份另行固定。

| 安装包源码文件 | SHA256 |
| --- | --- |
| `docling-core 2.101.1: types/doc/document.py` | `0f2f342b78a1ecea80dd41f3b38c8f8823164719e87e1709f54e5ff2b76b25eb` |
| `glmocr 0.1.5: parser_result/pipeline_result.py` | `08df09a66d423a57cf04613a0c83769067f2b98d4f0032824b4e3bc612b6198c` |
| `glmocr 0.1.5: server.py` | `7d260951738792d1d560997469b2d1b4ff7edcbcbd39001feb3b6f6dab7a12e3` |
| `glmocr 0.1.5: postprocess/result_formatter.py` | `df6a98e64a960bceda29632e39d3158786313906ae4a8e6b1a1a6cee9aaf6b94` |
