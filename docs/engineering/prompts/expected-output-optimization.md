# MO-Parse：新增23份独立验收与一个公共比较责任修复

先读取AGENTS.md、benchmark/evaluation-tasks.md的当前合同、唯一Lite报告及其data/diagnosis-summary.json。/opt/mosaic-parse与/opt/moparse指向同一仓库。以现场HEAD、工作区、software_id、测试和独立断言身份为准，保留已有修改，不执行reset、覆盖checkout或clean，不主动提交或推送。

固定18份、后续11份和BIS L838、L948、L674及IEA L588、L730五处局部来源修复已完成。原18份与华为、顺丰、中石化、后续11份合计32份转为回归保护；fixed_sample_acceptance、additional_sample_acceptance和cross_fragment_source_review保留历史批次身份。本轮固定上一轮明确列出的23份责任完整但缺少独立验收的样本，逐份阅读全部授权expected文字与结构、预先声明实质断言和表示策略，完成独立审查并绑定最终证据；在同一诊断的review_sample_acceptance保存清单及结果，不替换旧批次或正式manifest。同时从真实诊断选择一个有至少两个真实来源证明的公共实现根因，修复并核验全部同类命中范围，不扩展为118份全文修复或通用语言解析重建。当前状态只见唯一Lite报告。

接手HEAD为997dd9157344a586de4804566f57d3a99396d083，工作区干净，software_id和current索引与上一轮记录一致。接手时全局仍有118份比较责任缺口和固定23份待独立审查；这些是接手状态，不是本轮结果。173份来源、selection及五个输入范围保持。23份全部必须有通过、修复后通过、具体覆盖退回、真实外部阻塞或尚未审查的明确状态；不要求无条件全部通过。IEA训练能耗样本须完整审查，旧L730局部通过不能替代整份验收。

固定23份现已完成全部940个授权来源的独立阅读和断言执行：0份通过、23份退回、外部阻塞及未审查0份。唯一公共生产修复为完整内容数字的同源计量角色守卫，拒绝将日期、引用、计划/模型/证券标识的等值数码改写直接视为数量等价；影响3094个真实来源、164份视图，不授予集合外整样本验收。完整内容与已撤下局部命题父归属重复计票另列具体退回，不在本轮展开第二公共修复。原32份当前29份通过，CATL新能源市场L1826、飞亚达L192、PBOC封面L5的旧验收已明确撤回；旧批次身份保留。L298首句命题及4关系在分析层保留，但typed/mixed比较责任未保留，旧分析保护不能作为比较验收。当前结果只见唯一Lite报告；不要把已完成来源审查再次当作尚未审查，也不要把退回写成通过。

生产实现、完整授权来源断言和受控候选证据分别保存。容量对应由moparse_eval/requirement_ast.py::compare_document_ast及document_ast_comparison.py接入最终outcomes、blockers、分母和证据重放。已确认与暂定身份、排他缺失证明、语义四态及顺序的拥有定义见evaluation-tasks.md的“文档 AST 与内容比较”，合同仍为document_ast/1。semantic/1继续保持严格语义条件。

独立来源入口为tests/validation/lite_source_oracle.py；原18份及11份断言保留在tests/validation/lite_fixed_source_assertions.py；新增23份的声明分列在lite_review_alibaba_assertions.py、lite_review_hkex_assertions.py和lite_review_energy_assertions.py，独立数字角色反例在lite_review_numeric_role_cases.py，均通过同一入口执行并纳入聚合身份。生产读取器和评分器不得导入这些手写答案。先依据完整授权文字建立独立断言，再调用read_expected、compile_requirement_graph、来源审计、图校验及evaluation_projection。不能从生产输出复制Oracle，不能把没有pending、自动枚举ID或编译与current一致当作独立验收，也不能把实际expected复制成candidate自比较。

每份通过样本必须绑定当前源码、唯一current中的生成视图、comparison_coverage、实际执行的逐来源case、义务与语言分析限制、独立能力用例及完整selection身份。正文保留证明允许承担尚未完整解释的陈述；已有数量、单位、期间、条件和业务关系继续使用经过验证的类型化比较器。完整内容与类型化责任须互不吞并、无遗漏、无重复计票，文字变化按所属合同处理。

华为huawei-operating-results-p062-063、顺丰sf-cashflow-assets-liabilities-p040-041、中石化sinopec-finance-governance-p025-036保留原完整来源Oracle。A/B/C继续保护顺丰L742、L781、L920三项声明及221项计量、华为L1586三项业务要求、平安L298首句0–76的一项命题及4条关系。发现回归须修实现或逐来源撤回验收，禁止改写旧Oracle迎合输出。

已完成阶段修复了独立封面署名的错误拼接、冒号叙述误当标量、名词末尾“能”误当能力模态，以及连接分析跨度回到原始片段的责任归属。显式财务列声明与封闭标量记录仍交给既有读取器；不能扩大正文路由去吞掉已支持财务事实。具体来源、独立反例和投影变化见当前诊断及comparison-validation、mutations-validation、baseline-preservation，不另建Oracle平台、报告或通用语言解释器。

若源码或手写断言发生变化，先执行受影响受控用例，再以software-validation.json中保存的完整命令完成软件回归；测试输入保持独立合成。173份source-only重建使用 `.venv/bin/python -m moparse_eval.requirement_graph --baseline benchmark/runs/lite --output benchmark/runs/lite/requirements/<新的暂存目录> --workers 16`。先核对原始授权来源、selection、五个输入范围、A/B/C、每个B减少及合法分母变化，再替换唯一current并删除失效生成视图。退出码2可能表示集合外比较责任仍不完整，不删样本求0。

最终绑定命令为 `PYTHONPATH=/opt/moparse .venv/bin/python tests/validation/lite_source_oracle.py --output benchmark/runs/lite/requirements/validation/oracle-validation.json --diagnosis-output benchmark/runs/lite/requirements/validation/actual-source-diagnosis.json`。默认入口实际执行原32份回归、新增23份及五处有限来源审查，逐来源断言先于生产编译；新增23份逐源收集实质失败并继续检查后文，退回不伪装通过。`--sample SAMPLE_ID`仅用于局部开发，`--cross-fragments-only`仅审查五处而不接受其所属四份整样本。必须在最终源码、同版比较能力证据和已安装current下重新执行；--fresh-only只用于开发。源码、测试、手写断言、能力用例、索引和生成视图不一致时不得沿用旧验收。

全局来源责任、逐样本独立验收、比较能力、真实格式读取和交付回放保持独立门禁。新增23份全部完成实质审查后，最终源码须复验原32份及五处有限来源，保护A/B/C及接手1639项完整计量的实际payload、来源和限定。核验唯一公共根因的全部同类真实范围，集合外责任完整的样本仅记待独立验收。源码与断言冻结后完成受控回归、173份同源码JSON/XML重建、全部合法B/L变化及来源范围核验，再将验收绑定最终current。不扩大reason白名单、削减分母、吞掉完整计量或以没有pending宣称完成；退出码2的实际诊断须保留。全部质量成绩继续暂停。

五个输入范围保留原身份：Alibaba L230、Midea L417、PBOC L540，以及PBOC L252的两项既有选段。软件缺陷与输入授权问题分列，不能删成员、裁段或忽略目标。Alibaba L2353的两种附着及未经批准的多解释合同保持原状态。

canonical expected、原始映射、selection、页包、语料、有效native、历史交付正文和原始成本只读。本阶段禁止原始PDF、图片、字层、OCR/VLM、模型服务或裁判、实际候选比较、真实native到final回放、正式保存输出评分、GPU/TTS/在线服务操作、部署、公开API修改、提交、推送及质量排名。候选只用于独立合成受控测试，P01–P08标签参数化不代表八种原生适配链验收。分析使用16个CPU进程，不改变原管线或隔离后处理的资源合同。

只维护benchmark/reports/lite/report.md及现有诊断、验证目录。原始处理成本不重测、不改写；不向AGENTS.md追加本任务全文。通用检查永久排除pdf_sample、datasets、benchmark/reference-decisions、benchmark/runs和benchmark/reports，包括显式路径调用。来源验收、软件回归与原始材料的真实性审核保持各自边界。
