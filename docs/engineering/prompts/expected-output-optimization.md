# MO-Parse：原23份及撤回3份的验收阻塞修复

先读取AGENTS.md、benchmark/evaluation-tasks.md的当前合同、唯一Lite报告及其data/diagnosis-summary.json。继续使用/opt/moparse；/opt/mosaic-parse指向同一仓库。以当前HEAD、工作区、software_id、测试和独立断言身份为准，保留已有修改，不执行reset、覆盖checkout或clean，不提交或推送。接手参考提交为4d537c942ea49f0101fd51af217bd2919b3476d2。

当前本轮已完成：原23份23/23通过，撤回3份3/3恢复，其余29份回归、55份完整来源Oracle及五处局部来源全部通过，173份JSON/XML同版重建并绑定证据。当前软件和断言摘要以唯一Lite报告及现有验证记录为准；以下保留本轮执行合同和复现入口，不自动授权118份新任务。

本轮只修复上一轮固定23份及撤回3份直接依赖的生产缺陷，并执行其余29份有效基线和必要公共回归。不建立新批次，不再执行相同的940项人工普查，不展开其余118份的整样本新任务。上一轮“只实施一个公共修复包”的限制已取消；已知实现缺口不能仅以另一个公共根因为由登记后停止。32份旧批次及23份新增样本身份保留，不修改正式manifest、来源或selection。当前结论以唯一Lite报告和绑定证据为准。

先修父归属重复计票。完整内容与被替代局部命题对同一陈述、同一父端点和来源只承担一份L责任；其他表示保留分析或证明用途。责任唯一化发生在候选读取前，并贯穿投影、覆盖、固定B/L分母、最终outcomes及证据重放。不能按关系类型、同行或同标题批量去重，不能只在评分末尾修数字；独立标题层级、列表归属和阅读顺序继续保留。正常生产输入应实际通过且只计一票，独立注入重复责任后仍须被实质Oracle拒绝。

先恢复catl-nev-battery-markets-p127-132、fiyta-bond-followup-p011-017及pboc-cover-p001，再对原23份运行全部已有来源case并继续修复残余。Alibaba股东信的不完整主体、HKEX目录的导航与父组、Ping An舍入注记和策略L298/L309/L328的typed/mixed责任均在范围内。定位行号不替代授权原文。完整内容合同继续有效，但已规定的类型化责任不得被整段内容吞掉。C基线须核实首句一项命题与4条关系进入最终比较，并通过顺序及错绑判定路径，分析层仍存在不足以恢复验收。

独立来源入口为tests/validation/lite_source_oracle.py；原18份及11份断言保留在tests/validation/lite_fixed_source_assertions.py；23份的已完成声明位于lite_review_alibaba_assertions.py、lite_review_hkex_assertions.py和lite_review_energy_assertions.py，数字角色反例位于lite_review_numeric_role_cases.py。生产读取器与评分器不得导入这些手写答案。保留真实失败记录和实质标准，不删除守卫、允许重复票或接受错误输出求绿。目录的通用标量断言不得与已手写的严格导航合同相冲突；字段定位端点与B极性的职责分别验证，不能放宽原本的事实或关系要求。

每个修复依次完成独立失败反例、通用实现、完整expected生产链、合成candidate最终B/L比较、证据复核及原真实来源Oracle。保留数字角色和同源守卫、普通错值判错、未支持改写未决、候选分块不改变固定分母；数量角色不从邻记录借用。已有比较定义由benchmark/evaluation-tasks.md的“文档 AST 与内容比较”拥有，继续使用document_ast/1，semantic/1仍保持严格语义条件，不另建Oracle平台或通用自然语言解析器。

本轮修复记录放在既有actual-source-diagnosis.json的acceptance_blocker_repair；原review_sample_acceptance、fixed_sample_acceptance、additional_sample_acceptance和cross_fragment_source_review保留批次历史，当前验收绑定最终源码和生成视图。每份通过样本须有全部非延期来源责任、实质case、义务、分析限制及能力用例证据。没有pending、自动枚举ID、编译完整或与current相同都不单独建立独立验收。

源码与断言冻结后，执行software-validation.json中完整受控回归并纳入新反例，再用 `.venv/bin/python -m moparse_eval.requirement_graph --baseline benchmark/runs/lite --output benchmark/runs/lite/requirements/<新的暂存目录> --workers 16` 同版重建173份JSON/XML。核对每份原始来源、selection、五个输入范围、A/B和1639项完整计量的payload；逐来源解释每项B变化及L撤票，证明确实消除同一责任的重复票。核验暂存结果后替换唯一current并删除失效生成视图，不归档过期生成答案，不删样本求退出码0。

最终绑定命令为 `PYTHONPATH=/opt/moparse .venv/bin/python tests/validation/lite_source_oracle.py --output benchmark/runs/lite/requirements/validation/oracle-validation.json --diagnosis-output benchmark/runs/lite/requirements/validation/actual-source-diagnosis.json`。默认入口执行55份来源Oracle及BIS L838、L948、L674和IEA L588、L730五处局部来源审查。--sample与--fresh-only仅供开发，不能替代最终current绑定。来源、测试、断言、能力证据、索引和视图摘要不一致时不得沿用旧验收。五处局部通过不接受其所属整样本；原23份中的IEA训练样本仍须整份通过原完整Oracle。

A保护顺丰L742、L781、L920三项声明及221项计量；B保护华为L1586三项业务要求；C保护平安策略L298首句0–76的一项命题和4条关系及其最终判定。完整计量保护1639项原有明确单位数值要求，须核对原值、单位、期间、来源和完整payload，不只比较数量。五个输入范围保留Alibaba L230、Midea L417、PBOC L540及PBOC L252两项既有选段。Alibaba L2353双附着和未经批准的多解释合同保持原状态。

结束时首先交付生产修复与真实复验结果，不能以审查完全部退回、失败守卫、报告或单元测试作为完成。当前授权下能够修复的实现缺口继续修。真正不能解决的输入、授权或证据问题保留失败，给出原文、最小反例和所需决策，不强制样本变绿。最终先报告父归属是否修复、撤回3份恢复数、原23份通过数及每份真实剩余阻塞，再说明29份回归、五处局部、173份重建和证据绑定。

canonical expected、原始映射、selection、页包、语料、有效native、历史交付正文及原始成本只读。本阶段禁止读取PDF、图片、字层或OCR，禁止模型、实际候选比较、真实native到final回放、正式评分、GPU/TTS/在线服务操作、部署、公开API修改、提交与推送。候选只限独立合成受控测试，不把实际expected复制为candidate。16进程仅用于CPU分析，不改变原管线或隔离后处理资源。

只维护benchmark/reports/lite/report.md及现有诊断和验证记录，原始处理成本不重测、不改写。通用检查永久排除pdf_sample、datasets、benchmark/reference-decisions、benchmark/runs和benchmark/reports，包括显式路径调用。来源验收不建立真实原生格式、保存输出评分、交付或全局质量验收，全部质量成绩继续暂停。
