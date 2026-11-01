# MO-Parse评测报告

唯一正式入口是[Lite比较报告](lite/report.md)：八组原生质量、处理耗时、内存及显存，以及P07/P08实际正文的修复前后比较。方法、目录角色、采样覆盖、开发暴露和复现命令见[附录](lite/appendix.md)，分项结果与采用门槛见[机器数据](lite/data/results.json)。

| 位置 | 保留内容 |
| --- | --- |
| `benchmark/reports/lite/` | 主报告、方法附录、图件、数据与证据入口，纳入Git |
| `benchmark/runs/lite/` | 本地保存的八组原生输出、原计时与统一评分，不纳入Git |
| `benchmark/runs/lite/preflight/` | 工程预检及执行冻结依据 |
| `benchmark/runs/lite/service/{earlier,before,after}/` | 较早、修复前、修复后的实际正文及CPU处理记录 |

五个原日期目录已按上述角色合并；原生输出、实际正文和原测量继续保留，重复报告和中间副本删除。原始记录中的旧路径与当前位置对应关系见[来源身份](lite/data/provenance.json)。错误旧评分逻辑、成绩与产物直接删除，不恢复或归档。

expected是唯一只读答案来源。统一程序只判正确或错误，遗漏和候选失败留在分母；评分软件故障必须修复后发布。详细规则见[评测任务](../evaluation-tasks.md#current-task-expected-only)，执行工具见[moparse_eval](../../moparse_eval/README.md)，继续优化须遵循[任务提示词](../../docs/engineering/prompts/expected-output-optimization.md)。
