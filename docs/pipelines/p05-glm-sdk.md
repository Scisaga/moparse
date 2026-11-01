# P05：全页 GLM-OCR SDK

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

## 1. 配置与执行边界

全部页由 GLM-OCR SDK 完成布局和识别；不能用当前只处理扫描和混合页的服务分支代替。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

全部页的 GLM SDK 布局 JSON、Markdown、可用图片及执行状态。若使用 Python SDK，保留 `PipelineResult` 已有媒体；若使用现有 HTTP 入口，保留收到的完整回包，并单独说明图片获取方式和入口未暴露的信息。

### 2.1 GLM-OCR SDK 页结果

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

### 2.2 标题角色与级别来源

2026-10-27追踪正式worker内glmocr 0.1.5的ResultFormatter._format_content：按native_label处理标题，doc_title去除已有开头井号后固定加一个井号，paragraph_title固定加两个井号。纯合成格式化验证中，同一带三级标题语法的输入会分别被改成一级或二级标题；因此其级别来自布局角色和SDK规则，不是任意多级父子关系的直接预测。该机制同样适用于P01/P02/P06/P07的共享GLM分支。评分器按既有标题语法及原生顺序读取作用域，不将heading_of成绩视作完整文档标题树准确率。固定版依据见[官方格式器](https://github.com/zai-org/GLM-OCR/blob/v0.1.5/glmocr/postprocess/result_formatter.py)。

## 3. 研究侧读取与导出

全部页面均走 SDK，不能复用当前服务路由后仅有扫描页的结果充当 P05。逐页保留响应、区域顺序、表体和角色；将 JSON、SDK 对象与 HTTP 中同内容字段的区别写清，避免重复计入相同文本或把空元数据当有效测量。

研究执行器直接使用 Python SDK，固定以 `json_result` 为主要评分视图，`raw_json_result` 为独立审计视图，不按答案或样本择取阶段。raw 阶段按自身原生区域顺序完整保存至 `views/pNNNN-glm-raw.md`，并在 `faithful.md` 明示独立阶段；formatter 重编号及合并后无稳定跨视图区域身份，跨视图阅读顺序未知，不按几何或内容近似删重。官方完整 YAML 的 `skip` 可提供图片，`abandon` 带来的识别前覆盖限制照实记录；已有文字和实际图片字节保留，未识别内容不补认。

当前客户端的 `_page_regions` 主要面对单页区域列表；服务端多结果包装可能再包含逐单元的 JSON 字符串或列表。全页读取必须先核对实际层次和页清单，再解析各页，不能把所有嵌套列表一律展开，也不能把现有单页读取函数直接当作整本 PDF 的结果读取器。

## 4. MO-Parse 适配逻辑

1. 用原始页清单绑定每份 SDK 结果，读取并校验实际区域结构；按已记录的方向变换回到来源位置。
2. 保存 HTML 的真实跨度与文字，Markdown 只作派生显示；SDK 缺少源格坐标或表头角色时明确未知，不使用均分列框替代。
3. 按 `image_path` 与 SDK 图片集合建立引用；HTTP 没有图片字节时，由声明的页面图像及区域裁图保全，区分 SDK 媒体与服务补充。
4. 畸形区域只隔离自身，保留有效邻居与原始内容；正文和布局网格按用途处理，页面家具角色参与后续清理判断。

## 5. 实现状态与验证项

P05研究执行路径已修复，[P05工程预检02](../../benchmark/reports/20261026-repaired-preflight-02/)独立完成同一清单的11个任务并提供本次冻结依据。本组已完成quality800一次和perf80三轮，八组统一评分、首版报告及原MO服务恢复完成；结果只见[当前统一评测报告](../../benchmark/reports/20261101-preservation-repair-08/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS只观测不控制，先前撤回测量不恢复；执行和自动评分完成不构成内容、Gold或图片内容验收。

vLLM 0.19.1 的 MRoPE CUDA 快路径忽略 GLM-OCR decoder 所需 GPT-J 相邻配对的缺陷，已由研究配置显式使用 native rotary 绕开，并保留 CUDA Graphs；glmocr 0.1.5、FP16 和 repetition_penalty=1.1 保持原定义。P01/P02/P06/P07 的共享 GLM 研究分支使用同一修复，各组分别完成自身工程预检。机制证据及上游出处见[执行层诊断](../../benchmark/diagnostics/README.md)；算子及工程验证不能替代完整 SDK 的质量与成本测量，也不代表生产GLM配置已改变。

研究读取以 json_result 为主要视图，raw_json_result 独立保留，不跨阶段择优补认。研究路径已修复原生阶段保全和局部导出错误隔离，完整 SDK 配置、媒体交接及失败状态按本组证据追溯；现有生产服务客户端的 _page_regions 对部分畸形区域仍可能抛错，不能把研究侧修复当作该客户端已经修复或部署验收。收到响应或执行未知时不自动重试，SDK abandon 覆盖限制和未提供媒体仍按实际状态报告。

## 6. 格式核对依据

格式依据沿用 2026-10-21 的静态核对：`glmocr==0.1.5`。上述结构为类型与字段示意，完整配置的实际输出样本及适配验收状态见第 5 节。

实现参考：[GLM SDK 接入](../../app/parsers/glm_sdk_remote.py)。官方格式与源码链接在本页相应分支说明中列出。

以下为已核对源码文件的 SHA256，用于复查格式依据；模型权重及运行身份另行固定。

| 安装包源码文件 | SHA256 |
| --- | --- |
| `glmocr 0.1.5: parser_result/pipeline_result.py` | `08df09a66d423a57cf04613a0c83769067f2b98d4f0032824b4e3bc612b6198c` |
| `glmocr 0.1.5: server.py` | `7d260951738792d1d560997469b2d1b4ff7edcbcbd39001feb3b6f6dab7a12e3` |
| `glmocr 0.1.5: postprocess/result_formatter.py` | `df6a98e64a960bceda29632e39d3158786313906ae4a8e6b1a1a6cee9aaf6b94` |
