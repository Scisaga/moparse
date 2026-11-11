# 管线输出与适配索引

每条管线的执行边界、原生对象与字段、媒体、研究侧读取、MO-Parse 适配逻辑、验证状态及核实依据均放在本组说明中，可独立阅读。八个固定比较配置仅在[待测管线](../../benchmark/pipelines-to-test.md)维护。

这里的“管线输出”指完整声明配置产生的原生结构、Markdown、媒体及状态。混合配置包含两个分支及其原始页序关联；一次 VLM 请求的文本、当前 worker 投影和 MO-Parse 最终正文分别核对。

2026-11-12的[架构与评测审查](../../benchmark/reports/lite/moparse-architecture-evaluation-review.md)已读取八组保存quality800原生JSON，确认应按Docling、GLM、Paddle、typed MinerU和visual五个格式族保留差异、共享无损交接和公共内容处理。下一阶段先抽取P01已验证的通用交接，以P01双分支与P05全页GLM横向验证，再验证P03/P04；P02作为V2差异接入，不复制整条服务链。当前P01专用分支、其余bridge和公共消费字段仍不完全一致，八组读到adapted不等于统一服务验收。该方向尚未实施，本轮没有修改adapter、IR或运行转换、回放及评分；具体边界和顺序由[技术路线](../engineering/technical-route.md)维护。

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

研究入口及共享读取代码位于[评测模块](../../moparse_eval/README.md)。本轮八组已按冻结身份各完成quality800一次和perf80三轮，原生测量及原MO服务恢复完成；旧评分及结论已删除；本轮按完整身份、候选上下文及源位置重新计算，实际完成范围以评测索引为准。结果只见[当前统一评测报告](../../benchmark/reports/lite/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS只观测不控制，先前撤回测量不恢复；执行和自动评分完成不表示内容、Gold、图片内容或生产部署已验收，机制证据由[执行层诊断](../../benchmark/diagnostics/README.md)维护。

## 共用规则

研究侧读取只转译原生已有信息，保存原表、页面信息及必要媒体，不补答案。服务适配可共享无损读取函数，再将内容交给用途判断、表格转换、图片保全和页面清理；原件补充保留在独立服务步骤并单独归因。媒体提取、裁图与导出须遵守各组来源权限，必要计算计入声明的解析处理边界。

原生结构和媒体先保全，再据实际内容设计适配及共同组装。上游字段不足时记录缺失，现有 IR 不足时明确扩展需要，不把 GFM 或某个有限内部模型规定为所有候选的入口。实施依赖见[技术路线](../engineering/technical-route.md)，运行组件见[架构](../engineering/architecture.md)。

## 保存结果的八管线服务适配

2026-11-11新增的P01单文档开发入口按当轮明确授权执行真实保存JSON到最终正文的转换，独立于下述八组正式执行门槛。它强制禁用原件和媒体字节访问，实际正文放在`service/current/p01/development/`，不修改正式`service/current/index.json`或既有P07/P08配对。范围、partial和证据由[P01说明](p01-docling-v1-glm.md)及[唯一报告](../../benchmark/reports/lite/report.md)维护；其他七组没有因此取得新的纵向验收结论。

工作区的[离线 bridge](../../moparse_eval/service_replay_native.py)现按已保存的实际页分支接入八组：P01/P02读取各自Docling文档树及GLM主视图，P03/P04读取各自Paddle页面区域，P05读取全页GLM主视图，P06/P07读取各自typed MinerU及GLM分支，P08读取视觉SDK块。这里没有重新运行converter、布局模型或识别模型，也不以raw审计视图补全主结果。后端原生对象仍独立保留；服务的表格和页面模型仅为消费投影，不能替代完整原生树、单元格引用、跨度、媒体、顺序及失败记录。

[来源守卫](../../moparse_eval/service_source_policy.py)按每页实际分支限制PDF补充：Docling/MinerU原生分支保留声明的字层与矢量来源许可，GLM、Paddle和纯视觉分支不进入字层或矢量服务，包括混合配置中的GLM页。具体来源许可仍由[配置说明](../../benchmark/pipelines-to-test.md#各配置的信息许可)维护；候选worker不挂载expected、没有网络或GPU，模型调用由NoInference硬拒绝。独立后处理保持8 CPU、8 GiB及外层串行；保存输出分析的16进程不改变这些资源。

[阶段审计](../../moparse_eval/service_stages.py)捕获实际adapted、source_pages、native_pages、exported、assets、semantic及final视图，保存各阶段的来源sidecar、适用页及未适用原因。adapted来自当时真实bridge页面，不是将faithful.md改名；相邻阶段的edit ledger保留实际字符串前后跨度及文字，只记录变换，不判断正确。未适用的来源阶段明确记录，不制造历史before。既有P07/P08 baseline/current实际正文不覆盖，P01-P06没有历史service baseline；新产物写入`service/executions/<执行身份>/pXX`，八组完成且同软件、同scope及结构门槛通过后，才可一次原子切换唯一`service/current/index.json`。

本次实现验证包含受控格式、引用、来源许可及原子选择反例，以及只读同一保存单页的八组JSON诊断；P01/P02/P03/P04/P05/P08已在宿主读取到实际adapted阶段且原生JSON未改，P06/P07的声明middle对象与页指针可读，但宿主缺固定`docvortex==0.5.16`，官方typed投影仍为依赖准备缺口，不能以研究Markdown替代。未读取原PDF或图片、未执行新CPU全量回放或评分；这些工程观察不构成转换质量、完整覆盖或部署验收。实际执行须等待当前expected结构门槛及固定环境预检，不能沿用旧诊断状态充当passed gate。

`prepare --validation <门槛文件>`可将同软件身份的`expected_structure_gate`写入新执行及worker plan，不启动候选；未提供门槛仍可准备工件，但不能实际warmup或measured。两种真实执行在启动容器前及worker入口都检查该门槛，warmup也不能使用已变化的软件；受控单函数测试不需要真实语料或容器。

## 核实状态

已修复的研究执行问题包括共享 GLM 的 MRoPE 配对错误、Paddle 颜色交接错误、旋转坐标混用的来源路由，以及局部异常影响已有原生结果与导出的问题。源码审计和受控探针支持限定的机制结论；八组各自完成当前[工程预检02](../../benchmark/runs/lite/preflight/)同一清单的11个输入任务，实际配置与直接单页标定记录作为本次冻结依据。这些工程证据不能生成解析质量成绩或排名，生产路径也不能据此被认定已修复或验收；各组边界见对应专文和[执行层诊断](../../benchmark/diagnostics/README.md)。

本轮[执行锁](../../benchmark/execution-lock.json)已据当前工程预检02冻结，八组的工程预检互不替代，不能沿用失效执行锁。完整页面执行、分支页序、方向、媒体、原生读回、失败隔离及资源约束的具体证据按组保存，质量与成本按[统一标准](../../benchmark/evaluation-tasks.md)测量。未提供字段、未读资源和未标注结构保持缺失或未知，执行完成不能替代来源内容验收。

研究执行器与评分读取已经独立实现，八组MO-Parse服务适配及最终转换没有因本轮评测获得新的验收结论。格式样本仍须区分正文、表格或网格、图片、页面角色、空白及失败；格式和读取验证不能代替完整原件上的解析质量比较。

最终 Markdown、图片和输出包由[输出规范](../specs/moparse-output-spec.md)定义；适配完成后仍需分别验证内容转换及组装。
