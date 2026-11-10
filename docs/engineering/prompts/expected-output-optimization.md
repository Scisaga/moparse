# MO-Parse：第三阶段比较责任修复的续做入口

继续/opt/moparse；/opt/mosaic-parse为同一入口。先读AGENTS.md、benchmark/evaluation-tasks.md的当前合同、唯一Lite报告、data/diagnosis-summary.json、requirements/current/index.json及validation/actual-source-diagnosis.json。接手公开参考提交为46045f5f073891a8b470e5d46176e6803024a9d9；本轮修改未提交。以现场源码、测试、断言和索引身份为准，不回退、覆盖或清理已有工作。

第三阶段从55份完整独立验收和118份责任缺口接手。本轮固定tencent-covenants-interest-conditions-p118-123的全部61个授权来源，手写声明在tests/validation/lite_stage3_assertions.py；完整父链按独立声明的原始行号从只读来源解析，再调用生产编译。其余55份的成员和实质断言不变。最终新增通过、全局覆盖及验证身份以唯一报告和phase3_coverage_repair绑定记录为准，不能把自动责任完整的范围外样本称为独立验收通过。

已定位的公共首败路径是three_layer._Graph.prose对未知列表父级统一产生阻塞，document_ast_comparison._fallback_blocks因而没有生成固定内容责任。新分支逐级核对完整父节点、先前来源和父子文字，复用document_ast/1的父链及顺序比较；父级原文未承担、来源缺失或已有类型化字段、身份、明确单位计量时继续阻断，不把条件当已发生事实。原list_membership仅在完整父链、父子端点、来源及唯一内容所有者均相同时转为证明记录，其他独立列表关系保留。字段序列读取另行修复孤立句末冒号被当成空值字段的问题。规则定义只在evaluation-tasks.md维护。

同一列表通用修改曾在暂存视图中吞掉集合外华为L754的一项既有误报率计量。该暂存结果未安装；真实失败和独立合成反例保留在phase3_coverage_repair.discovered_numeric_regression。修复要求核对retained_semantic_requirements中的实际比较责任，不能只检查分析图仍有该数值。不得删除这个反例或放宽1639项完整payload保护。

118份接手诊断沿实际来源、读取器分支、既有事实、内容所有者、来源审计及最终阻塞追溯；路径家族互相重叠，不是118个语法任务，也不是reason计数推导的独立根因数量。来源级路由、第一失败条件和两个真实复现来源保存在phase3_coverage_repair.root_cause_clustering。下一轮优先处理已定位且有真实来源证据的同类缺口，先固定完整样本及手写来源断言，再修首个生产失败；不要重建AST、Oracle、比较器或诊断平台，不重做55份人工普查。

唯一独立入口仍为tests/validation/lite_source_oracle.py，validation/source-oracle.py仅为启动器。原18份、11份及23份断言模块保持历史成员，第三阶段声明单列。默认入口现在执行原55份加本轮固定样本及五处BIS/IEA局部来源；--sample和--fresh-only用于开发，不能替代最终current绑定。可用16个CPU分析进程分批调用既有--sample入口并汇总同版结果；每批真实命令、全部case和五处局部结果均须记录。

每次修改走合成expected声明、read_expected、compile_requirement_graph、来源审计、validate_requirement_graph、evaluation_projection、独立合成candidate读取、grade_layers及validate_evidence完整链。覆盖条件、例外、AND/OR、数值、单位、期间、主体错绑、邻来源借用、缺失节点、完整文字但错父链、重复责任和责任空洞。普通错值判错、未知改写未决、确实缺失保留missing证据，固定分母不随候选分块变化。不得把真实expected复制成candidate。

源码及测试冻结后，执行software-validation.json的完整受控命令并加入新反例；同版运行 `.venv/bin/python -m moparse_eval.requirement_graph --baseline benchmark/runs/lite --output benchmark/runs/lite/requirements/<新的暂存目录> --workers 16` 重建173份JSON/XML。退出码2须检查真实阻塞；不删目标、裁段或改门禁求0。逐项核对来源及selection、五个输入范围、1639项原值/单位/期间/限定/来源/完整payload、每项B/L变化和责任归属。通过后替换唯一current并删除失效生成视图，不归档过期答案。

最终执行 `PYTHONPATH=/opt/moparse .venv/bin/python tests/validation/lite_source_oracle.py --output benchmark/runs/lite/requirements/validation/oracle-validation.json --diagnosis-output benchmark/runs/lite/requirements/validation/actual-source-diagnosis.json`，或复现oracle-validation.json记录的16进程同版分批命令。完整回归JUnit中的实际通过case重新绑定能力证据；源码、测试、断言、覆盖、生成视图和索引摘要必须一致。责任完整但尚未独立验收的样本仍单列，不能复用旧源码下的通过状态。

A保护顺丰L742/L781/L920三项声明及原221项payload，其中161项typed、60项已有内容承担；B保护华为L1586三项；C保护平安L298首句的一项类型化命题、4条关系、互斥余段和最终顺序判定。五个输入范围保持Alibaba L230、Midea L417、PBOC L540及PBOC L252两项既有选段。Alibaba L2353双附着及未经批准的多解释合同保持原状态。局部BIS/IEA通过不接受其所属整份样本。

canonical expected、原始映射、selection、页包、语料、有效native、历史交付正文和原始成本只读。禁止PDF、图片、字层、OCR、模型、实际候选比较、真实native到final回放、正式评分、GPU/TTS/在线服务操作、部署、公开API修改、提交或推送。16进程仅用于CPU来源分析，原管线及隔离后处理资源不变。source-only验收与真实格式读取、保存输出评分、交付及全局质量验收分开，质量成绩继续暂停。

只维护benchmark/reports/lite/report.md及现有诊断和验证目录，最小同步本续做入口与拥有规则的文档，不追加任务全文到AGENTS.md。通用检查排除语料、datasets、reference-decisions、runs和reports，包括显式路径调用。结束时逐样本报告新增完整通过、退回和未完成审查，说明原55份、计量保护、173份重建及剩余覆盖状态，不能以测试数量或pending减少代替完整样本验收。
