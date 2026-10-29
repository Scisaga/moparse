# 管线输出与适配索引

每条管线的执行边界、原生对象与字段、媒体、研究侧读取、MO-Parse 适配逻辑、验证状态及核实依据均放在本组说明中，可独立阅读。八个固定比较配置仅在[待测管线](../../benchmark/pipelines-to-test.md)维护。

这里的“管线输出”指完整声明配置产生的原生结构、Markdown、媒体及状态。混合配置包含两个分支及其原始页序关联；一次 VLM 请求的文本、当前 worker 投影和 MO-Parse 最终正文分别核对。

## 管线索引

| 编号与说明 | 已有依据或代码 | 研究侧现状 |
| --- | --- | --- |
| [P01：Docling TableFormer V1 + GLM SDK](p01-docling-v1-glm.md) | 完整原生对象及GLM分支 | V1显式选择，阅读树、表格及媒体保存 |
| [P02：Docling TableFormer V2 + GLM SDK](p02-docling-v2-glm.md) | 与P01共享原生读取 | V2显式选择，独立配置身份 |
| [P03：全页 PaddleOCR-VL 1.5](p03-paddleocr-vl-1.5.md) | 官方完整页面执行器 | 研究侧颜色与线程交接已修复，P03独立工程预检完成 |
| [P04：全页 PaddleOCR-VL 1.6](p04-paddleocr-vl-1.6.md) | 同系列执行器及媒体读取 | 研究侧颜色与线程交接已修复，P04独立工程预检完成 |
| [P05：全页 GLM-OCR SDK](p05-glm-sdk.md) | SDK对象、媒体及局部失败 | 全页执行；主json_result与独立审计视图分开 |
| [P06：MinerU Standard + TXT + GLM SDK](p06-mineru-standard-glm.md) | 完整typed原生文档及GLM分支 | Standard显式入口、原物理片段及已有关系保存 |
| [P07：MinerU Advanced + TXT + GLM SDK](p07-mineru-advanced-glm.md) | 与P06共享格式读取 | Advanced显式入口，独立运行及分支记录 |
| [P08：MinerU 全页纯视觉 SDK + vLLM](p08-mineru-visual.md) | 完整PDF渲染及官方纯视觉SDK | 原生块先行保全、局部导出隔离已修复，独立工程预检完成 |

研究入口及共享读取代码位于[评测模块](../../moparse_eval/README.md)。本轮八组已按冻结身份各完成quality800一次和perf80三轮，统一评分、首版报告及原MO服务恢复完成。结果只见[本轮v3报告](../../benchmark/reports/20261026-lite-v3/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS只观测不控制，先前撤回测量不恢复；执行和自动评分完成不表示内容、Gold、图片内容或生产部署已验收，机制证据由[执行层诊断](../../benchmark/diagnostics/README.md)维护。

## 共用规则

研究侧读取只转译原生已有信息，保存原表、页面信息及必要媒体，不补答案。服务适配可共享无损读取函数，再将内容交给用途判断、表格转换、图片保全和页面清理；原件补充保留在独立服务步骤并单独归因。媒体提取、裁图与导出须遵守各组来源权限，必要计算计入声明的解析处理边界。

原生结构和媒体先保全，再据实际内容设计适配及共同组装。上游字段不足时记录缺失，现有 IR 不足时明确扩展需要，不把 GFM 或某个有限内部模型规定为所有候选的入口。实施依赖见[技术路线](../engineering/technical-route.md)，运行组件见[架构](../engineering/architecture.md)。

## 核实状态

已修复的研究执行问题包括共享 GLM 的 MRoPE 配对错误、Paddle 颜色交接错误、旋转坐标混用的来源路由，以及局部异常影响已有原生结果与导出的问题。源码审计和受控探针支持限定的机制结论；八组各自完成当前[工程预检02](../../benchmark/reports/20261026-repaired-preflight-02/)同一清单的11个输入任务，实际配置与直接单页标定记录作为本次冻结依据。这些工程证据不能生成解析质量成绩或排名，生产路径也不能据此被认定已修复或验收；各组边界见对应专文和[执行层诊断](../../benchmark/diagnostics/README.md)。

本轮[执行锁](../../benchmark/execution-lock.json)已据当前工程预检02冻结，八组的工程预检互不替代，不能沿用失效执行锁。完整页面执行、分支页序、方向、媒体、原生读回、失败隔离及资源约束的具体证据按组保存，质量与成本按[统一标准](../../benchmark/evaluation-tasks.md)测量。未提供字段、未读资源和未标注结构保持缺失或未知，执行完成不能替代来源内容验收。

研究执行器与评分读取已经独立实现，八组MO-Parse服务适配及最终转换没有因本轮评测获得新的验收结论。格式样本仍须区分正文、表格或网格、图片、页面角色、空白及失败；格式和读取验证不能代替完整原件上的解析质量比较。

最终 Markdown、图片和输出包由[输出规范](../specs/moparse-output-spec.md)定义；适配完成后仍需分别验证内容转换及组装。
