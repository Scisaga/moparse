# P04：全页 PaddleOCR-VL 1.6

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

## 1. 配置与执行边界

全部页由 PaddleOCR-VL 模型 1.6 的完整管线处理，不接 GLM 分支；与 P03 保持共同前处理和资源条件。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

全页 PaddleOCR-VL 1.6 的页面 JSON、原生 Markdown、图片及状态，仍由本组完整管线处理所有页。官方同系列接口只用于说明候选结构，不能直接认定与 P03 已冻结为同一输出格式。

### 2.1 PaddleOCR-VL 页结果

本节依据[官方完整管线说明](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)和[结果序列化源码](https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/inference/pipelines/paddleocr_vl/result.py)，核对日期为 2026-10-21；上游分支会变化。这里描述 P04 的候选接口；锁定实际包与模型后须确认字段和序列化形状，不能将模型名称 1.6 当作 Python 包版本或输出 schema 版本。

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

## 3. 研究侧读取与导出

使用本组实际包、模型与后端确认序列化结果；逐项核对相对 P03 的字段、区域标签、分组、格式化选项和媒体导出差异。差异应显式写入本条说明，不能在通用读取器里静默丢字段。

## 4. MO-Parse 适配逻辑

1. 先验证版本和输出字段；确认相同的部分再复用 P03 读取函数，差异只在明确的格式处理处解释。
2. 保留本组页清单、原文、表体、图题、多边形及其他已提供信息，不降格成仅供比较的 Markdown 再重建结构。
3. 分别判断数据表与网格排版，将确认的表格关系、布局正文、图片引用和页面角色交给服务转换与组装，同时保留本组缺口与失败；目标相同不表示与 P03 的原生字段必须相同。

## 5. 实现状态与验证项

P04 的依赖及模型锁、执行器和实际输出样本仍未就绪。需为 P03/P04 分别核对样本和适配行为，确认共同方向处理与输出适配规则一致；未发现差异时也记录核对依据，不凭模型宣传推定兼容。

## 6. 格式核对依据

格式依据沿用 2026-10-21 的静态核对：Paddle 官方候选接口，实际包和模型锁待确认。上述结构为类型与字段示意，完整配置的实际输出样本及适配验收状态见第 5 节。

官方接口与序列化源码见本页第 2 节。引用的浮动分支用于说明候选字段，不作为本组执行锁。
