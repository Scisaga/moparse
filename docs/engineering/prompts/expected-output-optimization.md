# MO-Parse：实际 expected 语义缺口闭合

继续用户2026-11-07的任务。先读取AGENTS.md、benchmark/evaluation-tasks.md、唯一Lite报告及其data/diagnosis-summary.json，再核对当前HEAD、工作区和源码身份。本轮接手HEAD为65af55b06484deb1f6087613844b9de0a4311cb5；后续以实际本地现场为准。保留已有修改，不执行reset、覆盖checkout或clean，不主动提交、推送。

当前只授权source-only软件工作和受控合成比较。canonical expected、选段、映射、原始页包、有效native、历史交付正文及原始成本只读。不能访问原始PDF、图片、字层、OCR/VLM，不能执行真实候选比较、任何真实native到final回放、正式保存输出评分、模型、GPU、TTS、服务操作、部署或公开API。五个输入范围保留全部文字和目标，不裁段、不计零；新软件问题不能并入这五项。完整质量成绩继续撤回。

本轮目标仍是完成真实样本的全部业务语义，不能只减少pending或完成若干句段。来源完整性、受控软件证据、完整expected语义、真实交付执行和质量发布分别验收；测试通过、视图写出、没有pending都不能代替完整样本的独立验收。当前没有原先blocked的完整样本新增通过。

保留已完成A/B/C：顺丰L920、L742、L781声明及41条记录、221项计量；华为L1586的金额/同比及不借前句年度的净利润；平安L298首句字符0–76的一个build命题、平台、共享定语和受益关系。不要重做这些范围，也不要新建Source Obligation、Narrative AST、Oracle或比较平台。复用现有实现，直接修复尚未解释的实际来源。

source_obligations.py已增加独立角色边界守卫；原因、目的、条件、另一个动作、完整句子或金额前句不能由一个opaque S/O证明覆盖。十二项旧SVO不再按原过宽结构输出，但其所在段落仍有独立内容未解释。Sinopec L864的金额及相对上年末的增量已分开；L860的金额部分可读，原因链继续pending。详见actual-source-diagnosis.json中的baseline_svo_repairs，逐项保留原文、旧角色、独立来源分句、当前facts/relations及T/L/B处置，不能把旧SVO移除当作整段修复完成。

series_requirements.py已绑定同一封闭指标记录中的两个连续年度与明确同比操作符，保留每个年度、日期后缀和数值来源；第三年度、缺年、不同月日及普通增减不能选定比较对。父级只提供实际列表成员关系，子项自己的期间、单位和金额不由父级代填。scalar_evidence.py及来源审计拒绝跨记录借用相同年份；expected_report.py使用完整候选业务bank复核这类证据，不因未被召回而丢失其本行年度。

cjk_measurement_requirements.py已扩展有界金额、完整日期、明示比较基础、金额增减及分子/分母占比。保留词面本公司/本集团等实际主体，不补公司实名或未打印年度。成对字段强调标记不能进入指标或期间；source_requirements.py、最小字段范围绑定和represented_feature_comparison.py共同保留排版控制及真实正文来源。复杂原因、中的关系、定性趋势及其他未支持内容仍明确未决。

fronted_nominal_context.py复用现有fronted_context、proposition和coordination节点表示By/Through手段及明确目的操作。操作数不是额外无条件B事实；原始语法独立要求main、operation、controller和实际附着边。删除AST、操作数、关系、feature或更换来源不能通过。平安L298第二句已保留手段结构和可读including操作数，accounts in…及主句with…仍未闭合；不能称整句或整个p008-011完成。

继续顺丰sf-cashflow-assets-liabilities-p040-041的全部residual_issues，尤其经营、投资、融资现金流原因，差异说明引用及后续合同资产、金融资产、借款、库存股的原因和内部范围。七条列表中的同比期间已有来源配对，但原因正文不是普通金额记录，不得省略或伪造成新的金额事实。L920紧凑表保留基线。

继续华为huawei-operating-results-p062-063的全部residual_issues。多年度、父列表、共享/局部单位、金额与明确占比已推进，借助/随着、研发及费用说明、净财务损益原因、债务优化/偿还与年初比较仍需通用解释。单位默认必须在正文、新标题或不支持父级处终止，不能通过复制年度和单位伪造来源。L1586不重做。

继续平安pingan-strategy-cards-p008-011的全部授权正文。检查非限定引言、手段、目的、条件、原因、预期结果、引号名称、共享名词、介词附着、否定及多动作关系。已有主句不能吞掉未知邻句或操作数。不能仅凭引号或TitleCase把复杂结构变成名称。

Alibaba L2353仍保留共享infrastructure与只限定AI的两个候选附着。L96及L2371等授权文字提供共享解释的旁证，但未唯一绑定L2353同一投资对象，仍保留歧义；capture目的不变成已实现收益。actual-source-diagnosis.json保存完整原文、两种结构、B/L影响及检查过的授权上下文。多解释验收合同仅可提议，未经用户批准不改变正式合同、分母和发布门槛。

所有修复必须贯通实际expected入口、要求图、独立来源审计、T/L/B投影、手写受控Oracle、来源/结构突变、最终B/L比较及报告重放。重点检查没有pending的复杂正文；同步kind/feature、同字面邻源、条件当事实、目的当结果都必须留下pending或明确冲突。未知不能改为不适用，共享限定不重复加B票。

完整回归命令和证据位于benchmark/runs/lite/requirements/validation/software-validation.json及regression.xml；新增受控用例位于test_proposition_semantic_coverage_guard.py、test_financial_sequence_semantic_closure.py和test_nonfinite_operation_production.py。最终数据中的test count及software_id以当前文件为准，不沿用历史数量。软件修改后同源码重建全部173份视图，使用16个分析进程；这不改变任何候选管线或隔离回放资源。

重建时先写临时目录，核对所有视图、软件身份、原始source inventory、完整授权selection和五个输入范围，再安装为唯一requirements/current并删除失效生成视图。sources中的派生分段或解释标记可能随读取修复改变，必须逐来源说明；这与不可改的原始授权sources分开报告，不能声称所有辅助数组原样相同。退出码2表示structure_blocked，不是worker失败或语义通过。

只维护benchmark/reports/lite/report.md和现有相邻数据；actual-source-diagnosis.json保存三个样本的完整原文、投影、审计及residual_issues，并保存每项投影变动的来源。正式分母未冻结，不把投影数称为质量分母。原始成本不重测、不改写、不相加冒充端到端时间。通用检查排除pdf_sample、datasets、benchmark/reference-decisions、benchmark/runs和benchmark/reports。

后续真实交付计划不是当前启动授权。只有P07/P08有真实历史baseline/current配对，P01-P06不制造历史基线。当前完整语义及比较门槛未通过时，不启动八组回放或保存输出重评分；即使全部受控软件测试通过，也继续按本轮边界执行。
