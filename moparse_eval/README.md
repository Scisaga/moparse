# MO-Parse 评测工具

当前读取修复由独立契约反例约束：`.venv/bin/python benchmark/diagnostics/expected-preservation-probes.py`应退出0。评分及转换缺陷的修复见[根因与修复](../benchmark/reports/lite/appendix.md#正文修复与信息保留)。2026-11-02已按用户要求删除旧评分、人工排除、旧报告入口及其产物，不保留归档或旧格式兼容路径。当前工程冻结、统一重评和正文回放状态由[评测索引](../benchmark/reports/README.md)维护；canonical expected保持只读，不人工排除目标。

本次输出优化必须以`pdf_sample/parsing/expected/`中的现有expected为唯一验收标准。直接对照expected与被测实际输出，不查看原PDF图片裁决，不使用原图参考排除决定，不生成另一套答案，也不以原图理由改判或豁免差异。评分索引和已有1,726个字段仅是部分检查项，不能代替expected全部业务内容。完整规则见[当前验收标准](../benchmark/evaluation-tasks.md#current-task-expected-only)，续做使用[任务提示词](../docs/engineering/prompts/expected-output-optimization.md)。

检查和判分必须由同一程序对所有管线执行，统一expected范围、业务目标、分母、等价规则、异常政策及冻结评分版本。人工阅读用于诊断程序缺陷，不提供正式成绩或验收决定。不同格式可有忠实读取器，不能按管线身份设评分例外；共同修正后全部受影响组统一重评。八组原生结果横向比较，P07/P08后处理前后最终正文另作配对比较；评分器补读收益与实际正文改善分别报告，不将后处理结果与其他组原生结果混排。

当前程序入口使用`mo-parse-expected-only-v1`。`expected_readback`只读canonical expected及现有选段映射，用Markdown语法树读取完整选段；不读取旧评价文件的答案或人工裁定。`expected_evaluation`对八组保存原生结果及P07/P08保存的最终Markdown运行同一个评分器。最终正文读取不依赖私有IR，缺失候选保留目标并判错，软件读取故障阻止发布。

已有完整评分位于`benchmark/runs/lite/scores/current/index.json`。日常只需运行报告命令；它从同版评分与原资源测量生成唯一正式报告、方法附录、七组图件及机器明细，不读取expected、不重新判分。候选和测量保存在本地`benchmark/runs/lite/`，不进入Git。

```bash
.venv/bin/python scripts/render_lite_report.py \
  --index benchmark/runs/lite/scores/current/index.json \
  --output benchmark/reports/lite
```

需要独立重评分时，先冻结已通过软件验证的当前身份。下列`--output`必须尚不存在；只评分保存输出，不执行模型或后处理。生成的逐项结果、读取观察及变化证据保存在该运行的`private/`目录，再将报告命令的`--index`指向新索引。

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/runs/lite \
  --previous-root benchmark/runs/lite/service/earlier \
  --intermediate-root benchmark/runs/lite/service/before \
  --current-root benchmark/runs/lite/service/after \
  --freeze benchmark/diagnostics/expected-preservation-validation-20261102.json \
  --output benchmark/runs/lite/scores/new-reproduction --workers 8
```

`--previous-root`是较早保存的最终正文，`--intermediate-root`是本轮开始时已保存的最终正文，`--current-root`是本次代码CPU回放生成的最终正文；三者都不是expected。`--workers`只并行分析保存输出，不改变判分和原处理计时。最终覆盖清单按每个expected内容元素追溯至实际目标，编译器遗漏任一内容元素时拒绝发布。

`report.md`先呈现八组原生质量、耗时、内存和显存，再单列本轮修复前后的P07/P08实际正文。方法、采样覆盖、早期累计对照及复现命令放入`appendix.md`；不再并列维护摘要和日期报告。`data/results.json`保留完整分项与覆盖，`data/errors.json`定位逐项评分证据，`data/provenance.json`保存输入、评分软件和报告程序身份。资源峰值覆盖原固定协议全程，CPU后处理RSS另列；支配判断核对全部质量与成本维度，二维图只呈现投影。改变展示不改变评分软件身份，不重新推理或回填原处理计时。

读取器`canonical_expected_8`保留实际具名字段、复合主体、斜线路径、局部计量单位、年度说明及连续列表币种。具名数值不作为实体身份，业务词尾也不作为单位声明；完整目标标签和明确业务范围先定位，数值随后比较。同一事实中的不适用单位不能被另一条正确陈述掩盖，不同明确期间分别判定。标题、表号和单位说明可按自身语法约束相关字段，不能跨越其他正文或表格借用。

普通文字按完整字面在相邻可见文本中连续对照，允许标题与段落分块不同；逐段保留实际字符范围。表格、图片、已知物理页范围及实际阅读顺序限制连续视图，不能跳过插入的否定或其他文字，也不能从文字连续性建立业务字段关系。

采用同时要求正文版本间没有正确目标损失，以及原生正确的全部内容目标在当前实际Markdown中全部保留，业务字段另列。`private/native-preservation.json`列出原生到正文的每项损失，`adoption.json`保存两道门槛；报告会从逐项结果复算门槛，拒绝与实际判定不一致的采用声明。旧错误在多个正文版本中持续存在也不能通过采用。

`score --run ... --freeze ...`同样使用新入口，先完成八组原生对照，再将新索引写入该运行的`latest_scores`。P07/P08新候选准备要求已有完整expected-only原生索引；历史裁定不会继承，显式`--adjudications`立即失败且不打开裁定文件。评分协议仅由`expected_scoring.PROTOCOL`定义，原生、最终正文、冻结和报告共用该定义。工程检查通过与实际评测完成分别记录，当前运行状态见[评测索引](../benchmark/reports/README.md)。

本轮八组已按[冻结执行身份](../benchmark/execution-lock.json)各完成quality800一次和perf80三轮，原MO服务恢复完成。[当前比较报告](../benchmark/reports/lite/report.md)的评分完成状态、采用结论与限制由[评测索引](../benchmark/reports/README.md)维护，执行完成不代表质量已完成判定。TTS按2026-10-26授权仅观测、不控制，先前撤回测量不恢复；自动评分不构成语料重新验收。协议由[评测标准](../benchmark/evaluation-tasks.md)维护，配置身份由[八管线计划](../benchmark/pipelines-to-test.md)维护，修复及验证边界见[执行层诊断](../benchmark/diagnostics/README.md)。

原件、Lite/Full数据包、冻结参考和作者标注保持原样，不重新生成或机械复核。Full不启动推理。GLM rotary、Paddle颜色接线、旋转路由与异常隔离已修复，并补足Paddle逐区域生成观测。八组在[当前工程预检02](../benchmark/runs/lite/preflight/)共完成88项任务，其中64项独立单页标定全部成功；[执行就绪记录](../benchmark/runs/lite/preflight/execution-readiness.json)保留实际配置、超时依据和Graph证据，并为本次冻结锁提供执行依据。这些记录只说明所测范围的执行就绪，不是页面质量评分或语料验收。

安装评分与开发依赖使用`uv sync --group benchmark --group dev`。解析SDK运行于独立固定镜像；`python -m moparse_eval.preparation --help`说明准备能力，准备结果不等于通过执行验证或可用于正式测量。依最新TTS观测策略重新预检，并冻结当时的代码、模型、镜像、资源、参数和Graph状态，不能沿用失效执行锁。各原生格式定义见[管线专文](../docs/pipelines/README.md)。

已有数据包无需重新包装。需要另建包装时，`package`只按人工清单复制资料、提取声明页，不选页、不生成答案、不判断内容正确。目标必须尚不存在，冻结不能由计数、哈希或格式检查代替。

```bash
python -m moparse_eval package --selection datasets/authoring/lite-selection.json --output /absolute/path/new-lite-package --source-root .
```

## 历史原生执行示例

以下保留此前原生预检和测量的方法，本次输出优化只复用保存原生产物，不执行这些新预检、推理或GPU维护命令。当前授权边界以[续做提示词](../docs/engineering/prompts/expected-output-optimization.md)为准。历史执行中预检使用准备配置，正式测量先完成预检与执行锁冻结；同名运行目录不能覆盖，撤回产物不得评分或拼接。

```bash
python -m moparse_eval run --dataset datasets/moparse-dataset-v1-lite --suite preflight8 --pipeline all --config benchmark/execution-prepared.json --output benchmark/runs/new-preflight --prepare-only
python -m moparse_eval run --dataset datasets/moparse-dataset-v1-lite --suite preflight8 --pipeline all --config benchmark/execution-prepared.json --output benchmark/runs/new-preflight --calibrate-single-pages --maintenance-window
# Freeze a new execution-lock.json after the new preflight before this command.
python -m moparse_eval run --dataset datasets/moparse-dataset-v1-lite --suite lite --pipeline all --config benchmark/execution-lock.json --output benchmark/runs/new-lite --maintenance-window
python -m moparse_eval score --run benchmark/runs/new-lite
python -m moparse_eval report --run benchmark/runs/new-lite
```

正式Lite按同一冻结输入执行共同预热、每组800页一次及固定80页三轮。全部八组使用新执行身份；初始化、预热、解析、评分和报告分别计时。执行器只获得输入PDF、配置和输出目录，不能访问expected。一个管线worker跨样本保留SDK，外层并发1；受测后端共享16 GiB自有显存预算，TTS保持运行而其负载不控制，评测不启动、停止、重启或改配置。身份和活动仅观测，变化或unknown不作为运行及报告阻断条件；报告披露实际共驻、活动和观测覆盖，不宣称独占或TTS空闲。受测进程、TTS与整卡显存分别记录，归属未知保持NA。GPU 1维护结束、失败或取消时恢复原MO-Parse模型，GPU 0及其他项目不动。

`--calibrate-single-pages`仅用于预检：按既有三样本八页声明，在新预检目录复制页段并提取八份单页输入，同一SDK生命周期先执行页段、再直接测量单页，不读取参考或比较内容。提取不是语料验收。正式入口要求真实预检之后的新执行冻结记录，并核对冻结的软件身份，软件变更后不能沿用原锁。原生结构能力缺口保留为候选局部结果；适配和导出工程异常须先修复，不能把两者混为质量正确。

Paddle原生服务使用单个长期owner线程统一初始化、推理与关闭，并显式`use_queues=False`；识别区域边界按固定颜色策略将BGR转为PIL RGB，布局模型继续接收BGR。每个区域记录有效生成参数、长度与EOS观测，输出上限保持4096，未暴露的实际停止原因保持unknown，不修改输出或重试。GLM native rotary按明确服务配置启用，保留支持且经验证的CUDA Graphs；Paddle捕获例外由新预检保留真实证据和重启用条件，不能以两token试验替代完整生成回放。具体字段见[运行手册](../docs/operations/runtime-recipes.md)。

## 当前expected评测

`score`只读expected并写评分结果，不提供语料检查或修复模式。主评测聚焦信息保全、内容准确和必要归属；结构、定位细节与字符差异作为诊断，旧索引未覆盖的expected内容仍需完成对照，不形成第三种业务评分。既定目标遗漏或运行失败仍保留目标分母并判错；字符指标不能替代关键数值和关系正确性。DocVortex续接读回只读取明确原生声明，不补表头、期间、单位或内容。

当前只使用`mo-parse-expected-only-v1`，旧评分实现及成绩已经删除。正文定位及字符诊断、表格或正文中的业务字段分别统计；业务正确要求实际值、业务标签、单位、期间和附注满足expected。每个目标必须完成正确或错误判定，路径分段、表格方向和格位差异不单独扣内容分。完整分母和表达等价政策只维护在[评测标准](../benchmark/evaluation-tasks.md#4-指标与匹配)，旧子集成绩不构成当前任务完成声明。

冻结并验证评分软件后，可用`score --run <run-directory> --freeze <scoring-freeze.json>`重评分已有产物。freeze记录软件身份、协议身份及通过的工程验证，入口拒绝身份不符或未通过验证的记录，评分结束再次确认软件未变。该操作不启动模型、不改写参考或执行观察，不回填原解析耗时；存在工程读回错误时不发布新的评分索引。当前入口拒绝`--adjudications`，服务配对不继承历史排除记录；合成测试覆盖显式及隐式两条路径，实际统一评测单独记录。

`benchmark/reference-decisions/`保留历史人工记录，当前不以其中原图结论排除目标、修改参考答案或判定输出通过。旧`exclude_unit_pending`实现已删除；按现有expected完成的程序对照范围见当前评测索引。已有固定字段评分、测试通过和原图查看数量均不能证明expected全量覆盖。

统一评分完成后，正式报告由`render_lite_report.py`生成；CLI内置报告只留在本地评分目录，不作为另一份正式入口。逐项证据保存在评分JSON中，`data/errors.json`提供对应路径和目标ID；未知定位原因不冒充原PDF缺项。图件仅使用对应新测量，保留800页单次与80页三轮的不同口径、版本、分母、开发暴露和缺测。字体采用DejaVu Sans与Noto Sans CJK，PDF嵌入字体。人工案例必须明确作者阅读范围，不能自动生成来源判断。

通用代码验证只使用合成材料，不打开真实语料或独立人工裁定。`datasets/`、`pdf_sample/`、`benchmark/reference-decisions/`和`benchmark/reports/`、`benchmark/runs/`永久排除通用检查，包括显式路径调用。需要受控故障复现时使用[独立诊断探针](../benchmark/diagnostics/README.md)，这些结果不构成新的页面质量或吞吐成绩。

## P07/P08服务后处理的配对评测

`python -m moparse_eval.service_evaluation`独立处理有效P07/P08保存的原生结果，按[服务配对协议](../benchmark/evaluation-tasks.md#7-p07p08与mo-parse最终输出的配对评测)执行实际MO-Parse后处理。它不启动模型，不调用公开HTTP解析接口，不操作线上服务或TTS；候选容器只挂输入、原生产物、软件及不含参考的工作目录。正式输出、原始观察、评分派生观察和耗时分别保存，来源材料与参考保持只读。

新运行目录按`prepare` → `run --phase warmup` → `freeze` → `run --phase measured` → `freeze-scoring` → `score` → `report`执行；两个freeze命令都要求显式`--validation`工程验证记录，不能用文件存在或语料计数代替验证。`prepare`还需`--baseline`、`--output`和仅含公开处理参数的`--service-config`。服务执行与最终读回分别冻结身份，共享评分规则保持原样，旧运行目录不能覆盖。报告重生只读已有运行和评分JSON，不读取语料、重新推理或重新评分。

当前服务配对同样采用`mo-parse-expected-only-v1`，标准见[评测任务](../benchmark/evaluation-tasks.md#current-task-expected-only)。每个目标只判正确或错误，读取故障先修复。`service_evaluation prepare --previous-run <旧运行>`要求完整expected-only原生索引，接纳同一原生输入、参考声明及已冻结执行身份的修改前候选；候选worker不挂载旧结果或参考。候选执行继续冻结实际适配、后处理、app及依赖，公开Markdown的评分由单独冻结的共同程序完成。必须同步重评原生、修改前和修改后输出，不能复制旧分数；新增正确、原正确项损失及分项退化由`expected_report`从当前评分产物生成。原表格上下文报告工具已删除；原生与正文统一由正式报告生成器展示。

代码验证使用`python -m pytest -q tests/unit tests/test_markdown_policy.py moparse_eval/tests`。其中`test_information_context.py`覆盖单位、年度、分组和脚注正反例，`test_native_table_context.py`覆盖原生结构与局部转换，`test_moparse_eval_service_observation.py`覆盖实际正文读取及未渲染内部关系不得计分。它们使用受控合成材料，与对照expected的实际输出验收及运行成本分别记录；通过代码测试不代表expected中的业务内容已经验收。

`tests/unit/test_moparse_eval_pipeline_fairness.py`使用合成HTML与GFM正反例，把完全相同的候选分别标为P01-P08，要求全部判分和证据一致，覆盖年份交换、单位错误、符号错误及目标缺失，且参考与候选不被改写。它约束管线身份不能改变共同判分，不替代八组真实产物的统一评分或expected内容覆盖。

## 历史读取诊断

先前`service_observation`、v15及`scoped_literal_formats_17`的实现记录保留在[读取诊断](../benchmark/diagnostics/service-readback.md)。本轮实际最终Markdown只走`expected_readback`，旧记录不提供当前答案、排除或分数。当前读取器支持明确空字段、显式原表留空、不同表的唯一实际位置、完整业务范围、单位与币种、具名类别及附注；图片alt文字仅作字面诊断，资产交付另记，不构成图片语义理解。
