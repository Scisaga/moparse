# 管线输出与适配索引

每条管线的执行边界、原生对象与字段、媒体、研究侧读取、MO-Parse 适配逻辑、验证状态及核实依据均放在本组说明中，可独立阅读。八个固定比较配置仅在[待测管线](../../benchmark/pipelines-to-test.md)维护。

这里的“管线输出”指完整声明配置产生的原生结构、Markdown、媒体及状态。混合配置包含两个分支及其原始页序关联；一次 VLM 请求的文本、当前 worker 投影和 MO-Parse 最终正文分别核对。

## 管线索引

| 编号与说明 | 已有依据或代码 | 当前待完成项 |
| --- | --- | --- |
| [P01：Docling TableFormer V1 + GLM SDK](p01-docling-v1-glm.md) | Docling + GLM 的读取代码 | 完整组合、原生保存及适配验收待确认 |
| [P02：Docling TableFormer V2 + GLM SDK](p02-docling-v2-glm.md) | 与 P01 同族格式 | V2 显式选择、模型锁和实际产物待准备 |
| [P03：全页 PaddleOCR-VL 1.5](p03-paddleocr-vl-1.5.md) | 官方页面结果接口 | 1.5 的包、模型、执行器和样本待准备 |
| [P04：全页 PaddleOCR-VL 1.6](p04-paddleocr-vl-1.6.md) | 同系列候选接口 | 1.6 的包、模型、执行器及与 P03 的差异待确认 |
| [P05：全页 GLM-OCR SDK](p05-glm-sdk.md) | GLM SDK 对象及 HTTP 接入 | 全页执行、媒体传输和完整状态待落实 |
| [P06：MinerU Standard + TXT + GLM SDK](p06-mineru-standard-glm.md) | MinerU PDF + GLM 格式 | Standard 入口及完整组合待准备 |
| [P07：MinerU Advanced + TXT + GLM SDK](p07-mineru-advanced-glm.md) | Advanced worker 与客户端 | 原生结构和媒体保全、完整组合待确认 |
| [P08：MinerU 全页纯视觉 SDK + vLLM](p08-mineru-visual.md) | 官方纯视觉 SDK 源码 | 执行锁、全页执行器、媒体及适配待落实 |

## 共用规则

研究侧读取只转译原生已有信息，保存原表、页面信息及必要媒体，不补答案。服务适配可共享无损读取函数，再将内容交给用途判断、表格转换、图片保全和页面清理；原件补充保留在独立服务步骤并单独归因。媒体提取、裁图与导出须遵守各组来源权限，必要计算计入声明的解析处理边界。

原生结构和媒体先保全，再据实际内容设计适配及共同组装。上游字段不足时记录缺失，现有 IR 不足时明确扩展需要，不把 GFM 或某个有限内部模型规定为所有候选的入口。实施依赖见[技术路线](../engineering/technical-route.md)，运行组件见[架构](../engineering/architecture.md)。

## 核实状态

本轮完成静态格式核对与适配逻辑说明，未生成或冻结八组完整输出样本，也未验收八组服务适配。格式样本应覆盖本组实际会返回的正文、表格或网格、图片、页面角色、空白及失败状态；未提供字段保留缺失。格式和适配验证不能代替完整原件上的解析质量比较。

最终 Markdown、图片和输出包由[输出规范](../specs/moparse-output-spec.md)定义；适配完成后仍需分别验证内容转换及组装。
