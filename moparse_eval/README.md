# MO-Parse 统一评测工具

本轮复用有效保存输出及原始测量，不重新执行模型。方法、指标、分母、失败政策和完成条件只维护于[评测任务](../benchmark/evaluation-tasks.md#current-task-expected-only)。当前状态及唯一正式报告由[评测索引](../benchmark/reports/README.md)维护。

## 读取与判分

`expected_readback`只读canonical expected及现有manifest/source-map选段，展开完整正文与明确记录要求，不读取旧标注答案。`target_coverage`追溯完整文字范围至业务要求或正文目标，保留字段提取后的剩余文字；这种程序记账不认证参考真实性，也不单独证明语义覆盖。

`saved_native`从保存的native.json调用各组真实格式读取器，再由`native_readback`暴露显式关系；P05只使用json_result主视图。候选读取器不接收expected。最终Markdown由`markdown_observation`直接读取，不使用内部IR、未打印跨度或隐藏关系。`expected_scoring`对所有组共同判分，`prose_metrics`报告正文定位、字符覆盖、字符保全及已对齐严格CER，整段全对只作诊断。业务主结果分列值与标签正确/全部目标及完整信息正确/全部目标。

软件读取失败须先修复，不能批量计成解析错误。缺失候选或真实失败仍接受全部目标且判错。代码身份、依赖和已通过的独立验证冻结后，全部受影响原生与正文使用同版程序重新评分。程序不提供语料检查、参考修复或人工成绩入口。

业务定位在`scoring._locate_record_field`中统一执行字符串召回、完整身份核对及候选上下文读取，每个命中包括唯一候选都留存`localization.query`、`candidates`、身份检查和排除理由。范围冲突不回退比较。`candidate_context`只从候选自己的打印表题和原列名格读取有边界的共享列名，不合并物理表、不接受expected答案；新的范围或冲突会撤销读取依据。正文近似检索先裁到已有标题范围。`score_contract`在判分和报告入口独立拒绝缺少追溯、身份冲突和选择来源不符的结果；该检查仍不能代替独立反例和真实文字诊断。

`context_matching`按实际完整标题和表内明确分组查范围，并保留父级标题证据。默认显示级别不能覆盖expected明确给出的从属关系；同名叶标题仍须核对父级。仅最初连续的明确文件键值信息可位于根标题之前，跨文档标题或业务正文不继承该范围。年度必须有当前范围证据，已删除全文扫描年度后全局填入各字段的旧逻辑；局部明确年份优先于宽范围年度。读取连写的年度/完整日期和标签括号旁空格不改变文字、数字、附注编号或值。

`named_retrieval`读取实际按列排列的命名记录及同一打印列表中的后续单项属性，保留姓名、角色表头、列范围、列表范围和每个原值。新的记录或业务边界终止读取。普通网格检查实际表头与数据行的位置关系；表头明确引用另按引用读取。拆分图表/框题的完整匹配同时保留各实际文字部分，默认显示级别不会把已证实的子标题误当成父范围结束。每个正文候选另列父范围检查及停止位置。

`context_matching.flat_display_levels`只在完整父子标题实际使用同级标记的当前范围内校准显示级别，保存实际父子位置，其他范围仍按自己的层级与明确边界读取。`candidate_sequences`在候选连续的至少两对完整标识符和说明中忠实暴露顺序关系，保留每对原文和来源；不使用名称词典或expected答案。规则及反例由[评测任务](../benchmark/evaluation-tasks.md#43-上下文和顺序)定义。

重复的已打开祖先标题保留先前锚点与当前实际标题，不切断原子范围；双语标题的完整语种部分仅从生产者已声明标题的单条实际行读取。兄弟范围、新名称和新文档仍阻断，普通业务文字和拼接正文不能提供标题证据。业务字段的`scope_search`与正文的`repeated_ancestor_reading`保留该读取过程。

完整多行标题索引保留全部文字；纯列表父标签不生成未声明的空值字段，但全文和子范围继续比较。实际列表标签、字段关系及打印标签范围共同查证归属，边界不因其文字已经比较而消失。`candidate_sequences.read_colon_value_pairs`读取标签后紧随的实际字面值，并撤销同一标签的伪空值视图；`candidate_context`保留无新范围打断的明确单位说明。具体条件及反例由[评测任务](../benchmark/evaluation-tasks.md)维护。

## 冻结前的真实输出诊断

先运行`tests/unit/test_expected_retrieval.py`及实际受影响格式的独立合成用例，再按已声明的Lite样本选择不同格式、正文、重复标签、单位、负数、布局正文和跨页情况运行完整链：

```bash
.venv/bin/python -m moparse_eval.diagnose_saved \
  --run benchmark/runs/lite \
  --service-baseline benchmark/runs/lite/service/baseline \
  --service-current benchmark/runs/lite/service/current \
  --sample midea-business-p013-024 \
  --sample bis-policy-boxes-p026-034 \
  --output benchmark/runs/lite/diagnosis --workers 16
```

输出是本地软件诊断证据，保存全部目标及候选检索轨迹，不是Lite成绩或自动通过声明。文字诊断必须具体检查：字符串命中有没有被漏掉；身份冲突是否排除；共享表头是否有当前候选证据；选中的值是否来自已经验证的位置；正文是否仍在自己的标题范围。不能只读汇总计数或用户提供的一个例子。工具执行完成仍标记文字诊断待完成，不自动声明没有读取缺陷。修代码后用最终同版程序重新运行必要诊断，再生成评分冻结。

## 保存输出的统一重评

八组原生及测量位于`benchmark/runs/lite/`，唯一修改前正文为`service/baseline/`，新正文为`service/current/`。earlier/before/after、旧成绩、错误冻结和旧报告框架已删除，不保留兼容入口。

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/runs/lite \
  --service-baseline-root benchmark/runs/lite/service/baseline \
  --current-root benchmark/runs/lite/service/current \
  --freeze benchmark/runs/lite/scoring-freeze.json \
  --output benchmark/runs/lite/scores/current --workers 16
```

输出目录必须不存在。`--current-root`尚未生成时可省略，只重评八组原生及唯一基线。重评不会调用模型或候选后处理，也不回填处理时长。评分JSON、文字范围追溯、候选证据和配对变化保持本地。禁止用旧评分填充新索引。

评分使用进程池，`--workers`范围为1至16，每个“样本 × 输出组”独立计算；本轮按用户指示使用16进程。并行度不改变评分规则、目标、证据或原处理成本，独立合成运行比较串行与16进程的逐项结果一致性。它不改变候选CPU回放的8核、8 GiB和串行任务配置。

冻结必须记录当前`cli.code_identity()`、`expected_scoring.PROTOCOL`及独立反例与真实格式读取验证通过的工程证据；入口核对软件身份、依赖与协议，并在完成时再次确认未变。不能用测试数量、文件存在或复现一致代替判分有效性。

## 唯一报告

```bash
.venv/bin/python scripts/render_lite_report.py \
  --index benchmark/runs/lite/scores/current/index.json \
  --output benchmark/reports/lite
```

只有`benchmark/reports/lite/report.md`是正式报告。附录、分项、逐项错误、范围、文档/家族/类别和配对证据在相邻目录；报告入口从实际逐项结果复算汇总及采用门槛，拒绝版本混用、目标不齐、未完成或已知读取缺陷。旧并行报告生成器和分组独立评分入口已删除。

`examples.html`直接并列expected、实际候选与全部命中及排除理由，默认P08且先列仍有差异项。对应current组还显示从唯一baseline和当前`final.md`直接读取的前后片段，源路径及片段保存于`data/conversion-examples.json`；省略表行有独立省略号。没有真实正文文件或找不到不同的实际业务改善片段时，报告拒绝编造示意文本。除正确目标保全外，还须检查实际新增文字有没有无依据的父路径等多余关系。

报告只读取同版已完成评分及有效原测量，不重新读取expected或判分。原生历史时间与CPU回放单列；800页和80页三次重复分列，初始化、预热、采样覆盖及缺失另列。不相加独立峰值，不将TTS或整卡显存归给管线。图表使用无衬线字体，SVG字体栈和PDF嵌入以程序验证，不开展原页或候选图片视觉验收。

## 隔离CPU后处理

发现真实转换损失后，修复原生已有信息能够支持的问题，再运行实际服务链。候选容器只挂载输入、对应管线原生产物、软件和输出目录，不挂载参考、历史评分或expected；网络关闭，无GPU设备。P08不读取PDF文字或矢量表格，P07沿用已声明来源处理，不新增补充方法。只改评分器时不重跑候选。

```bash
.venv/bin/python -m moparse_eval.service_evaluation prepare \
  --baseline benchmark/runs/lite \
  --output benchmark/runs/lite/service/current/p07 \
  --pipeline P07 \
  --service-config benchmark/runs/lite/service/baseline/service-config.json
.venv/bin/python -m moparse_eval.service_evaluation run --run benchmark/runs/lite/service/current/p07 --phase warmup
.venv/bin/python -m moparse_eval.service_evaluation freeze --run benchmark/runs/lite/service/current/p07 --validation benchmark/runs/lite/service/service-validation.json
.venv/bin/python -m moparse_eval.service_evaluation run --run benchmark/runs/lite/service/current/p07 --phase measured
```

P08使用对应管线和目录。预热与800页质量回放、固定80页三轮分别记录。`freeze`验证实际后处理代码与依赖，不重新运行原生预检。实际后处理完成后，由前述统一评分入口对全部受影响组重新评分；正文收益、baseline正确项损失及原生到正文损失分别报告。不部署，不操作GPU、TTS或在线服务。

评分代码变化不要求重跑已验证的后处理。若两者已分开冻结，CPU后处理的`freeze`和`run`从该组`software/`快照执行，保留实际处理的软件身份；评分器以独立的最终身份读取保存正文。不能把原执行快照改成新评分版本，也不能把工程冻结当作正文采用结论。

## 软件验证边界

独立合成反例先固定，再修实现。`tests/unit/test_expected_contract.py`从SDK、HTML、GFM及列表完整读取链约束正文标点、负号、单格多事实、单位、年度、否定、附注、冲突、身份公平和实际正文边界；其余合成格式及定位测试补充多层表头和续接。真实保存结果的专项程序读取验证单独执行，不是语料复核。

通用测试及Markdown检查只读取代码和非语料文档，永久排除`pdf_sample/`、`pdf_sample_extra/`、`pdf_page_images/`、`datasets/`、`benchmark/reference-decisions/`、`benchmark/runs/`和`benchmark/reports/`，显式路径亦不可绕过。原件、参考、标注、映射、资产和数据包保持原样。运行资料与软件快照留本地，本任务仅提交代码、正式文档和报告。
