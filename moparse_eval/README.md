# MO-Parse 保存输出评测工具

当前仅以canonical expected和现有选段声明为答案。执行约束见[AGENTS](../AGENTS.md)，计分合同见[评测任务](../benchmark/evaluation-tasks.md#three-layer-evaluation)，最新状态见[评测索引](../benchmark/reports/README.md)。新三层核心已实现部分解释和判定，完整质量成绩仍暂停；局部分母、诊断完成和测试通过不能代替正式重评。

## 代码边界

`expected_readback.py`只读取Markdown语法及声明选段，保存原始文字、格子、行号与外部上下文，不生成旧业务record，不把未选单位或期间灌入要求。部分语法选段和外部依赖保留来源，不改写语料。

`saved_native.py`和`adapters.py`分别读取Docling、Paddle、GLM、DocVortex和视觉ContentBlock结构；`native_readback.py`忠实暴露原生明确关系。接口不接收expected。thead、ARIA、th/scope和headers按实际声明保存，全td网格不靠邻格推断角色。

`compact_requirements.py`读取明确列说明、合写/拆写要求和父指标声明；`matrix_evidence.py`从候选自己的行列角色、完整头链、单位、期间及分组暴露事实和实际数据对象。二者不交换答案。没有独立对象来源的父指标、未声明的分组层级、歧义单位至列绑定仍须保留未决范围；原始字面存在不等于业务绑定已经成立。父指标声明来源及其跨表示对应仍在联调，不能以编译出的集合为自己的正确答案。

`header_path_requirements.py`读取实际最终Markdown中的行路径、列路径和独立标量，从本行打印的指标角色区分记录主体与行指标。每个金额、占比、年份、单位和口径保留自己的来源，普通URL、时间及`A / B`字段不由全局斜杠拆分。四列无同比声明与五列含同比声明分别解释；未明确起止期间的同比保留自己的待决项，不按另一列年份推断。相关真实缺陷及修复证据见[service表头路径](../benchmark/diagnostics/service-header-path-readback.md)，读回收益不计交付改善。

`measurement_evidence.py`只从当前字面读取完整数值、单位和明确币种，保留各自跨度，不做换算或默认货币推断。字段头括号只有整个内容为单位时才拆分；数量括号和看似金额的身份名称仍保持原样。单位位于值后、表头或同记录声明中，不能改变业务断言数量。年度限定的有限B/L归一不改变T字面。

`text_projection.py`只根据实际schema、打印来源和有限数据对象建立共享标签/单位的有界alias，保留原格、原片段和每个对象的容量。普通正文与身份值的真实重复不按字符串去重，其他对象上的单个百分号不能补当前对象缺少的字面。业务单位绑定有歧义时，T仍保留实际印出的单位。父指标文字的有限投影须保留父声明的真实来源，不得改挂到叶值来源。

`scalar_evidence.py`在判分前及报告复核时，针对已声明`raw_value`与精确`value_source`的标量核对独立保存的原格/原片段：实际字段原字、数值子跨度、路径及对象边界必须相符。同步修改fact与ledger不能绕过原文检查；该来源检查不解析一般正文、不证明尚未支持的业务语义。

`context_evidence.py`保留原生父引用、标题事件、相邻平级标题的完整有界序列及隔断；`scope_correspondence.py`核对候选自己实际证明的业务范围。显示层级压平可以由来源证据解释，缺失父标题、未知同级范围及North/South同名叶项不能互借。`business_correspondence.py`先核身份、范围和位置限定，再比较值；`relation_correspondence.py`使用独立对象或完整逻辑角色核对关系。有限业务角色拼写对应由`business_labels.py`维护，不改实体名、数值、条件或T字面。

范围声明使用最多8组有界文字索引，只缓存有序原text tuple及canonical策略到匹配序号的映射。来源、角色、父范围等每次从本次原声明回取，不按可变列表id复用；重复标签保持原次序，所有实际事件、边界、身份检查和完整检索证据仍逐项处理。这是分析实现优化，不更改判定标准、分母或处理成本。

`prose_requirements.py`支持有限的明确义务、条件、例外、否定和普通正文关系；公共入口先按实际同范围、连续来源合并合法句片段，再读取业务断言。每个片段保留原text、原source和拼接范围，不跨标题、图片、字段或业务父范围补句。`entity_requirements.py`读取有限的明确业务角色身份述句，保留实际角色和实体字面；未知重要身份句式保留pending与B阻塞，普通copula不因值含大写或中文就成为实体。未解析的重要业务谓词、多断言正文、含业务数值的长标签及条件否定不能被另一条已读取身份题掩盖；失败关闭也不代表这些要求已完整解释。

明确逻辑字段标签形成有来源的局部范围，标题和相同字段前缀可表达同一范围；同一原段的后续句保留实际原段偏移及原标签来源。明确Name父记录来自实际列表或原生parent引用，记录身份与原句actor分别保留，不把`he`改写成人名。字段/记录身份先核对，条件、否定和值随后比较；另一个字段、记录或North/South范围中的正确值不能救当前项。

已确认逻辑字段的T标签与正文按各自实际跨度分别读取，字段分隔冒号是关系控制语法；原段全文仍留在来源清单中。字段改成相同标题不再造成T漏字，第二句的正文与业务值保持原段偏移。业务前句/枚举不能借此被当作字段，未支持的报道及期间关系也不能吞入actor；这些范围保留原文和pending，阻断相应质量层。

`series_requirements.py`读取有明确属性、年度、单位和来源的时间序列。缺少属性的数字tuple、没有独立比较期说明的本年/上年增减不能按最大年度或列序补全。`toc_evidence.py`已接公共入口，读取明确目录角色、条目、页码slot和实际父路径；目录同名叶项不能跨父范围借页码，生成序号不充当独立对象锚点。已证明根目录使用空路径及实际root证据，未证明或损坏的父引用使用None及候选歧义，不能混为根。完整平面文字或Title/Page schema可以证明平面根，显式坏引用禁止回退；软件未支持的headers仍阻断，不从expected补树。独立受控验证不等于全部真实目录已经可靠解释。

`three_layer.py`编译要求、读取候选证据并独立判定T/L/B；`expected_scoring.py`是同一实现的当前入口，没有旧算法回退。`layer_aggregation.py`分别汇总各层及配对。解释器的ledger用于检出调用期间的突变，不能证明业务语义覆盖；软件未支持不变成候选0分。

`expected_evaluation.py`统一编排八组原生及P07/P08实际baseline/current正文，默认使用16个CPU spawn进程。任务按sample_id轮转，同一样本最多有一个组任务执行；各样本内部保留原声明组顺序，完成后其下一组加入就绪队尾，由其他已等待样本填充可用进程。全部声明样本和组保留，未捕获的任务异常直接使执行失败且不重试。该调度只改变保存输出分析，各管线和独立后处理的原始资源与计时保持原声明。

每份完整评分轨迹通过`json.dump`流式写入同目录唯一`.part`文件，保持紧凑UTF-8 JSON和结尾换行；关闭成功后原子替换目标文件。编码、写入或替换异常清理本次临时文件，保留已有目标及其他工作进程的临时文件。`index.json`和`execution-status.json`的`analysis_scheduling`记录并行上限、每样本活动上限、启动方式、样本及组次序、完成后入队策略、失败不重试和声明任务总数。独立受控调度与写入验证不代表全范围遍历已完成，实际状态仍以当前执行记录为准。

`expected_report.py`复核完整T manifest、原始来源、alias容量、正文拼接来源、逐项检索和关系证据，再复核分母、S/D/I及配对；报告器仅接受同版、完整、无软件阻塞的结果。这些证据检查仍不能替代独立正确要求和实际文字诊断。旧字段评分、普通文字评分、硬行列定位和旧报告入口已删除。`information_reading.py`只保留候选单位字面读取，供既有service readback使用。

## 独立软件验证

```bash
.venv/bin/python -m pytest \
  tests/unit/test_three_layer_*.py \
  tests/unit/test_compact_requirements.py tests/unit/test_matrix_evidence.py tests/unit/test_matrix_date_axis_contract.py \
  tests/unit/test_header_path_requirements.py tests/unit/test_scalar_evidence.py \
  tests/unit/test_text_projection.py tests/unit/test_context_evidence.py \
  tests/unit/test_scope_correspondence.py tests/unit/test_prose_requirements.py tests/unit/test_prose_field_context.py \
  tests/unit/test_prose_multi_clause_contract.py \
  tests/unit/test_entity_requirements.py tests/unit/test_series_requirements.py \
  tests/unit/test_measurement_evidence.py tests/unit/test_measurement_reader_drift.py \
  tests/unit/test_toc_evidence.py tests/unit/test_toc_parentage_contract.py tests/unit/test_business_correspondence.py \
  tests/unit/test_business_label_equivalence.py tests/unit/test_expected_syntax_selection.py \
  tests/unit/test_moparse_eval_scoring_freeze.py tests/unit/test_moparse_eval_report_resources.py \
  tests/unit/test_moparse_eval_cli.py tests/unit/test_moparse_eval_request_metadata.py \
  tests/unit/test_moparse_eval_reporting_metadata.py tests/unit/test_moparse_eval_native_readback.py \
  tests/unit/test_moparse_eval_table_readback_repairs.py tests/unit/test_candidate_delivery.py \
  tests/unit/test_table_semantics.py tests/unit/test_table_semantics_entrypoints.py \
  tests/unit/test_postprocessing_preservation.py
```

测试硬断言业务集合、角色、权重、限定、实际cell端点和排除理由，覆盖表示变化、Status误读、独立引用换绑、重复冲突、合法分块、父范围、条件/否定与L独立、实体漏项、时间序列、目录模块、来源容量及突变。它们使用受控数据，不读取语料或运行目录。此命令是回归入口，不能据命令存在或测试数填写passed；公共入口与保存输出的文字诊断仍须独立验证。

## 保存输出软件诊断

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/runs/lite \
  --service-baseline-root benchmark/runs/lite/service/baseline \
  --current-root benchmark/runs/lite/service/current \
  --output benchmark/runs/lite/diagnosis/three-layer-current \
  --diagnostic --workers 16
```

输出目录须不存在。诊断保存实际来源、全部命中、身份检查、排除理由及软件阻塞，不生成正式冻结或成绩。`--sample 样本ID`可重复使用，仅在`--diagnostic`下限制软件诊断样本；选中样本仍使用同一判定器遍历全部声明组。正式重评拒绝`--sample`，不能用抽样缩小正式分母或把局部范围冒充全量。`index.json`为`blocked`时进程返回2，表示存在必须修复的软件范围，并非候选失败率。部分要求数量不构成完整语义覆盖。主分和分子被清空，原始处理时间及资源单列，不重跑解析或CPU后处理，不更新原run.json。

只保留`benchmark/runs/lite/diagnosis/three-layer-current/index.json`对应的当前全范围诊断；执行中查看同目录`execution-status.json`，只有完成索引才能说明实际遍历状态。旧选样、旧全范围及单项派生轨迹在源码变化后删除，不归档或继承。实际位置和剩余问题见[原生读取诊断](../benchmark/diagnostics/three-layer-native-readback.md)、[矩阵文字诊断](../benchmark/diagnostics/three-layer-matrix-readback.md)、[目录读回](../benchmark/diagnostics/three-layer-toc-readback.md)及[五个选段输入边界](../benchmark/diagnostics/three-layer-input-boundary.md)。这些边界不授权修改参考、包或输入范围。

## 正式重评及报告

只有独立反例、突变、实际格式及保存输出诊断均可靠且无已知缺陷时，才可生成正式冻结。冻结须匹配当前`cli.code_identity()`和`three_layer.PROTOCOL`。validation的`independent_counterexamples`、`mutations`、`native_formats`及`saved_output_diagnosis`四项分别包含`status: passed`和实际证据路径；这些字段本身不证明判分正确。

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/runs/lite \
  --service-baseline-root benchmark/runs/lite/service/baseline \
  --current-root benchmark/runs/lite/service/current \
  --freeze benchmark/runs/lite/scoring-freeze.json \
  --output benchmark/runs/lite/scores/current --workers 16
.venv/bin/python scripts/render_lite_report.py \
  --index benchmark/runs/lite/scores/current/index.json \
  --output benchmark/reports/lite
```

当前阻塞未解时不得执行正式重评或制造passed冻结。正式入口遇到软件阻塞会停止全部成绩汇总；报告器在覆盖报告前拒绝不完整结果。八组原生与P07/P08三种配对分别报告，不推导旧“零转换损失”或采用结论，不混排正文与原生成绩。

## 保全与范围

不打开PDF或图片，不运行渲染、OCR、视觉、裁判推理、Full或额外PDF；expected、原件、标注、映射、资产、数据包、候选正文和原始测量只读。既有执行及CPU后处理组件保留，本任务不调用它们，不操作GPU、TTS、服务或部署。

通用检查永久排除语料、datasets、benchmark/reference-decisions、benchmark/runs和benchmark/reports，包括显式路径。专项诊断不认证语料。仅提交本任务代码、正式文档与报告，运行资料、大候选和软件快照留本地。
