# P06：MinerU Standard + TXT + GLM SDK

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

## 1. 配置与执行边界

原生页使用 MinerU 4.0.12 Standard/TXT，关闭 image_analysis；扫描和混合页使用共享 GLM SDK。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

原生页 `tier=standard`、TXT 的 MinerU `ParseResult`/MiddleJson、Markdown 与实际媒体，以及共享 GLM 分支的页结果。二者按完整配置共同结束，不能把 Standard 的单个返回对象当作整份 PDF 的组合输出。

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

## 3. 研究侧读取与导出

按 [MinerU PDF 格式](#21-mineru-pdf-解析结果)读取 Standard 的嵌套 typed blocks、行内 span、表体、caption、footnote、媒体和元数据，保留 GLM 分支原始结果。没有保存媒体的 JSON 或当前 worker 的 Advanced 回包都不能冒充本组完整产物。

## 4. MO-Parse 适配逻辑

1. 显式验证 Standard 的实际入口与配置；复用字段读取代码时保留本组 producer、tier、页号和来源身份。
2. 使用原生 renderer 或明确的 typed-block 读取保存富文本、公式、列表和附注，不能把嵌套 `content` 一律转字符串。
3. 表体 HTML 解析和表格用途、角色判断分开；保留完整物理片段，只有完整延续证据才建立跨页关系。
4. 图像和页面角色保留真实来源，按原物理页组合 GLM 分支，分别报告原生失败、读回缺失与服务转换未完成。

## 5. 实现状态与验证项

当前 worker 的 tier 固定为 Advanced，P06 入口与真实输出待准备。需验证 Standard 的类型和媒体、与 P07 共享读取代码的边界、完整页组合及缺失状态，不能通过改组名或借用 P07 样本证明实现。

## 6. 格式核对依据

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
