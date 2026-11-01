# MO-Parse 当前输出评测

本轮读取与正文转换修复、统一重评及信息保留验收完成。当前结果见[正式报告](20261101-preservation-repair-08/summary.md)、[完成记录](20261101-preservation-repair-08/completion.json)和[根因与修复](20261101-preservation-repair-08/root-cause-resolution.md)。

范围为Lite所选800页、173个样本、44份文档、33个文档家族。每组14,672个目标，其中业务字段7,133个；10,524个expected内容元素全部进入程序对照，遗漏为0。八组原生及P07/P08三个正文版本共14组、2,422份样本评分，统一使用`canonical_expected_8`，每项只有正确或错误。旧1,726字段子集保持历史身份。

以下比较06版修改前正文与08版修复后正文；expected始终是同一只读答案来源。两组原生正确的全部内容目标在最终正文中均保留，业务字段、标题、正文、单位和图题文字均纳入门槛。

| 管线 | 修改前正确业务字段 | 修改后正确业务字段 | 新增正确业务字段 | 原正确项损失 | 原生到正文全部目标损失 |
| --- | ---: | ---: | ---: | ---: | ---: |
| P07 | 2,778 | 2,798 | 20 | 0 | 0 |
| P08 | 2,843 | 2,866 | 23 | 0 | 0 |

P07原生正确业务字段2,449项、P08为2,502项，全部保留。原生到正文的全内容目标保留见[native-preservation-summary.json](20261101-preservation-repair-08/native-preservation-summary.json)。实际Markdown变化见[修改实例](20261101-preservation-repair-08/delivered-markdown-changes.md)；评分器补读不算正文新增收益。

最终正文仍有业务字段错误：P07为4,335项，P08为4,267项；这些目标在原生输出阶段已不满足expected。逐项expected位置、实际候选与证据入口见[剩余错误](20261101-preservation-repair-08/remaining-errors.json)，完整判定和片段保存在正式运行的private/target-details.csv及逐样本评分中。

P07/P08各完成800页CPU回放和固定80页三轮，预热单列；800页后处理分别为216.087秒、194.046秒。[成本摘要](20261101-preservation-repair-08/execution-cost-summary.json)分别保存原生历史处理与CPU后处理，不相加作为端到端时间。原生测量沿用TTS共驻及负载不受控的实际条件；本轮没有新模型推理、GPU/TTS或服务操作，未部署。

工程验证2,427项通过、1项跳过；4个真实样本在14组中的56份完整评分独立复算一致，17个指定报告产物逐字节复现一致。方法和输入要求见[复现说明](20261101-preservation-repair-08/reproduce.md)。Lite已经用于开发，开发暴露保留在报告中。

此前06版的质量采用声明继续撤回，保留[缺陷诊断](20261101-expected-only-06/root-cause-analysis.md)及原执行记录。中间07版因表头回归未采用，见[拒绝状态](20261101-preservation-repair-07/current-validation-status.json)；其原生产物、候选和计时保留。当前规则由[评测任务](../evaluation-tasks.md#current-task-expected-only)维护，工具说明见[moparse_eval](../../moparse_eval/README.md)，续做使用[任务提示词](../../docs/engineering/prompts/expected-output-optimization.md)。
