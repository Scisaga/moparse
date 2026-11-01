# MO-Parse 文档导航

按要解决的问题选择文档。每条解析管线的原生格式、字段、媒体和适配逻辑都在本组说明中；配置、接口与最终输出各有唯一归属。

| 需要了解什么 | 文档 | 内容归属 |
| --- | --- | --- |
| 最终交付什么 | [输出规范](specs/moparse-output-spec.md) | 正文、数据表与网格排版、图片、manifest、ZIP、覆盖与当前缺口 |
| 如何调用服务 | [API](specs/api.md) | 请求、认证、任务、下载、资产和当前公开行为 |
| 如何保存与使用来源 | [表格来源](specs/table-source.md) | 源格、跨度、标题作用域、跨页证据及审计 |
| 每条管线输出什么、如何适配 | [管线索引](pipelines/README.md) | P01–P08 各自的执行边界、原生格式与字段、媒体、读取、适配逻辑、验证状态及核实依据 |
| 下一步做什么 | [实施路线](engineering/technical-route.md) | 依赖、具体工作、交付物、缺口与完成条件 |
| 代码如何分工 | [架构](engineering/architecture.md) | 组件、处理流程、内部表示、持久化和实际调用边界 |
| 如何安装和运行 | [部署入口](operations/deployment.md) · [运行手册](operations/runtime-recipes.md) | 模式选择、配置归属、模型准备、启动、检查与回退 |
| 研究什么、如何作判断 | [研究框架](research/research-framework.md) | 解析与转换研究的问题、证据、评价方法及既有有界历史记录 |
| 使用哪套数据 | [Lite数据包](../datasets/moparse-dataset-v1-lite/README.md) · [Full数据包](../datasets/moparse-dataset-v1-full/README.md) | 资料范围、包内路径、审核状态、未知与开发暴露 |
| 如何执行和评分 | [评测标准](../benchmark/evaluation-tasks.md) · [评测工具](../moparse_eval/README.md) | 评价单元、分母、字符与关系指标、运行及重生命令 |
| 查看评测状态 | [当前统一评测报告](../benchmark/reports/20261101-preservation-repair-08/report.md) · [状态与限制](../benchmark/reports/README.md) · [执行层诊断](../benchmark/diagnostics/README.md) | 八组各完成800页一次及80页三轮，统一评分、首版报告与原MO服务恢复完成；TTS仅观测不控制，撤回测量不恢复 |

## 解析管线

| 编号 | 独立说明 |
| --- | --- |
| P01 | [Docling TableFormer V1 + GLM SDK](pipelines/p01-docling-v1-glm.md) |
| P02 | [Docling TableFormer V2 + GLM SDK](pipelines/p02-docling-v2-glm.md) |
| P03 | [全页 PaddleOCR-VL 1.5](pipelines/p03-paddleocr-vl-1.5.md) |
| P04 | [全页 PaddleOCR-VL 1.6](pipelines/p04-paddleocr-vl-1.6.md) |
| P05 | [全页 GLM-OCR SDK](pipelines/p05-glm-sdk.md) |
| P06 | [MinerU Standard + TXT + GLM SDK](pipelines/p06-mineru-standard-glm.md) |
| P07 | [MinerU Advanced + TXT + GLM SDK](pipelines/p07-mineru-advanced-glm.md) |
| P08 | [MinerU 全页纯视觉 SDK + vLLM](pipelines/p08-mineru-visual.md) |

八组比较配置、模型身份与资源条件以 [benchmark/pipelines-to-test.md](../benchmark/pipelines-to-test.md) 为准。Benchmark 只维护[评测任务](../benchmark/evaluation-tasks.md)、[待测管线](../benchmark/pipelines-to-test.md)和 [MinerU 调优](../benchmark/mineru-tuning.md)三份规划，不在管线说明中复制实验协议或成绩。

## 其他入口

- [仓库执行约束](../AGENTS.md)：授权、资源、语料范围和文档维护要求。
- [架构决策](adr/0001-faithful-gfm-for-downstream-extraction.md)：最终格式与文档职责的决策记录。
- [接入任务提示词](prompts/eventrail-moparse-integration-fix.md)：Eventrail 接入修复的任务说明。
- [品牌与图标](brand.md)：标志、图标与图形规范；共用插图保存在 `assets/`。
