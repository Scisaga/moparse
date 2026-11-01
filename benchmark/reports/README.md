# MO-Parse 当前输出评测

**当前评分及业务验收结论存在已复现的软件缺陷，不作为采用依据。** [根因诊断](20261101-expected-only-06/root-cause-analysis.md)已经证明：expected单位构造会产生错误答案，候选读取会把已打印内容判丢失，转换器也存在真实单位绑定错误。此前139/211项只代表有缺陷程序的阶段判分差异，不能解释为真实信息损失总数。

[当前验证状态](20261101-expected-only-06/current-validation-status.json)记录12个独立合成样例中的8个契约违例。需先修复这些通用缺陷，再统一程序重评；不能修改expected、排除目标或人工改判。此前原生产物、CPU回放、评分JSON和计时保留不变，原始目标尚未完成。

## 已完成执行的历史记录

以下保留上轮执行口径和原始记录。其中“完成”描述程序运行与产物生成，原质量及业务验收声明已被上述诊断撤回采用依据。

本轮已完成expected唯一标准下的统一程序对照、P07/P08后处理回放、退化验证和报告复现。当前结果见[正式报告](20261101-expected-only-06/report.md)、[覆盖记录](20261101-expected-only-06/coverage.json)和[交付状态](20261101-expected-only-06/completion.json)。

评测范围是Lite所选800页、173个样本、44份文档和33个文档家族。每组13,525个目标，其中业务字段5,729个；10,524个expected内容元素全部进入程序对照，遗漏为0。八组原生输出和P07/P08三个正文版本共14组、2,422份样本评分，使用同一冻结程序，每项只判正确或错误。旧1,726字段是历史子集，不代表本轮范围。

04版是较早保存的最终Markdown，05版是本次修改开始时的最终Markdown，06版是本次CPU回放的最终Markdown；expected始终是同一答案依据。04到06，P07业务字段正确2,035到2,122，新增87；P08为2,005到2,070，新增65；原正确目标损失和字面退化均为0。这些变化包含前轮已实施的正文优化；本次单独补丁没有新增业务正确项，实际改善是P08的5处已关联附注数值包装，见[实际Markdown差异](20261101-expected-only-06/delivered-markdown-changes.md)。评分读取修复不算正文改善。

最终正文仍有业务字段错误：P07为3,607，P08为3,659。其中原生相同目标正确、最终Markdown错误的业务字段分别为139、211，逐项列在[转换错误](20261101-expected-only-06/conversion-errors.json)。其余完整错误及候选证据保存在正式运行的逐项评分和private/target-details.csv；阶段统计见[failure-stages.json](20261101-expected-only-06/failure-stages.json)。这些错误没有被排除；程序对照完成不表示全部输出正确。

P07/P08各完成800页CPU回放及固定80页三轮，预热单列；800页后处理分别耗时235.537秒、182.626秒。[成本摘要](20261101-expected-only-06/execution-cost-summary.json)保存原生历史处理与各版本CPU处理的独立记录，不相加冒充新端到端耗时。原生测量沿用TTS共驻且工作负载不受控的实际条件；本轮没有新模型推理、GPU或TTS操作、服务重启和部署。

最终软件回归2,373项通过、1项跳过；42份真实输出独立重评分的完整结果一致，13个指定生成报告产物逐字节复现一致。[复现方法](20261101-expected-only-06/reproduce.md)区分评分、正文处理和报告生成。Lite已用于开发，不能宣称独立未见测试集。

当前规则由[评测任务](../evaluation-tasks.md#current-task-expected-only)维护，工具入口见[moparse_eval](../../moparse_eval/README.md)，续做使用[任务提示词](../../docs/engineering/prompts/expected-output-optimization.md)。canonical expected保持只读；旧字段索引和人工原图排除不提供答案，也不改变本轮分母。原图回看57页、800页或剩余743页均不作为当前验收进度。

历史运行、旧口径报告和诊断保留原身份。本轮最终索引是`20261026-lite-v3/artifacts/scores/expected-only-06-final-r3/index.json`；此前expected-only诊断运行因读取缺陷被本轮取代，不作为采用依据。大型候选、软件快照、资源采样与逐项调试材料保留本地，Git只提交任务代码、正式摘要、图件和复现记录。Full和额外六份PDF仍未启动。
