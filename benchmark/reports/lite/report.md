# MO-Parse Lite：新增23份独立审查与数字角色责任修复

新增23份已完成独立审查：0份通过、23份退回、0份受外部条件阻塞；公共根因「完整内容数码误用数量等价」已修复，影响3094个真实来源、164份样本。940个授权来源全部阅读并实际执行逐源断言，未审查0份。以上是source-only软件和来源责任验收，不是管线质量成绩。

## 固定23份与逐项结论

接手HEAD为997dd9157344a586de4804566f57d3a99396d083，工作区干净，源码与索引身份匹配交接记录。固定23份来自上一轮明确清单，与责任完整集合减原32份的差集一致，没有替换成员或修改manifest。旧18份及旧11份历史身份保留；本轮清单、完整selection、原始来源身份、接手与最终view/coverage摘要、固定B/L、能力依赖及实质失败保存在[actual-source-diagnosis.json](../../runs/lite/requirements/validation/actual-source-diagnosis.json)的review_sample_acceptance。

统一入口为[tests/validation/lite_source_oracle.py](../../../tests/validation/lite_source_oracle.py)，默认实际执行55份及五处有限来源。新23份逐源执行，失败后继续后文；来源case的expected来自预先手写声明，生产输出只作为observed。每份执行证据见[oracle-validation.json](../../runs/lite/requirements/validation/oracle-validation.json)的results[sample_id]；case_ids、已验收要求、observed失败要求、obligations及analysis limitations分别保存，不用自动枚举ID证明通过。

| sample_id | document_id | 授权来源 | 固定合同B/L | 结论及最小具体缺口 |
| --- | --- | ---: | ---: | --- |
| alibaba-company-overview-p006-008 | complex-alibaba-2025-annual | 35 | 20/63 | 退回：L114 父归属重复计票 |
| alibaba-mission-values-p003 | complex-alibaba-2025-annual | 14 | 10/38 | 退回：L39 父归属重复计票 |
| alibaba-risk-summary-p105-108 | complex-alibaba-2025-annual | 70 | 65/152 | 退回：L2258 父归属重复计票 |
| alibaba-shareholder-letter-p004-005 | complex-alibaba-2025-annual | 29 | 24/61 | 退回：L56 不完整类型化解释；L76 父归属重复计票 |
| bis-endnotes-technical-annex-p052-057 | complex-bis-economic-2024 | 65 | 63/139 | 退回：L968 父归属重复计票 |
| byd-bilingual-review-p013-024 | complex-byd-2024-annual | 67 | 46/125 | 退回：L345 父归属重复计票 |
| hkex-chairman-statement-p017-020 | complex-hkex-2024-annual | 39 | 30/75 | 退回：L366 父归属重复计票 |
| hkex-contents-p003 | complex-hkex-2024-annual | 33 | 26/46 | 退回：L13 父级责任缺失；L15 25项目录角色/页码及父组证明缺失 |
| hkex-independent-auditor-p137-141 | complex-hkex-2024-annual | 78 | 61/155 | 退回：L4312 父归属重复计票 |
| hkex-nomination-governance-p105-108 | complex-hkex-2024-annual | 76 | 57/151 | 退回：L3225 父归属重复计票 |
| hkex-operational-timeline-p008-009 | complex-hkex-2024-annual | 53 | 45/78 | 退回：L123 父归属重复计票 |
| hkex-strategic-message-p007 | complex-hkex-2024-annual | 6 | 5/12 | 退回：L70 父归属重复计票 |
| iea-energy-manufacturing-p037-040 | complex-iea-energy-ai-2025 | 31 | 20/68 | 退回：L647 父归属重复计票 |
| iea-inference-energy-boxes-p043-048 | complex-iea-energy-ai-2025 | 44 | 35/91 | 退回：L753 父归属重复计票 |
| iea-rise-ai-p021-024 | complex-iea-energy-ai-2025 | 33 | 21/58 | 退回：L434 父归属重复计票 |
| iea-training-energy-p041-042 | complex-iea-energy-ai-2025 | 16 | 13/31 | 退回：L707 父归属重复计票 |
| nvidia-definitions-p017 | complex-nvidia-2025-annual | 50 | 49/67 | 退回：L466 父归属重复计票 |
| pingan-chairman-p014-019 | complex-pingan-2024-annual | 32 | 27/93 | 退回：L504 父归属重复计票 |
| pingan-integrated-finance-p022-024 | complex-pingan-2024-annual | 45 | 23/64 | 退回：L658 父归属重复计票；L668 不完整类型化解释 |
| pingan-mission-opportunities-p006-007 | complex-pingan-2024-annual | 30 | 18/48 | 退回：L231 父归属重复计票 |
| pingan-results-announcement-p001 | complex-pingan-2024-annual | 16 | 14/29 | 退回：L21 父归属重复计票 |
| pingan-strategy-cards-p008-011 | complex-pingan-2024-annual | 53 | 36/82 | 退回：L291 父归属重复计票；L298 指定typed/mixed责任缺失 |
| tencent-enforcement-notices-jurisdiction-p149-151 | complex-tencent-2025-bond-programme | 25 | 19/46 | 退回：L2091 父归属重复计票 |

所有explained内容均纳入审查。标题、父级、列表、图题、记录、签章、完整数字/单位/期间/限定/否定/顺序及不适用的正面依据保存在三份手写声明模块。图题只审查文字与结构，不读取图像；零项不适用没有被写成100分。IEA训练样本完整审查16个来源，L730仍通过局部复验，L707/L709等整样本计票缺口没有因此获准。

## 唯一公共生产修复

首个失败函数是moparse_eval/requirement_ast.py::_content_token_equivalence：旧实现仅因词面token为number，就调用数量无损等价，错误接受日期、法条、计划、模型版本及证券代码的等值数码改写。两个实际授权来源为NVIDIA L452的Item 402(v)/Regulation S-K，以及IEA训练L722的as of 24 March 2025；它们进入同一完整内容数字比较路径。没有把真实expected复制成candidate，也没有比较真实候选。

read_content_ast现在保留数字的同源比较角色及有限本地计量依据和单位跨度，validate_content_ast从原文重新核验这些信息。只有有明确计量依据的内容数字调用既有number等价；没有所属角色证明的等值数码改写保持unresolved，完整要求和分母保留，相关层不发布成绩。完整typed数量、期间、字段身份及文本值继续使用原比较器。数量18小時到18.0小時、有限单位/限定词变化仍受控通过；日期和引用不再借用该规则，T仍保留字面差异。

全部同类实际范围已在173份来源图重新编译和来源校验中核验：3094个原始来源、164份样本视图，集合外141份没有因此获得整样本验收。修复只改变来源绑定的数字角色证据；分析T/L/B、固定B/L要求、来源与责任分区均未变化，合法分母变化为0。具体逐来源命中见shared_comparison_responsibility_repair.affected_scope；不是按pending条数估算收益。

独立[数字角色用例](../../../tests/validation/lite_review_numeric_role_cases.py)执行13组、39个变体：12组36个变体通过；原security-code单句的3个变体保留为独立的重复L责任失败，没有改预期L1去迎合L2，也不计为已验证数字能力。额外19项生产链测试覆盖合法计量变化、近似非等价、角色/单位来源删除和伪造、邻源借用、错误范围、最终outcomes、固定分母及证据重放。最终结果均绑定同一源码、测试、断言和current。

## 审查退回与旧验收纠正

完整内容已经承担整段及其明确父范围后，生产仍保留已撤下局部命题的prose_heading_membership，并另计完整内容document_scope，形成重复父归属票。独立单句控制和真实HKEX L390、L4350证实相同范围及关系；其他来源逐一核对原文、完整内容跨度、已撤下B端点和相同父范围后退回，未按同一行号或reason字符串直接豁免。该第二根因仅建立失效验收守卫和具体诊断，本轮没有修改生产实现去展开第二公共包。

另有Alibaba股东信L56将前置年度句吞成actor、HKEX目录L13父级和25项导航角色缺失、Ping An L668舍入注记错误modal object，以及策略L298/L309/L328的必需typed/mixed责任缺失。完整文字保留不能覆盖这些合同缺口；没有以reason白名单、删除要求或缩小分母使其通过。

原32份最终复验为29份通过、3份旧验收撤回。华为、顺丰、中石化三个完整Oracle通过；撤回的是catl-nev-battery-markets-p127-132 L1826、fiyta-bond-followup-p011-017 L192、pboc-cover-p001 L5，均为已有父归属重复责任。历史批次记录和旧实质断言保持，当前撤回见review_sample_acceptance.original_32_final_regression，不把错误验收静默保留。

五处BIS L838/L948/L674、IEA L588/L730在最终current下全部通过，仍仅为局部来源证据。A保留顺丰三项声明及221项计量，B保留华为L1586三项要求。C的原一项命题及4条关系在分析层完全保留，但新审查证明它们没有作为首句typed/mixed比较责任保留；旧“只核对分析payload”的保护不足已明确撤回，不能宣称C比较责任通过。

1639项完整计量的真实保护范围已确认：保留B中可由既有exact_number读取数值且有明确unit限定的要求，属于2321项保留数值事实的子集。逐来源、值、单位、期间、限定及完整payload核对无丢失或降级；173份全部分析B payload及关系也完全保持，不只检查数量相等。证据见[baseline-preservation.json](../../runs/lite/requirements/validation/baseline-preservation.json)和final_rebuild_comparison。

## 最终同版验证与全局门禁

完整受控回归为4453 passed in 234.45s (0:03:54)，源码、测试、手写断言在执行期间不变。software_id为`6c6a6e709df49536fa69e0ab8fe8a3b4ab124147db8c4d3daa93493393b5f37b`，tests_sha256为`b61adb05198ac9801c4cc55db2aec50f282e6b0bfcdb6cb56479530f9c29a3cb`，手写断言聚合身份为`fc978dd00d1c8ef09a6b5bebbcedf2c6f1f6038e35f02c35c2c7cef698912b45`，唯一current索引为`6cbcd359ce4ce56363ea2690595b1c58f9b1ffcf2aa0ce4b1efac248cbd8b70a`。原4452项开发执行因手写模块在运行期间变化，已由这次冻结后执行替代，未作为最终验收。

173份JSON/XML由16个CPU分析进程同源码重建，来源完整性失败0，退出码2对应保留的集合外责任及五个输入范围；不是来源编译失败。最终Oracle退出码1对应真实退回和旧验收撤回，940/940新来源已执行，未反复运行相同命令求0。暂存视图完成保真核对后替换唯一current，失效生成视图已删除。Ruff指定规则、非语料Markdown政策和排除受保护路径的diff空白检查通过。

| 当前独立维度 | 数量 |
| --- | ---: |
| 编译比较责任仍有缺口 | 118 |
| 编译责任完整但缺少有效独立验收 | 26 |
| 当前有效独立来源及合同验收 | 29 |
| 固定23份已审查 / 未审查 | 23 / 0 |
| 既定输入范围目标 | 5 |

这些维度不机械相加。编译责任完整不是独立验收；本轮数字角色修复没有让集合外新增整样本通过。五个输入范围保留Alibaba L230、Midea L417、PBOC L540和PBOC L252两项原身份；Alibaba L2353的两种附着及未批准的多解释合同保持。来源结构、比较能力、真实格式读取、全范围保存输出诊断及交付转换门禁仍未通过，全局为structure_blocked，质量成绩继续暂停。

本轮未读取原始PDF、图片或字层，未运行OCR、VLM、模型服务或裁判、实际候选比较、真实native到final回放、正式评分、GPU/TTS或在线服务操作、部署、公开API修改、提交、推送或质量发布。canonical expected、原始映射、selection、页包、语料、有效native、历史交付和原始成本保持只读。仅独立合成candidate用于受控比较；P01–P08标签或受控测试不代表八组原生适配链通过。续做入口见[expected output optimization](../../../docs/engineering/prompts/expected-output-optimization.md)。

## 原始处理成本

以下为原始执行观测，单位为秒；不含本轮source-only软件耗时，没有重新运行解析或后处理。数值未改写或补零。原生边界为worker开始处理到原生产物及忠实导出就绪，初始化/预热单列。quality800为800输入页的一次执行，perf80为相同80输入页的三次执行；各轮值为原case处理时长之和，不是整批作业首尾墙钟时长，重复轮次不增加独立文档样本。每组native的173次quality执行及84次perf执行均记录completed，原始时长没有缺测；这是执行状态，不是内容正确率。逐轮值、初始化/预热、资源范围及缺测政策见[原始成本数据](data/processing-cost-summary.json)。

| 原生组 | quality800 | perf80中位数（最小–最大） |
| --- | ---: | ---: |
| P01 | 1565.35 | 199.90（199.42–201.00） |
| P02 | 1478.30 | 186.33（186.27–187.19） |
| P03 | 11576.99 | 937.51（893.87–1001.96） |
| P04 | 11826.90 | 778.31（778.19–967.77） |
| P05 | 2908.12 | 276.46（275.32–278.23） |
| P06 | 1619.34 | 202.44（202.14–202.87） |
| P07 | 2411.70 | 276.90（274.57–279.99） |
| P08 | 3327.53 | 311.49（310.53–316.18） |

服务表保留既存实际正文的独立CPU后处理成本；本次八组新回放尚未执行，不继承这些时长为新实现测量。后处理成本不与native相加或解释为新的端到端时长。右列为quality800实际执行状态，partial和警告均保留，不转为质量分数或采用依据。

| 服务后处理组 | quality800 | perf80中位数（最小–最大） | completed / warnings / partial / failed |
| --- | ---: | ---: | --- |
| P07 baseline | 216.09 | 28.02（27.74–28.40） | 126 / 16 / 31 / 0 |
| P07 current | 216.84 | 28.04（27.91–28.22） | 126 / 16 / 31 / 0 |
| P08 baseline | 194.05 | 28.91（28.82–29.27） | 127 / 14 / 32 / 0 |
| P08 current | 181.99 | 27.37（27.18–27.39） | 128 / 14 / 31 / 0 |

原生配置的CPU预处理分配为8核及8GiB内存、推理进程分配为4核及20GiB内存，自有评测GPU显存预算16GiB；原服务后处理为8核及8GiB内存、无GPU、并发1。原始执行存在TTS共驻和未受控制的活动：起止持久任务计数71至76，观测到5个新增任务；短调用可能没有被这些观测捕捉。不得据此宣称GPU独占或TTS空闲。数据分别保存分配与实测使用、RSS/cgroup峰值及观测覆盖；未记录的GPU指标保持未知，单页allocator峰值不等于整个设备占用。本轮16个CPU分析进程仅用于source-only要求图重建，不改变原执行资源与时长。
