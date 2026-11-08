# MO-Parse：文档 AST 结构与内容比较续做入口

先读取AGENTS.md、benchmark/evaluation-tasks.md中的三层合同、唯一Lite报告及其data/diagnosis-summary.json。以现场HEAD、工作区和源码身份为准，保留已有修改，不执行reset、覆盖checkout或clean，不主动提交或推送。/opt/mosaic-parse与/opt/moparse指向同一仓库。

用户2026-11-08明确要求收敛到多层级AST结构与内容比较。保真读取两边已有的文档结构，建立范围、角色和内容对应，再独立比较T/L/B。复用现有requirement_ast、业务比较器、grade_layers和validate_evidence；不要再把扩充通用中文动词及语法覆盖率当作工作主线，也不要另建评测、Oracle或报告体系。

完整有序内容AST在同一已验证文档范围内相同，可以证明陈述内容保留。已支持的数量、单位、期间、条件和原因仍按所属语义合同比较。其他文字改写没有可验证同义规则时保留unresolved，不直接计业务错误。原语义解释器的未决记录继续保留，不能把内容保留证明称为任意中文语义解析完成。不能用正确数值定位候选，重复身份及候选容量必须有完整检索轨迹。

固定中石化目标为sinopec-finance-governance-p025-036，当前manifest原页25–36，授权expected为L752–1111的既有选段，共202个原始来源。包括治理正文，不能裁成只有财务表格的子样本。财务事实、原因及培训记录具有独立手写断言；其余治理陈述保留完整内容AST、标题归属和有来源的词面节点。最终验收状态只见唯一报告及actual-source-diagnosis.json，不用没有pending或测试数量推断完成。

华为huawei-operating-results-p062-063与顺丰sf-cashflow-assets-liabilities-p040-041是完整source-only成功基线。可版本化独立入口为tests/validation/lite_source_oracle.py，默认重新编译并核对唯一requirements/current；--fresh-only仅供开发，不能当作current绑定证据。禁止静默改写原基线断言迎合回归。

保留A/B/C：顺丰L742、L781、L920三项紧凑声明及41条记录的221项计量；华为L1586三项业务要求；平安L298首句0–76的一个命题和4条关系。其他平安、Alibaba或中石化经营样本不在本轮语义开发范围。

共享原因补验仍须独立区分明确共同、前者、后者、不同主体、独立记录、各有原因及证据不足。顺丰L948的本句封闭分类、共同借款对象、主体和记录共同提供范围证据；缺少“均”本身不能认定原文歧义。中石化L860保留一个外层主要原因及两项解释内容，不从逗号补出内部因果机制。此前把这些实现问题直接提成来源歧义的说法已撤回。

普通错数、已支持错单位、错年度和错方向，应完整读取、正常比较并只影响相应要求；内部来源或结构伪造应被拒绝。源文字全部保留但AST叶子、节点、关系或作用域缺失，不能通过。连续分块对齐不能跨标题、图片、插入内容或不同范围。精确无损数量等价沿用现有实现，不增加浮点、舍入或汇率容差。

本轮仍只授权source-only软件工作和受控合成比较。canonical expected、selection、原始映射、页包、语料、有效native、历史交付正文和原始成本只读。禁止PDF、图片、字层、OCR/VLM、模型裁判、模型服务、实际候选比较、真实native到final回放、正式保存输出评分、GPU/TTS/在线服务操作、部署和公开API操作。不能将真实expected复制成候选自比较，再作为独立验收证据。

五个输入范围原样保留：Alibaba L230、Midea L417、PBOC L540，以及PBOC L252的两项既有选段。新的软件问题不能并入这五项。Alibaba L2353的两种附着及未经批准的多解释合同保持原状态；本轮内容证明不自行裁定它们。

开发只运行受影响受控测试。最终固定同一源码，完成完整软件回归、华为/顺丰/中石化独立Oracle及173份source-only JSON/XML重建。保存输出分析使用16个CPU进程；不改变原管线或隔离后处理的8 CPU、8 GiB、串行、禁网及无GPU资源。先写受控暂存目录，核对完整授权来源、selection、五个输入范围及A/B/C，再替换唯一current，不保留失效生成视图。

只维护benchmark/reports/lite/report.md及现有相邻数据，关键验证入口纳入版本追踪。软件身份、验证代码身份、命令和返回状态必须对应实际执行；Git HEAD不能代替脏工作区的software_id。通用检查排除pdf_sample、datasets、benchmark/reference-decisions、benchmark/runs和benchmark/reports。原始成本正文及数据不重测、不改写。

完整质量成绩仍暂停。P01–P08原生横向比较与P07/P08真实历史baseline/current交付配对分开；P01–P06不制造历史基线。当前source-only工作完成也不等于173份全部验收、八组交付链通过或授权启动后续真实评测。
