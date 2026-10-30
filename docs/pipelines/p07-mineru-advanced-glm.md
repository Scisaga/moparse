# P07：MinerU Advanced + TXT + GLM SDK

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

## 1. 配置与执行边界

原生页使用 MinerU 4.0.12 Advanced/TXT，关闭 image_analysis；扫描和混合页使用共享 GLM SDK。与 P06 仅改变 tier。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

Advanced/TXT 原生页的完整 MinerU 原生结构、Markdown、媒体与状态，加上与其他混合配置一致的 GLM 页结果。当前 MO-Parse worker 的传输投影与这组目标原生产物之间仍有信息保存差距。

### 2.1 MinerU PDF 解析结果

核对了安装的 `mineru/parser/base.py` 和 `docvortex/schema.py`，对照[官方 SDK](https://opendatalab.github.io/MinerU/usage/sdk_api/)及[输出说明](https://opendatalab.github.io/MinerU/reference/output_files/)。本轮只读取定义，没有调用解析或 `save()`；原生 schema 及其版本属于上游，应照实保存。

```text
ParseResult
└── middle_json
    ├── metadata / extensions / is_full_document
    └── pages[]: PageInfo
        ├── page_idx
        └── blocks[] -> type / index / bbox / 嵌套 content

markdown() / structured_content() / to_json() -> 不同派生表示
save(writer) -> 物化可用素材并保存多种原生表示与图片
```

| 内容 | 原生载体与含义 |
| --- | --- |
| 文档对象 | `ParseResult.middle_json`，通过 `pages` 访问页面；原生结构含元数据、扩展、完整文档标志及页面，不是旧式 `pdf_info` |
| 页面与块 | `PageInfo.page_idx` 从 0 起算；`blocks` 保留块顺序、`index`、`type` 和嵌套内容；文本可为行内 span，不能假设所有 `content` 都是字符串 |
| 表格与图像 | 表格容器含 body、caption、footnote 等子块，表体可为 HTML；图片、图表和其他视觉容器保留媒体或来源区域；附注不能随表体替换而丢弃 |
| 位置与角色 | 块 bbox 是 0–1 归一化框；已有 header、footer、page_number 等角色及延续观测应保留，不由显示位置直接推定语义 |
| 表格续接 | 顶层 `TableBlock.continues_prev` 为布尔值或空值，`cell_merge` 为0/1列表或空值；前者声明续接，不等于完整表头、期间、单位或值绑定，空值不证明合并完成 |
| 输出方式 | `to_dict()`/`to_json()`、`markdown()`、`structured_content()` 和 `save(writer)` 含义不同；后者可物化媒体并保存多种结果 |
| 媒体边界 | PDF 的普通 JSON 序列化会省略 `image_base64`，因此仅保存 JSON 不是完整媒体包；必须检查素材及真实引用是否就绪 |

当前 [native worker](../../native_worker/server.py) 把原生块投影成 `mineru-native/1` 回包，附加页尺寸、块 Markdown 和 `source_images` 区域，且省略图像二进制。这个标记是现有传输定义，不是八组共同模型或新的内部版本。保存当前 worker 回包不能自动证明完整上游产物、元数据及媒体都已保全；当前回包也不等于本组完整的原生与 GLM 分支组合输出。

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

这是 SDK 后处理后的产物，格式器本身会清理内容、合并部分块并跳过部分空或失败内容；这些行为属于声明的 SDK，不能将 MO-Parse 再次清理计作同一能力。原始阶段数据若未从所用入口提供，明确记不可得，不根据最终文本推造。现有客户端以均分区域宽度构造的列边界只是显示几何，不能充当 SDK 识别出的真实单元格坐标或表头证据。

### 2.3 标题角色与级别来源

2026-10-27追踪正式worker内MinerU 4.0.12和DocVortex 0.5.16：Advanced/xhigh先取得视觉SDK的标题块，再由完整PDF管线的本地布局区分doc_title和paragraph_title，并赋级别1或2；DocVortex按已有level导出标题。固定版依据为[标题角色与级别赋值](https://github.com/opendatalab/MinerU/blob/b7f3dd0c5f6e6d66a298239ffd02b328b873918e/mineru/backend/analysis/pdf/normalization.py#L44-L64)。因此本组相对P08的标题关系证据来自额外布局处理，不是相同视觉模型天然输出了一棵多级树。GLM分支见[P05标题来源](p05-glm-sdk.md#22-标题角色与级别来源)。

完整MinerU另有默认关闭的LLM title_leveling后处理，仅在该特性开启且输入标为is_full_document时执行，需要独立模型、连接和调用成本；当前执行器未显式开启。它与视觉SDK采样或导出开关不同，不能为既有测量追补为免费能力。固定版处理边界见[文档后处理](https://github.com/opendatalab/MinerU/blob/b7f3dd0c5f6e6d66a298239ffd02b328b873918e/mineru/backend/postprocess/llm_aided.py#L18-L27)。本轮heading_of只评价既有级别和原生顺序支持的作用域，不证明真实多级树恢复。

## 3. 研究侧读取与导出

以实际 `ParseResult` 和媒体物化结果为依据，再确认 worker 需要传递什么；原生完整内容与传输投影分别保留身份。投影附带的 Markdown、几何和 `source_images` 不能替代被省略的上游元数据、原始结构或图片文件。

GLM 固定以 `json_result` 为主要评分视图，`raw_json_result` 为独立审计视图，不按答案或样本择优。完整 raw 阶段按原生区域顺序保存至 `views/pNNNN-glm-raw.md`，并在 `faithful.md` 明示独立阶段；formatter 重编号及合并没有稳定跨视图身份，跨视图阅读顺序未知，不按几何或文字近似删重。官方完整 YAML 的 `skip`、识别前 `abandon` 及覆盖限制照实记录；已有文字和实际媒体保全，未识别内容不补认。

## 4. MO-Parse 适配逻辑

DocVortex 0.5.16的官方`render._internal.common.planner._merge_continued_table_blocks`把显式continues_prev=true解释为同一原生文档内最近前序表的跨页续接。研究评分只读取这一已有声明及明确文档、page_idx、顶层index身份，保留原物理片段，不执行渲染器的HTML合并。没有唯一前件或身份冲突时保持未知，不从相似文字、列数或位置选择前件。表对连接和先后方向按[统一标准](../../benchmark/evaluation-tasks.md)分开评价；这些字段不能用于替候选补出业务语义。

1. 对照原生结构清点现有 worker 保留、变换及未传递的内容，先补无损交接，再使用远程读取逻辑。
2. 读取嵌套表体、caption、footnote 和行内内容；原生图像由实际媒体引用关联，不根据占位符数量推定完整覆盖。
3. 使用共享 GLM 分支读取并按原页组合；当前 [MinerU 客户端](../../app/parsers/mineru_native_remote.py)的 HTML→GFM 和角色标记属于已有显示转换，不是共同语义中间层。
4. 原 PDF 表格来源补充、用途判断、最终表格描述与页面清理单记为 MO-Parse 工作；保存补充前结果，不能归为 MinerU 原生恢复。

## 5. 实现状态与验证项

2026-10-30工作区直接消费HTML单元格、rowspan、colspan和来源身份，按明确字段或计量记录建立局部范围，原生正文的表前说明、表题、期间与附注通过文字引用保留。嵌套原生列表按其段落顺序读取，末项明确年度说明以实际文字切片建立期间，下一同级编号结束范围；不从邻页或参考补年。整行合并的分组名与同期间的币种列身份进入实际正文，比例值不接受金额单位；算术调节结束范围不明的局部仍保留原表，规则见[表格来源](../specs/table-source.md)。完整PDF格网作为独立补充，已发现的来源冲突仍阻断转换。已有数字和关系在实际最终正文中表达；原生丢失的视觉层级不按公司或文件特例补造。开发回归、独立原页目读及正式回放分开记录，尚未部署。

2026-10-29工作区增加最终正文处理：采用typed正文块明确的`continues_prev`，只连接有唯一相邻前件的正文，不跨标题、表格或图片；生产者页标记、分页控制、表格处理注释和处理统计移出业务正文，内部保留精确编辑记录。只按明确页码角色及受限的重复页眉规则清理，签章日期、数字业务抬头及页脚业务文字保留。原生文字补充与表格转换后的正文使用同一发布步骤；未解决表格保留原内容并传递partial。对照P07原生输出的本轮评测按[配对协议](../../benchmark/evaluation-tasks.md#7-p07p08与mo-parse最终输出的配对评测)执行，实际结果由评测索引维护；工作区实现不代表线上部署。

明确的typed加粗span在最终正文中采用有效的strong标签，避免中文标点导致星号成为可见业务文字；只有与既有渲染精确对应的简单span参与此转换。原生正文补充要求水平范围与正文锚点可比，跨栏标题不能插进窄栏段落中。已确认数据表的内部月份范围建立独立期间作用域，项目与唯一明确主体列保留为复合行身份；具体正反例及读取器修复见[服务保全诊断](../../benchmark/diagnostics/service-postprocessing.md#2026-10-29p07和p08的连续正文适配)。

2026-10-28的服务客户端修复隔离MinerU与GLM已收到的局部格式错误，保留有效邻居、原始块及未知候选；worker官方渲染的局部错误也不再阻断其他块。HTML读取拒绝把多根或嵌套表解释为一张网格，显式sup/sub边界保留。实现与合成证据见[服务保全诊断](../../benchmark/diagnostics/service-postprocessing.md)；这些修改尚未部署，不改变下面研究测量的执行身份或分数。

P07研究执行路径已修复，[P07工程预检02](../../benchmark/reports/20261026-repaired-preflight-02/)独立完成同一清单的11个任务并提供本次冻结依据。本组已完成quality800一次和perf80三轮，八组统一评分、首版报告及原MO服务恢复完成；结果只见[本轮v3报告](../../benchmark/reports/20261026-lite-v3/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS只观测不控制，先前撤回测量不恢复；执行和自动评分完成不构成内容、Gold或图片内容验收。

研究执行器显式使用 tier=advanced，实际映射为 xhigh，与 P06 的 Standard/high 不同。共享 GLM 研究分支已采用 native rotary，避开 vLLM 0.19.1 的 GPT-J MRoPE 配对错误；MinerU 主模型的 NeoX 配对不具有同一冲突，不对其套用 GLM 修复。研究路径的旋转坐标交接、分支结果先行保全及局部图片导出隔离已修复；机制证据见[执行层诊断](../../benchmark/diagnostics/README.md)。

完整 middle_json、页级读取、忠实导出与媒体状态分别保留，后续异常不得抹掉已有有效页。SDK 恢复物理页号和连续页续接保护的源码依据不证明具体表头或跨页关系正确。本组工程预检使用自身 Advanced 配置及可写锁目录，保留 typed blocks、原页序、方向、GLM交接和清理记录，不借用 P06 的产物；共用读取代码及工程任务完成不能代替内容、媒体或服务转换验收，生产服务配置保持原样。

## 6. 格式核对依据

2026-10-31工作区的共同表格后处理保留partial剩余片段的实际跨度，并在本表明确附注绑定支持时转写文本数学标签。来源约束见[表格证据规则](../specs/table-source.md)，实际回放与内容目读范围见[评测索引](../../benchmark/reports/README.md)；不据软件测试宣称全部Lite页面通过内容验收。

格式依据沿用 2026-10-21 的静态核对：`mineru==4.0.12`、`docvortex==0.5.16`；`glmocr==0.1.5`。上述结构为类型与字段示意，完整配置的实际输出样本及适配验收状态见第 5 节。

实现参考：[MinerU 远程读取](../../app/parsers/mineru_native_remote.py)、[native worker](../../native_worker/server.py)及[依赖锁](../../native_worker/requirements.lock.txt)；[GLM SDK 接入](../../app/parsers/glm_sdk_remote.py)。官方格式与源码链接在本页相应分支说明中列出。

以下为已核对源码文件的 SHA256，用于复查格式依据；模型权重及运行身份另行固定。

| 安装包源码文件 | SHA256 |
| --- | --- |
| `glmocr 0.1.5: parser_result/pipeline_result.py` | `08df09a66d423a57cf04613a0c83769067f2b98d4f0032824b4e3bc612b6198c` |
| `glmocr 0.1.5: server.py` | `7d260951738792d1d560997469b2d1b4ff7edcbcbd39001feb3b6f6dab7a12e3` |
| `glmocr 0.1.5: postprocess/result_formatter.py` | `df6a98e64a960bceda29632e39d3158786313906ae4a8e6b1a1a6cee9aaf6b94` |
| `mineru 4.0.12: parser/base.py` | `16d61cb51b93dece48306415cac256f0070e62730006e90e778cba51c0acee1b` |
| `docvortex 0.5.16: schema.py` | `f1cb73d0f29104df10a59e0663b2884059354ce59c531402a362a4415854b4f4` |
