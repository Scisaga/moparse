# MO-Parse 评测状态

质量定义为[三层各占1/3](../evaluation-tasks.md#three-layer-evaluation)：纯文本T、版面逻辑关系L、重要业务信息B，总分(T+L+B)/3。旧核心、成绩、排名、图件和P07/P08采用结论已撤回，不恢复或继承。

当前已实际替换参考解释、候选读取、分层判定、汇总、配对及报告入口，并建立独立反例、突变、五种SDK链及保存输出文字诊断。最终同版程序以16进程遍历173个选段、12组共2076条保存输出；结果为blocked，没有完整语义比较或可发布质量分。遍历和测试通过不能解除尚未支持的矩阵、紧凑指标、正文关系、续接和输入边界问题。

唯一报告为[lite/report.md](lite/report.md)，方法与具体文字证据见其附录及[三层格式诊断](../diagnostics/three-layer-native-readback.md)，本地完整轨迹为[当前诊断索引](../runs/lite/diagnosis/three-layer-current/index.json)。阻塞摘要只记录软件能力，不是候选错误率；正式质量、关键业务错误及转换收益/损失均暂停。

原生候选、实际baseline/current正文、原始处理时长和资源观测只读保留。本轮没有重新推理、改候选或语料，也没有视觉/PDF/OCR验收、模型/服务操作或部署。后续按[任务](../evaluation-tasks.md#current-task-expected-only)及[续做提示词](../../docs/engineering/prompts/expected-output-optimization.md)完成剩余实现、独立验证及同版正式重评。
