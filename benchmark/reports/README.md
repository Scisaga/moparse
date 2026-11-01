# MO-Parse 当前输出评测

错误的旧评分、人工排除、旧报告分支及其产物已按2026-11-02用户要求直接删除，不归档。当前结果见[正式摘要](20261101-preservation-repair-08/summary.md)、[完整报告](20261101-preservation-repair-08/report.md)和[完成记录](20261101-preservation-repair-08/completion.json)。

当前范围为800页、173个样本、44份文档、33个家族。10,524个expected内容元素全部进入程序对照，遗漏0；每组14,672个目标，其中业务字段7,133个，每项只有正确或错误。八组原生与P07/P08三个实际正文版本共14组、2,422份样本评分，统一使用清理后冻结的canonical expected程序。

本次清理只重新评分保存输出，没有再次处理正文。下表仍比较06版与08版实际Markdown，所有数值都由当前程序重新计算。

| 管线 | 修改前正确业务字段 | 修改后正确业务字段 | 新增正确业务字段 | 原正确目标损失 | 原生到正文全部目标损失 |
| --- | ---: | ---: | ---: | ---: | ---: |
| P07 | 2,778 | 2,798 | 20 | 0 | 0 |
| P08 | 2,843 | 2,866 | 23 | 0 | 0 |

P07原生正确的7,851个内容目标和P08的8,017个内容目标全部保留，其中正确业务字段分别为2,449与2,502项。范围覆盖业务字段、标题、正文、单位和图题文字；见[信息保留](20261101-preservation-repair-08/native-preservation-summary.json)、[根因修复](20261101-preservation-repair-08/root-cause-resolution.md)和[实际正文变化](20261101-preservation-repair-08/delivered-markdown-changes.md)。

P07最终正文仍有4,335个业务字段错误，P08为4,267个；这些项目在原生输出阶段已不满足expected，继续保留在分母中。[逐项错误](20261101-preservation-repair-08/remaining-errors.json)提供expected位置、实际候选、原因及完整评分证据入口。

内存、显存和采样覆盖已补入[资源成本报告](20261101-preservation-repair-08/resource-costs.md)及完整报告。质量和耗时是800页口径，资源峰值覆盖原固定协议全程；工作容器内存与推理侧内存分列，受测显存仅计归属受测容器的进程，未相加独立峰值。当前八组在已声明的质量与四项成本观测向量中均有取舍，二维图只作投影。资源报告专项12项测试通过，质量评分软件及分数未改变。

原生历史处理成本与CPU后处理分别保存。P07/P08原800页CPU回放分别为216.087秒、194.046秒，固定80页各三轮且预热单列；此次清理不重跑后处理、不回填计时。原生测量中的TTS共驻和负载不受控按实际记录披露，本次无模型推理、GPU或TTS操作、服务变更和部署。

软件验证1,771项通过、1项跳过；12个独立契约反例通过。清理前后全部2,422份评分中的205,408项判定及证据一致，见[清理验证](20261101-preservation-repair-08/cleanup-verification.json)。另外56份完整评分独立复算一致，27个指定生成产物逐字节复现一致，方法见[复现说明](20261101-preservation-repair-08/reproduce.md)。Lite已用于开发，不宣称独立未见测试集。

有效原生输出与原始计时仍在20261026-lite-v3目录；04、06、08目录保留实际前后正文及执行记录，旧成绩已删除。当前评分索引为`20261026-lite-v3/artifacts/scores/preservation-clean-20261102/index.json`，工程冻结为`benchmark/diagnostics/expected-preservation-validation-20261102.json`。规则见[评测任务](../evaluation-tasks.md#current-task-expected-only)，工具见[moparse_eval](../../moparse_eval/README.md)，后续执行遵循[续做提示词](../../docs/engineering/prompts/expected-output-optimization.md)。
