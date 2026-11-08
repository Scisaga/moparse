# MO-Parse：容量边界与固定集合验收续做入口

先读取AGENTS.md、benchmark/evaluation-tasks.md的当前合同、唯一Lite报告及其data/diagnosis-summary.json。/opt/mosaic-parse与/opt/moparse指向同一仓库。以现场HEAD、工作区、software_id、测试和独立断言身份为准，保留已有修改，不执行reset、覆盖checkout或clean，不主动提交或推送。

本轮只处理暂定对应占用容量的问题及接手时固定的18份独立来源验收。固定集合、接手覆盖与验收证据核验、授权selection、原始来源、要求摘要和最终逐项结果保存在benchmark/runs/lite/requirements/validation/actual-source-diagnosis.json的fixed_sample_acceptance。原18份没有替换；新增责任完整样本只能列为公共修复影响，不能补入固定集合。当前最终状态与身份见唯一报告，不继承旧4357项或旧software_id为新证据。

生产实现、完整授权来源断言和受控候选证据分别保存。容量对应由moparse_eval/requirement_ast.py::compare_document_ast及document_ast_comparison.py接入最终outcomes、blockers、分母和证据重放。已确认与暂定身份、排他缺失证明、语义四态及顺序的拥有定义见evaluation-tasks.md的“文档 AST 与内容比较”，合同仍为document_ast/1。semantic/1继续保持严格语义条件。

独立来源入口为tests/validation/lite_source_oracle.py；固定18份的手写原始行、结构、限定、数值和来源断言保存在tests/validation/lite_fixed_source_assertions.py，全部纳入验证身份。生产读取器和评分器不得导入这些手写答案。先依据完整授权文字建立独立断言，再调用read_expected、compile_requirement_graph、来源审计、图校验及evaluation_projection。不能从生产输出复制Oracle，不能把没有pending、自动枚举ID或编译与current一致当作独立验收，也不能把实际expected复制成candidate自比较。

每份通过样本必须绑定当前源码、唯一current中的生成视图、comparison_coverage、实际执行的逐来源case、义务与语言分析限制、独立能力用例及完整selection身份。正文保留证明允许承担尚未完整解释的陈述；已有数量、单位、期间、条件和业务关系继续使用经过验证的类型化比较器。完整内容与类型化责任须互不吞并、无遗漏、无重复计票，文字变化按所属合同处理。

华为huawei-operating-results-p062-063、顺丰sf-cashflow-assets-liabilities-p040-041、中石化sinopec-finance-governance-p025-036保留原完整来源Oracle。A/B/C继续保护顺丰L742、L781、L920三项声明及221项计量、华为L1586三项业务要求、平安L298首句0–76的一项命题及4条关系。发现回归须修实现或逐来源撤回验收，禁止改写旧Oracle迎合输出。

本轮补验涉及独立封面署名的错误拼接、冒号叙述误当标量、名词末尾“能”误当能力模态，以及连接分析跨度回到原始片段的责任归属。显式财务列声明与封闭标量记录仍交给既有读取器；不能扩大正文路由去吞掉已支持财务事实。具体来源、独立反例和投影变化见当前诊断及comparison-validation、mutations-validation、baseline-preservation，不另建Oracle平台、报告或通用语言解释器。

若源码或手写断言发生变化，先执行受影响受控用例，再以software-validation.json中保存的完整命令完成软件回归；测试输入保持独立合成。173份source-only重建使用 `.venv/bin/python -m moparse_eval.requirement_graph --baseline benchmark/runs/lite --output benchmark/runs/lite/requirements/<新的暂存目录> --workers 16`。先核对原始授权来源、selection、五个输入范围、A/B/C、每个B减少及合法分母变化，再替换唯一current并删除失效生成视图。退出码2可能表示集合外比较责任仍不完整，不删样本求0。

最终绑定命令为 `PYTHONPATH=/opt/moparse .venv/bin/python tests/validation/lite_source_oracle.py --output benchmark/runs/lite/requirements/validation/oracle-validation.json --diagnosis-output benchmark/runs/lite/requirements/validation/actual-source-diagnosis.json`。默认覆盖原三个基线和固定18份，必须在最终源码、同版比较能力证据和已安装current下重新执行；--fresh-only只用于开发。源码、测试、手写断言、能力用例、索引和生成视图不一致时不得沿用旧验收。

全局来源责任、逐样本独立验收、比较能力、真实格式读取和交付回放仍为不同门禁。固定集合全部有结论不等于全部通过；18份通过也不等于173份通过。下一步只按用户新的明确授权推进，不能自动展开其余样本的完整修复、选择新的公司长文作语法主线或启动真实评测。全部质量成绩继续暂停。

五个输入范围保留原身份：Alibaba L230、Midea L417、PBOC L540，以及PBOC L252的两项既有选段。软件缺陷与输入授权问题分列，不能删成员、裁段或忽略目标。Alibaba L2353的两种附着及未经批准的多解释合同保持原状态。

canonical expected、原始映射、selection、页包、语料、有效native、历史交付正文和原始成本只读。本阶段禁止原始PDF、图片、字层、OCR/VLM、模型服务或裁判、实际候选比较、真实native到final回放、正式保存输出评分、GPU/TTS/在线服务操作、部署、公开API修改、提交、推送及质量排名。候选只用于独立合成受控测试，P01–P08标签参数化不代表八种原生适配链验收。分析使用16个CPU进程，不改变原管线或隔离后处理的资源合同。

只维护benchmark/reports/lite/report.md及现有诊断、验证目录。原始处理成本不重测、不改写；不向AGENTS.md追加本任务全文。通用检查永久排除pdf_sample、datasets、benchmark/reference-decisions、benchmark/runs和benchmark/reports，包括显式路径调用。来源验收、软件回归与原始材料的真实性审核保持各自边界。
