# MO-Parse 评测工具

本轮八组已按[冻结执行身份](../benchmark/execution-lock.json)各完成quality800一次和perf80三轮，原MO服务恢复完成。[原生比较报告](../benchmark/reports/20261026-lite-v3/report.md)的评分完成状态、采用结论与限制由[评测索引](../benchmark/reports/README.md)维护，执行完成不代表质量已完成判定。TTS按2026-10-26授权仅观测、不控制，先前撤回测量不恢复；自动评分不构成语料重新验收。协议由[评测标准](../benchmark/evaluation-tasks.md)维护，配置身份由[八管线计划](../benchmark/pipelines-to-test.md)维护，修复及验证边界见[执行层诊断](../benchmark/diagnostics/README.md)。

原件、Lite/Full数据包、冻结参考和作者标注保持原样，不重新生成或机械复核。Full不启动推理。GLM rotary、Paddle颜色接线、旋转路由与异常隔离已修复，并补足Paddle逐区域生成观测。八组在[当前工程预检02](../benchmark/reports/20261026-repaired-preflight-02/)共完成88项任务，其中64项独立单页标定全部成功；[执行就绪记录](../benchmark/reports/20261026-repaired-preflight-02/execution-readiness.json)保留实际配置、超时依据和Graph证据，并为本次冻结锁提供执行依据。这些记录只说明所测范围的执行就绪，不是页面质量评分或语料验收。

安装评分与开发依赖使用`uv sync --group benchmark --group dev`。解析SDK运行于独立固定镜像；`python -m moparse_eval.preparation --help`说明准备能力，准备结果不等于通过执行验证或可用于正式测量。依最新TTS观测策略重新预检，并冻结当时的代码、模型、镜像、资源、参数和Graph状态，不能沿用失效执行锁。各原生格式定义见[管线专文](../docs/pipelines/README.md)。

已有数据包无需重新包装。需要另建包装时，`package`只按人工清单复制资料、提取声明页，不选页、不生成答案、不判断内容正确。目标必须尚不存在，冻结不能由计数、哈希或格式检查代替。

```bash
python -m moparse_eval package --selection datasets/authoring/lite-selection.json --output /absolute/path/new-lite-package --source-root .
```

用户已授权继续新预检与八组评测，不再等待TTS维护确认。下面保留新目录调用形态：预检使用准备配置，正式命令须先完成新的预检与执行锁冻结；`--prepare-only`不启动解析，实际GPU维护只通过`--maintenance-window`进入，同名运行目录不能覆盖。评分须等完整八组执行、MO服务恢复和受测请求清理结束后进行；TTS变化或unknown不阻断执行、评分或报告，撤回产物不得评分或拼接。

```bash
python -m moparse_eval run --dataset datasets/moparse-dataset-v1-lite --suite preflight8 --pipeline all --config benchmark/execution-prepared.json --output benchmark/reports/new-preflight --prepare-only
python -m moparse_eval run --dataset datasets/moparse-dataset-v1-lite --suite preflight8 --pipeline all --config benchmark/execution-prepared.json --output benchmark/reports/new-preflight --calibrate-single-pages --maintenance-window
# Freeze a new execution-lock.json after the new preflight before this command.
python -m moparse_eval run --dataset datasets/moparse-dataset-v1-lite --suite lite --pipeline all --config benchmark/execution-lock.json --output benchmark/reports/new-lite --maintenance-window
python -m moparse_eval score --run benchmark/reports/new-lite
python -m moparse_eval report --run benchmark/reports/new-lite
```

正式Lite按同一冻结输入执行共同预热、每组800页一次及固定80页三轮。全部八组使用新执行身份；初始化、预热、解析、评分和报告分别计时。执行器只获得输入PDF、配置和输出目录，不能访问expected。一个管线worker跨样本保留SDK，外层并发1；受测后端共享16 GiB自有显存预算，TTS保持运行而其负载不控制，评测不启动、停止、重启或改配置。身份和活动仅观测，变化或unknown不作为运行及报告阻断条件；报告披露实际共驻、活动和观测覆盖，不宣称独占或TTS空闲。受测进程、TTS与整卡显存分别记录，归属未知保持NA。GPU 1维护结束、失败或取消时恢复原MO-Parse模型，GPU 0及其他项目不动。

`--calibrate-single-pages`仅用于预检：按既有三样本八页声明，在新预检目录复制页段并提取八份单页输入，同一SDK生命周期先执行页段、再直接测量单页，不读取参考或比较内容。提取不是语料验收。正式入口要求真实预检之后的新执行冻结记录，并核对冻结的软件身份，软件变更后不能沿用原锁。原生结构能力缺口保留为候选局部结果；适配和导出工程异常须先修复，不能把两者混为质量正确。

Paddle原生服务使用单个长期owner线程统一初始化、推理与关闭，并显式`use_queues=False`；识别区域边界按固定颜色策略将BGR转为PIL RGB，布局模型继续接收BGR。每个区域记录有效生成参数、长度与EOS观测，输出上限保持4096，未暴露的实际停止原因保持unknown，不修改输出或重试。GLM native rotary按明确服务配置启用，保留支持且经验证的CUDA Graphs；Paddle捕获例外由新预检保留真实证据和重启用条件，不能以两token试验替代完整生成回放。具体字段见[运行手册](../docs/operations/runtime-recipes.md)。

`score`只读冻结参考并写新评分版本，不提供语料检查或修复模式。主评测聚焦信息保全、内容准确和必要归属；结构、定位细节与字符差异作为诊断，未纳入冻结目标的内容单独披露覆盖边界，不形成第三种业务评分。既定目标遗漏或运行失败仍保留目标分母并判错；字符指标不能替代关键数值和关系正确性。DocVortex续接读回只读取明确原生声明，不补表头、期间、单位或内容。

当前主评测使用`mo-parse-eval-information-v5`，以expected的预期信息为中心。正文并列定位覆盖、已定位CER和字符覆盖；表格或正文记录均按实际表达的业务事实读取，分别报告值与业务标签、同时满足已标单位期间附注的完整信息正确率。所有已纳入目标完成正确或错误判定，路径分段、表格方向和格位差异不单独扣内容分；严格字符与结构诊断进入附录。完整分母和表达等价政策只维护在[评测标准](../benchmark/evaluation-tasks.md#4-指标与匹配)。

冻结并验证评分软件后，可用`score --run <run-directory> --freeze <scoring-freeze.json> --adjudications <existing-human-decision.json>`重评分已有产物。freeze记录软件身份、协议身份及通过的工程验证，入口拒绝身份不符或未通过验证的记录，评分结束再次确认软件未变。该操作不启动模型、不改写参考或执行观察，不回填原解析耗时；存在工程读回错误时不发布新的评分索引。原有人工排除决定继续统一适用，不能随重评分丢失。

独立人工参考排除决定保存在`benchmark/reference-decisions/`，不包含管线成绩。需要使用时给`score`显式传`--adjudications`；其记录和证据根约定见该目录说明，新run引用证据时须同时搬运记录指定的图片。迁移并不重新验收裁定或语料，也不改写冻结参考。只支持统一的`exclude_unit_pending`，不按管线选择答案。

`report`从新运行已有的评分和执行记录生成图文正文、完整附录、机器明细及图件，不能重生已撤销的旧比较。`field-details.csv`保存逐字段状态、限定信息证据及评分产物路径；未知定位原因不冒充原PDF缺项。图件仅使用对应新测量，保留800页单次与80页三轮的不同口径、版本、分母、开发暴露和缺测。字体采用DejaVu Sans与Noto Sans CJK，PDF嵌入字体。人工案例必须明确作者阅读范围，不能自动生成来源判断。

通用代码验证只使用合成材料，不打开真实语料或独立人工裁定。`datasets/`、`pdf_sample/`、`benchmark/reference-decisions/`和`benchmark/reports/`永久排除通用检查，包括显式路径调用。需要受控故障复现时使用[独立诊断探针](../benchmark/diagnostics/README.md)，这些结果不构成新的页面质量或吞吐成绩。

## P07/P08服务后处理的配对评测

`python -m moparse_eval.service_evaluation`独立处理有效P07/P08保存的原生结果，按[服务配对协议](../benchmark/evaluation-tasks.md#7-p07p08与mo-parse最终输出的配对评测)执行实际MO-Parse后处理。它不启动模型，不调用公开HTTP解析接口，不操作线上服务或TTS；候选容器只挂输入、原生产物、软件及不含参考的工作目录。正式输出、原始观察、评分派生观察和耗时分别保存，来源材料与参考保持只读。

新运行目录按`prepare` → `run --phase warmup` → `freeze` → `run --phase measured` → `freeze-scoring` → `score` → `report`执行；两个freeze命令都要求显式`--validation`工程验证记录，不能用文件存在或语料计数代替验证。`prepare`还需`--baseline`、`--output`和仅含公开处理参数的`--service-config`。服务执行与最终读回分别冻结身份，共享评分规则保持原样，旧运行目录不能覆盖。报告重生只读已有运行和评分JSON，不读取语料、重新推理或重新评分。

当前读取修正采用`mo-parse-eval-information-v5`，完整标准见[评测任务](../benchmark/evaluation-tasks.md)。每个已纳入业务目标只判正确或错误，全部目标完成判定后才能发布质量报告；评分器读取故障须先修复。`service_evaluation prepare --previous-run <旧运行>`只接纳同一原生输入、参考声明和已冻结执行身份的旧候选，读取原样保存的最终正文；候选worker不挂载旧结果或参考。评分冻结可单独更新只用于分析的共同读取与报告模块，实际适配、后处理、app及依赖仍须与执行冻结一致；必须同步重评原生、旧正文及新正文，不能复用旧分数。`prepare --rescore-native`允许在共同评分规则已修改时先准备候选回放；只放行评分模块差异，原生格式读取及依赖仍须一致，实际评分继续要求八组原生评分索引与当前完整软件身份一致，不能引用准备时的旧成绩。`python -m moparse_eval.table_context_report`逐项列出新增正确、原正确项损失及单位、期间、附注退化。

代码验证使用`python -m pytest -q tests/unit tests/test_markdown_policy.py moparse_eval/tests`。其中`test_information_context.py`覆盖单位、年度、分组和脚注正反例，`test_native_table_context.py`覆盖原生结构与局部转换，`test_moparse_eval_service_observation.py`覆盖实际正文读取及未渲染内部关系不得计分。它们使用受控合成材料，与真实候选专项评分、原页目读及运行成本测量分别记录；通过代码测试不构成语料验收。

最终表格读回直接解析交付Markdown中的HTML单元格及真实跨度；私有跨度或表格分类不能给没有打印跨度的GFM补分。单元格字符范围来自实际HTML源码，旧正文仍按其保存的字节及格式读取。原生、旧正文和新正文必须使用同一当前读取器重新评分。

共同读取器还读取实际记录中的字面单位字段名、范围内期间、普通文字形式的明确报告标题与表题。已有结构化单元格只补读同条实际打印记录中的限定，不重新猜测主体或重复产生候选值。短期间表题须以年度起始并包含本表实际表头文字，不能按期望值选择范围。单位不跨记录或套给比例，明确局部期间优先于共享报告年，冲突年份不强行取一；这些边界均有独立合成反例。
