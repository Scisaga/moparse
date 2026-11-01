# P03：全页 PaddleOCR-VL 1.5

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

## 1. 配置与执行边界

全部页由 PaddleOCR-VL 模型 1.5 的完整管线处理，不接 GLM 分支；研究使用原生 Transformers 推理后端，Python 包与模型 revision 由各次配置及原生产物记录，正式运行前须完成新一轮预检冻结，工程验证边界见第 5 节。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

全页 PaddleOCR-VL 1.5 的页面结果对象或其完整 JSON、原生 Markdown 与 Markdown 图片集合，关联每页实际输入图像、原 PDF 页号和方向变换。包含全部来源类别，不另挂 GLM 分支。

### 2.1 PaddleOCR-VL 页结果

本节依据[官方完整管线说明](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)和[结果序列化源码](https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/inference/pipelines/paddleocr_vl/result.py)，核对日期为 2026-10-21；上游分支会变化。这里描述 P03 的候选接口；锁定实际包与模型后须确认字段和序列化形状，不能将模型名称 1.5 当作 Python 包版本或输出 schema 版本。

```text
predict(...) -> 页面结果对象序列
├── json -> 当前官方示例中的 res 包装与实际页面数据
│   ├── 页面信息 / 尺寸 / model_settings
│   └── parsing_res_list[]
│       └── block_label / block_content / block_bbox / block_order 等
└── markdown
    ├── markdown_texts
    └── markdown_images -> 图片名或引用到图像对象的映射
```

| 内容 | 官方接口中的载体与含义 |
| --- | --- |
| 完整页结果 | `PaddleOCRVL.predict()` 产生页面结果对象，可读 `json`、`markdown` 并保存 JSON、Markdown；只调用 VLM 聊天接口不是本组完整解析 |
| 页面与布局 | JSON 中的页面信息、尺寸、有效配置和 `parsing_res_list`；图片输入的 `page_index` 可能为空，必须保留调用清单的原 PDF 页号 |
| 区域 | `block_label`、`block_content`、`block_bbox`、`block_id`、可空的 `block_order`；某些版本还有分组、多边形及跨页标识，存在时原样保留 |
| 坐标与表格 | 框或多边形绑定输入页面及其尺寸；表格内容按实际返回的 HTML/Markdown 读取，不把布局区域框等分成原生源格坐标 |
| Markdown 与图片 | `markdown_texts`、`markdown_images` 和可能的 `page_continuation_flags`；图片集合含真实图像对象，不能只保存文字或把布局可视化当业务图片 |
| 序列化差异 | 结果对象、JSON 的 `res` 包装和保存文件不必同形；格式化、忽略标签及选项会影响字段和文本，须以固定版本实物确认 |

研究导出检查是否默认忽略页眉页脚或特定标签，按已有区域保存完整内容；服务清理另做。跨页标志是候选观测，不直接授权段落拼接、继承表头或合表。可选图表理解不纳入当前服务范围，不额外开启图片语义化；已有原生附加内容仍保存在原始结果中，不扩展本轮关系评分。

### 2.2 标题角色与级别来源

2026-10-27追踪正式Paddle镜像内PaddleX 3.7.2的markdown_format_funcs.py：doc_title固定导出一级标题；paragraph_title有title_level时使用该声明，否则按标题内点号数量及固定偏移生成二级或更深标题。纯合成导出验证中，普通标题产生二级标题，1.2开头及普通文字含一个点号的标题均产生三级标题，说明这些级别可以来自软件格式规则。可选restructure_pages才调用额外层级分配，本轮逐页predict执行入口未调用该步骤。SDK已有标题语法可供评分器结合原生顺序读取作用域，但不能将heading_of成绩解释成模型已恢复真实多级树。

## 3. 研究侧读取与导出

先固定 Python 包、推理后端及 1.5 模型身份，再核对[本页字段说明](#21-paddleocr-vl-页结果)对应的真实包装和默认导出。保存原始 `parsing_res_list` 与可用图片，忠实导出已有内容；标签忽略设置造成的遗漏要从本组已有结构核对，不能从 PDF 原生文字补回。

## 4. MO-Parse 适配逻辑

1. 用调用页清单关联逐页结果；不以图片输入可能为空的 `page_index` 丢弃原始页身份。
2. 读取区域列表、顺序及可选分组，保留 `block_order=None` 等未知状态；不按 bbox 简单重新排序全部块。
3. 表格内容有 HTML 时保存单元格和跨度，仅有 Markdown 时明确结构缺口；用途判定独立于 `block_label=table`。
4. 保存 `markdown_images` 中的图片字节与引用，布局可视化另作诊断；正文、图片和页边角色进入服务组装与清理。

## 5. 实现状态与验证项

P03研究执行路径已修复，[P03工程预检02](../../benchmark/reports/20261026-repaired-preflight-02/)独立完成同一清单的11个任务并提供本次冻结依据。本组已完成quality800一次和perf80三轮，八组统一评分、首版报告及原MO服务恢复完成；结果只见[当前统一评测报告](../../benchmark/reports/20261101-preservation-repair-08/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS只观测不控制，先前撤回测量不恢复；执行和自动评分完成不构成内容、Gold或图片内容验收。

研究执行器、完整页面 native RPC 服务及薄读取器已实现。固定 PaddleX 3.7.2 路径的 BGR/RGB 交接缺陷已在研究路径修复；该问题与线程生命周期引发的宿主内存留存分开处理。模型及调用由长期线程统一持有，并显式使用 use_queues=False；本组独立工程预检不借用 P04 的产物，也不据此宣称内容或效率已验收。机制诊断见[执行层诊断](../../benchmark/diagnostics/README.md)。

HGNetV2 布局子模块不支持全局 SDPA，与 VLM 的 attention 设置分别配置；模型、processor 与原生注册名按冻结身份记录。颜色交接、区域 token/EOS 和截断、有效邻居、媒体、取消清理及资源状态由本组工程证据和运行记录分别追溯，不把任务完成当作逐项内容验收。CUDA Graphs 按真实有界捕获与推理记录描述，失败及 eager 例外保留；格式字段、工程预检或合成探针不能替代完整管线测量。

## 6. 格式核对依据

格式依据为 Paddle 官方候选接口的静态核对。上述结构是类型与字段示意，实际包、模型、镜像和执行参数由各次配置及工程预检原生产物记录，正式运行前须完成新一轮预检冻结；工程验证边界见第 5 节。

官方接口与序列化源码见本页第 2 节。引用的浮动分支用于说明候选字段，不作为本组执行锁。
