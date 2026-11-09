# MO-Parse Lite：新增11份独立验收与五处来源责任

新增11份已完成独立审查：11份通过、0份退回、0份受外部条件阻塞，未审查0份；其中6份修复后通过。五处跨片段来源责任全部闭合，局部剩余缺口0。原21份已在最终源码和唯一current下重新通过。以上是document_ast/1的source-only独立来源验收；全局仍未通过，质量成绩继续暂停。

## 固定新增批次与实际执行入口

接手HEAD为 `1c11b961d740ca961af9a5fc5f8b255a2b190cad`，接手工作区干净，/opt/mosaic-parse与/opt/moparse指向同一仓库。新增11份来自上一轮明确记录的集合外清单，与当前责任完整集合减去21份有效独立验收的差集一致，没有替换成员。旧18份历史身份继续保留在[actual-source-diagnosis.json](../../runs/lite/requirements/validation/actual-source-diagnosis.json)的fixed_sample_acceptance；本轮的完整声明、授权selection、来源身份、合同版本、接手视图及coverage摘要、能力和最终绑定位于additional_sample_acceptance。新增责任完整的其他23份单列，没有补入本批次或当作通过。

[独立入口](../../../tests/validation/lite_source_oracle.py)默认实际执行原21份、新增11份及五处有限来源审查。`--sample SAMPLE_ID`为局部开发入口，`--cross-fragments-only`只审查五处，不接受其所属四份整样本。[手写断言](../../../tests/validation/lite_fixed_source_assertions.py)分别保存旧ASSERTIONS、新ADDITIONAL_ASSERTIONS、表示策略、顺序组和五处原文断言；生产代码不导入这些答案。

11份的239个授权来源全部审查，包括explained内容；实际执行258个来源、空白或显式引用分隔、归属顺序case。每份证据位于[oracle-validation.json](../../runs/lite/requirements/validation/oracle-validation.json)的results[sample_id]，case_ids、requirement_ids、obligation_ids、analysis_limitation_ids及比较能力证明均在执行断言后绑定。没有用实际expected复制成candidate自比较。

| sample_id | document_id | 授权来源数 | 分析T/L/B节点 | 当前固定合同B/L | 结论 |
| --- | --- | ---: | ---: | ---: | --- |
| beijing-media-director-p001-003 | 1201816142 | 29 | 31/2/1 | 27/54 | 修复后通过 |
| fiyta-bond-followup-p011-017 | 1200778318 | 26 | 27/17/4 | 15/37 | 修复后通过 |
| huawei-audit-p066 | complex-huawei-2024-annual | 20 | 16/7/0 | 12/31 | 通过 |
| huaweitech-cover-p001 | complex-huaweitech-2024-096 | 15 | 11/4/2 | 12/23 | 通过 |
| huaweitech-middle-east-p021-023 | complex-huaweitech-2024-096 | 65 | 127/22/10 | 52/115 | 修复后通过 |
| midea-resumption-p001 | 1200767576 | 8 | 12/5/4 | 8/13 | 修复后通过 |
| pingan-honors-p020 | complex-pingan-2024-annual | 25 | 31/11/0 | 13/38 | 通过 |
| tangshan-directors-opinion-p001-002 | 1200975009 | 10 | 10/2/0 | 7/15 | 通过 |
| wuliangye-appeal-progress-p001 | 1201860324 | 17 | 21/8/3 | 13/27 | 修复后通过 |
| zhenye-correction-p001 | 1200799174 | 10 | 14/4/3 | 10/17 | 修复后通过 |
| zhenye-coupon-seals-p001-003 | 1200694910 | 14 | 22/12/7 | 13/22 | 通过 |

标题、图题、封面及签章只按授权文字和结构验收，不做图像理解。上下文标题及图题不额外虚构B事实；适用性不表示业务质量100分。表内分析节点与固定合同比较要求分列；本轮没有实际保存输出评分，因此没有实际候选分子、成绩或正式冻结分母。

## 五处来源的首个失败点与修复

这五处分别属于BIS的bis-fiscal-productivity-policy-p042-051、bis-policy-boxes-p026-034，以及IEA的iea-infrastructure-capabilities-p032-036、iea-training-energy-p041-042，和新增11份没有交集。文档分别为complex-bis-economic-2024和complex-iea-energy-ai-2025；原路径、全文、完整selection、旧撤回责任及阻塞义务、前后分析和原始跨度、最终要求与剩余义务见同一诊断的cross_fragment_source_review，执行证据在oracle-validation.json的source_span_results。

| 原始来源 | 首个实际失败点 | 当前合法责任 |
| --- | --- | --- |
| BIS L838 | 命题范围解释未闭合时，语言分析路由拒绝了该原始脚注范围；本处没有joined_fragments，不能谎称是连接坐标错误。 | 完整保留五条脚注、引用、日期、ICs所属描述和原始顺序；固定原来源0–688，单独内容要求，原17项分析限制保留。 |
| BIS L948 | 分词解释未闭合被当作不能由内容合同承担，导致整段没有责任。 | 原来源0–469保留last year与today、below 1.6%与1%、GDP及人口和地缘限定，原10项分析限制保留。 |
| BIS L674 | 前置名词范围解释未闭合阻止完整内容接手。 | 原来源0–98保留In addition to限定与主句，原1项分析限制保留。 |
| IEA L588 | 未加句号的L586和L588的独立有限句被连接，首句分析沿用了前一原始来源身份。 | 停止错误连接；按L588自己的0–883承担完整供应链正文，ASML、Carl Zeiss及地域和限定不借邻源；原23项分析限制保留。 |
| IEA L730 | L728未加句号的训练能耗callout错误连接了独立上标脚注。 | 脚注从L728拆开，L730原始0–62保留⁴与never及maximum designed限定；原1项分析限制保留。 |

五处各新增一份固定内容责任，局部对应B要求加1、范围及顺序L要求加2；没有强行恢复旧节点或旧数量。共享修复还影响四份中的其他来源，整样本固定B/L分别为44/148到59/181、45/126到60/157、14/40到19/50、9/23到13/31；这些更大变化的逐来源证据另见additional_sample_acceptance.final_rebuild_comparison，不能都计作五处成果。

本次五处均无剩余局部责任缺口。其所属整样本没有因局部审查取得独立验收；前述前三份另有5、19、105项阻塞义务及5、20、8项阻塞分析限制。训练能耗样本虽由共享修复取得完整比较责任，仍列在未独立验收的23份中。

连接分析只作连续表达记录。original_source_cuts在所属第一片段的分析坐标与各原始片段局部半开字符区间之间显式投影，检查非零起点、各片段顺序、首尾部分使用、真实空白与投影空白、插入空格及原身份。来源复核拒绝片段调序、删除、平移、替换和跨插入内容取字。不能跳过标题、图片、表格、列表边界或原文分号；原21份回归暴露的CATL L1952与SF L550分号跳过问题已作通用边界修复，原文及原分析义务保留。

跨片段部分解释若由内容接手，必须为该陈述所有实际原始片段建立责任，并检查相同范围、父级和连续结构，避免只补尾段却保留同一整句的类型化票。完整数量仍精确分区保留类型化比较，不以任意重叠ID、忽略text_span、邻源借值或reason批量豁免使其通过。本文正文合同的范围和顺序也有独立候选反例，不以字符区间并集证明关系。

## 新增审查发现的具体缺陷与表示策略

北青公告及中东文章的冒号标题原来生成虚构标量字段；现在保留标题全文及层级。括号字段如（股份代號：1000）原来被切成不平衡的标签和值；现在按预先声明的完整内容责任保留。飞亚达L192的“不存在对外担保（不包括对子公司的担保）”不能由一个负向includes及残缺actor解释；独立来源守卫拒绝该完整类型化解释，完整正文承担期间、否定及排除限定，原部分分析保留。

美的L5、五粮液L5与振业更正L5的宽空白分隔证券信息原来被吞进第一个值；现在保留各标签和值的原始跨度，分成实际打印的代码、简称和公告编号。中东文章L708/L713的URI scheme冒号不再成为https字段，完整引用文字仍保留。表格屏障的受控生产链还补齐了文档AST格位的已有native_path身份，未放宽来源匹配。

表示策略在读取任何候选前固定：A必须类型化的完整计量包括CATL L1779和L1793，以及明确声明的完整字段；B由完整内容负责的正文保持全文、范围、顺序和责任边界，不要求通用SVO；C仅为逐项指定、经完整断言验证的简单字段或短句允许两种完整表示。C仍检查完整覆盖、类型化端点、数量或期间关系、排他分区和固定计票规则，不能只判断own_content非空。没有将全部TYPED_ASSERTIONS机械改为强制类型化。

[表示策略反例](../../../tests/unit/test_fixed_source_oracle.py)直接验证必需计量被删除时，即使完整文字AST仍合法也不能通过，拒绝局部内容代替整段、责任重复、空洞及混合重叠；由完整内容负责的正文不因缺少SVO而被误拒绝。[跨片段生产链](../../../tests/unit/test_cross_fragment_source_ownership.py)由合成expected和授权声明开始，经read_expected、要求图、来源审计、投影、独立合成candidate、grade_layers及validate_evidence执行，覆盖多个片段、偏移、顺序、来源替换、屏障、脚注、混合责任和文字完整但归属顺序错误。

新写五粮液断言的一处标题层级曾误写H3，已依授权Markdown纠正为H2；新写标量断言曾把完整source当作value_source，已纠正并分别验证标签、值及单位来源。封面EM2.0模式的打印标签经完整来源审查明确为允许双表示的简单字段。这些是透明修正本轮新增Oracle；原21份已验收的实质预期未改写以迎合新输出。

## 合法要求变化与原21份保护

| 新增成员 | 接手固定B/L | 当前固定B/L | 原文依据 |
| --- | ---: | ---: | --- |
| beijing-media-director-p001-003 | 28/54 | 27/54 | L11是标题，L9的括号原文完整保留。 |
| fiyta-bond-followup-p011-017 | 15/41 | 15/37 | L192整句承担日期、否定及括号排除；撤销不能独立成立的局部关系票。 |
| huaweitech-middle-east-p021-023 | 55/113 | 52/115 | L628/L642/L658是标题；L708/L713是完整URI，仍有范围及顺序责任。 |
| midea-resumption-p001 | 6/11 | 8/13 | L5实际打印三项证券元数据，补回另两项。 |
| wuliangye-appeal-progress-p001 | 11/25 | 13/27 | L5实际打印三项证券元数据，补回另两项。 |
| zhenye-correction-p001 | 8/15 | 10/17 | L5实际打印三项证券元数据，保留“深振业 A”的原字。 |

其余新增5份固定B/L不变。新增批次合计固定B/L从180/388变为182/392；这是expected固定责任的合法变化，不是实际候选成绩。候选分块或表现没有改变这些数量。

原21份的最终当前绑定证据位于additional_sample_acceptance.original_21_final_regression及oracle-validation.json；旧18份历史身份没有覆盖。A保留三项声明及221项计量，B保留华为L1586三项要求，C保留平安L298首句一项命题及4条关系的原payload。旧三个完整来源Oracle的实质断言保持，当前结果在[baseline-preservation.json](../../runs/lite/requirements/validation/baseline-preservation.json)重新绑定。

173份的原始来源数组、selection及五个输入范围逐份保持；派生来源数组也173份全部保持。104份分析或固定合同投影变化保存在final_rebuild_comparison.contract_deltas_by_source；89处分析B减少逐来源保留原文、前后事实、最终内容或结构责任及具体理由。旧完整计量事实另核对1639项，丢失0，未把完整类型化计量吞进正文。这些集合外回归核对不提供其余样本完整独立验收。

## 最终同版证据与全局边界

[完整受控回归](../../runs/lite/requirements/validation/software-validation.json)为 `4426 passed in 256.91s (0:04:16)`，181个测试文件；受测源码与测试身份在执行期间保持。software_id为 `8752b11786c4ec6936ddc23840958e1e1a15dd9cf955fbcd03ef7a09b01efc78`，tests_sha256为 `9fddc0721c8940d2e3cd54e20e2bd9c846bd01a38ec69e371b63247817a33a41`。40种受控能力和599项突变或反例记录在comparison-validation.json、mutations-validation.json及regression.xml；受控能力不等于真实原生格式读取或八组交付链通过。

[唯一current索引](../../runs/lite/requirements/current/index.json)以16个分析进程重建173份JSON/XML，耗时154.23秒，来源完整性失败0。索引SHA-256为 `57914c6120086236ecaa6e4e03e9e93cc74481f21662c543cbd8e7fbe3e29bc4`；最终Oracle SHA-256为 `64e134be8f984ad96b0aa50c212420c941245dc2d94456e9c743201d9ae8ac74`。32份及五处均重新编译并与已安装current绑定，源码、测试、手写断言、索引、生成视图、coverage与执行能力证明一致。失效生成视图已删除。

最终命令为 `PYTHONPATH=/opt/moparse .venv/bin/python tests/validation/lite_source_oracle.py --output benchmark/runs/lite/requirements/validation/oracle-validation.json --diagnosis-output benchmark/runs/lite/requirements/validation/actual-source-diagnosis.json`。最终退出码0。重建退出码2对应仍未覆盖的集合外责任，保留原样，不删样本求0。

| 全局维度，允许重叠 | 当前数量 |
| --- | ---: |
| 来源或结构不完整 | 0 |
| 比较责任仍有未覆盖 | 118 |
| 完整责任但缺少独立样本验收 | 23 |
| 独立来源及合同验收 | 32 |
| 仅保留语言分析限制 | 50 |
| 含既定输入范围问题的视图 | 5 |
| 既定输入范围目标 | 5 |

全局仍为structure_blocked，来源结构、比较能力和交付转换三个全局门禁均未通过。23份新出现的责任完整视图只列在本轮诊断，没有替换新增11份，也没有开始其完整修复。真实格式读取、全范围保存输出诊断、八组真实回放及正式评分均未验收。五个输入范围保持Alibaba L230、Midea L417、PBOC L540和PBOC L252两项原身份；Alibaba L2353两种附着及未经批准的多解释合同保持。

当前HEAD仍为接手提交；本轮代码、测试及文档留在未提交工作区，没有提交或推送。Ruff指定致命错误规则、非语料Markdown政策及排除受保护路径的diff空白检查通过。原始处理成本及下列原始观测尾段保持；本轮source-only软件时间没有并入解析性能。

本轮未读取原始PDF、图片、字层，未运行OCR、VLM、模型或裁判、实际候选比较、真实回放、正式保存输出评分、GPU/TTS或在线服务操作、部署、公开API修改或质量发布。canonical expected、映射、selection、页包、语料、native、历史交付与原始成本保持只读。候选仅为独立合成测试。下一步只按新的明确授权推进；续做入口为[expected output optimization](../../../docs/engineering/prompts/expected-output-optimization.md)。

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
