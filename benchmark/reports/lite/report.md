# MO-Parse Lite：集成修复与真实 expected 来源诊断

完整任务仍未完成，质量成绩继续撤回。本轮修复既有读取器、来源审计、要求投影和最终判定之间的不一致，并以授权 expected 文字重新编译全部173份派生视图；没有运行真实候选比较或后处理回放。canonical expected、输入映射、原生结果、历史交付正文及原始成本没有写入。

开始时 HEAD 为 `2bc7a6f6322d3625fde1d32d92e1f08e765cdc53`，工作区干净；修复验证阶段没有回退。Git交付按后续独立用户指令执行。最终评测源码身份为 `b9e1499220f0b6ddcdce0099f526702ec080c7a3834d3d249ed73a5d30c15d9e`。[唯一要求索引](../../runs/lite/requirements/current/index.json)及173个worker均绑定该源码，索引 SHA256 为 `d1c4fee3f8ba51eccb78d283c54055ea4b04973d067b7507a230feb774e6a39e`。16个spawn分析进程完成source-only编译，来源完整性失败为0；退出码2表示语义仍未完成，不能解释成编译崩溃或通过验收。

[完整受控回归](../../runs/lite/requirements/validation/software-validation.json)为3770 passed in 62.02s，源码和测试在运行期间保持不变；[Oracle](../../runs/lite/requirements/validation/oracle-validation.json)、[Mutation](../../runs/lite/requirements/validation/mutations-validation.json)和[比较证据](../../runs/lite/requirements/validation/comparison-validation.json)均已绑定相同源码。测试只使用独立合成材料和受控结构；真实部分仅作expected来源编译与诊断。测试数量、空pending或源码身份不建立完整expected语义验收。

## 已复现并修复的生产路径问题

附件要求优先验证的四项均真实存在。六句 help、leverage、engage、capture 词形能被reader完整解释，却被独立来源审计拒绝；嵌套NP换序受raw object重复比较及共享所有者错置影响；完整AST判等未能纠正普通命题或关系的最终flat误拒；部分原有集成测试只经过 `compile_markdown`，没有覆盖完整expected入口。新增回归从临时原始expected和明确manifest选择进入 `read_expected → compile_requirement_graph → source obligation audit → validate_requirement_graph → evaluation_projection → 合成候选读取 → grade_layers → validate_evidence`，不预填business或semantic_complete。

| 位置 | 实际修复及边界 |
| --- | --- |
| action_forms.py；narrative、proposition、active_aspect；source_obligations._role_evidence | 抽取有限声明词形，解释与审计同义；未知词形仍未知，owns被伪造成acquire仍拒绝。来源义务仍独立枚举。 |
| nominal_syntax.nominal_phrase；requirement_ast.compare_requirement_ast | 共享determiner归属名词集合；仅在完整角色来源和全部词项闭合时，由结构承接raw object比较；原文继续用于来源校验和T。 |
| semantic_layer_comparison._business_responsibility、_relation_responsibility | 完整语义判等能改变本项最终B或L票。先验证独立身份、位置、scope、qualifiers、identity_facets、容量及记录约束；标量继续按既有精确数量契约判定。 |
| expected_report.validate_evidence | 从原flat证据和保留的源绑定语义输入重放相同责任分配，检查最终outcomes、分子和阻断，拒绝伪造正向结论。 |
| three_layer._Graph.prose；source_obligations._text_field_delimiters | 空标签保留末尾冒号或等号；已有准确label/value与attribute_source可证明中间delimiter。不得借邻源、丢文字或将数字当control。 |
| source_obligations.audit_source_obligations | 引用字段的label、directive、target分别按自己的来源桥接，验证实际owner及两条关系；没有真实同类来源收益，只有受控生产缺陷修复。 |
| represented_feature_comparison；enumeration_context；document_composition_requirements | 已有枚举、引用、文档组成和页码关系接入各自表示；来源路径留在binding证据，不作为另一文件必须相等的业务答案。 |
| cjk_measurement_requirements.emit；three_layer._Graph.ingest | 保留原已识别的数量、单位、币种及同比主体绑定证据，不增加业务事实或猜测期间。 |
| prose_requirements.prose_endpoint；requirement_ast._identity | 同指标不同年度按各自有来源的打印期间定位，保留逐候选拒绝trace；值和单位不参与选位置，无法确认期间来源时保持unresolved。 |

两组要求中的完整正例现在都得到最终B/L全票：`assets of its subsidiaries and affiliates`的内部成员换序，以及`two core businesses of e-commerce and cloud`换序。T保留字面差异。AND改OR、数量变化、成员缺失、所有者更换、附着变化、名词并列变成两个动作、缺事实或关系、缩短结构来源、额外身份限定、错期间或单位、重复和容量不足均不能靠AST正向判等恢复。

多年度受控例还验证：跨年交换全部数值时B为0而L保持100；句序倒置时B保持100、L为20/21。B/L各自使用完整要求，原文差异仍归T。以上均为软件用例结果，不是实际管线质量分数或交付改善。

## 真实来源已闭合的范围

[完整实际来源诊断](../../runs/lite/requirements/validation/actual-source-diagnosis.json)保存确切path、授权行段、格位和字符跨度、原文、修前证据、首个失败函数、连带pending及最终义务处置。按稳定来源比较，不依赖重编译后的临时节点ID。两类T问题合计244处、涉及72个实际样本；它们的T义务全部闭合，不能扩大解释成这些段落的B/L也已完成。

| 实际范围 | 首因及已确认结果 | 仍保留内容 |
| --- | --- | --- |
| 148处空标签，59个样本；例如Alibaba expected L176 `[0,83]` | 空字段分支丢弃末尾delimiter；最终148/148原文字义务均explained。 | B/L未知继续保留，未删难段或缩小选段。 |
| 96处已有label/value的文字桥接，32个样本；例如BYD L52 | 名词Report触发动作词检查，使准确文字之间的delimiter无法审计；最终96/96义务均explained。 | 只承接已保留的局部T原子，不替业务解释判等。 |
| 平安 expected L368 `[145,272]` | 已读出的leverages没有统一审计词义；该目标业务句局部pending由1变0，来源范围闭合。 | 所属样本其他语义仍blocked。 |
| 平安 L339 `[0,229]` | 相同词形审计修复了承接，局部pending由6变5。 | with和creating等附着仍未解释，整句没有闭合。 |
| Alibaba L114 `[303,328]`；NVIDIA L3203 `[92,120]` | their users and customers、our principles and practices的共享所有者已归属完整集合。 | 两样本仍blocked，不能把结构细化称为整个范围或样本验收。 |

全部173份视图的原始sources数组逐项保持一致；五个输入范围的sample、source、text及outside_selection保持一致。173个样本各自的T/L/B投影数量均未变化，总计仍为30090/18030/7731；它们是当前解释节点数，正式分母仍未冻结。没有通过删要求、改零、裁选段、移除未知或将剩余业务文字变成长字符串取得通过。

独立source扫描补入已受支持动作的有限词形后，20条semantic_content诊断转为proposition诊断，并暴露16条关系诊断记录。来源义务的类型和数量可因纠正漏建而合法变化；这些新增义务继续保留。当前非延期诊断记录33799变为33571，仍有109种reason/kind族，T pending由651变为407。诊断记录及族数不是业务题数或独立缺陷工作量，不得用净pending变化代替上述逐来源闭合证据。

没有原先blocked的实际样本整体新通过。仍有2份视图没有非延期语义pending，171份保留实际解释缺口；这2份也不能替代独立完整expected Oracle或真实交付验收。

## 既有特征比较的验收范围

本轮八类均已接入实际表示：document_composition、page_reference_binding使用现有typed文档结构及专用关系；explicit_reference_binding、enumeration_context_scope使用已有关系；quoted_nominal_scope使用名词角色proof和scope关系；shared_period_scope、same_subject_relative_clause、year_on_year_comparison使用已有计量结构、限定及同比主体绑定。未为满足门槛伪造narrative AST。

它们的“实现可用”和“有限独立生产链正反例通过”已经记录；完整真实格式和完整实际expected语义验收继续未通过。运行自比较只检查输入可被消费，不证明答案正确。独立复核还修复了将“未知组成条件仍保留pending”误标成feature就绪，以及将候选未解释的额外identity_facets用AST恢复正确的问题。受控支持不授权绕过后续门槛。

## 原始处理成本

以下为原始执行观测，单位为秒；不含本轮评分时间，没有重新运行解析或后处理。数值未改写或补零。原生边界为worker开始处理到原生产物及忠实导出就绪，初始化/预热单列。quality800为800输入页的一次执行，perf80为相同80输入页的三次执行；各轮值为原case处理时长之和，不是整批作业首尾墙钟时长，重复轮次不增加独立文档样本。每组native的173次quality执行及84次perf执行均记录completed，原始时长没有缺测；这是执行状态，不是内容正确率。逐轮值、初始化/预热、资源范围及缺测政策见[原始成本数据](data/processing-cost-summary.json)。

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

原生配置的CPU预处理分配为8核及8GiB内存、推理进程分配为4核及20GiB内存，自有评测GPU显存预算16GiB；原服务后处理为8核及8GiB内存、无GPU、并发1。原始执行存在TTS共驻和未受控制的活动：起止持久任务计数71至76，观测到5个新增任务；短调用可能没有被这些观测捕捉。不得据此宣称GPU独占或TTS空闲。数据分别保存分配与实测使用、RSS/cgroup峰值及观测覆盖；未记录的GPU指标保持未知，单页allocator峰值不等于整个设备占用。当前16个CPU评分进程不改变这些原执行资源与时长。

## 当前阶段与具体剩余阻塞

| 阶段 | 当前状态 |
| --- | --- |
| 来源传输及绑定 | 173份视图传输完整；全部局部业务关系绑定尚未完成。 |
| expected语义解释 | 未完成，171份仍blocked；244处T义务及L368局部闭合不能代表完整语义完成。 |
| 比较能力独立验收 | 既有28类有限受控证据可执行；完整比较能力验收未通过。 |
| 八组真实native到final交付链 | 未执行本轮真实验收；P07/P08历史配对保留，P01-P06不制造历史baseline。 |
| 统一评测执行 | 未启动全范围实际候选比较或保存输出重评分。 |
| 完整质量发布 | 继续撤回，无完整成绩或排名。 |
| 五个输入范围 | 全部目标保留，继续待确认，不删、不计零。 |

以下具体来源说明仍需解决的首个失败阶段；它们是授权expected文字的软件诊断，不是人工正式答案，也不是五个输入范围的新增延期。

| 授权文字及位置 | 首个失败与连带影响 | 下一处实现位置及约束 |
| --- | --- | --- |
| 平安 L298 `[0,76]`：We build a one-stop financial and daily-life service platform for customers. | build的for受益关系无argument frame；对象内financial and daily-life共head附着也未完整恢复，随后无事实、无边、义务pending。 | nominal_syntax._role和nominal_phrase的定语并列；须同时保全平台和受益者，不能仅加介词名单或opaque object。 |
| 华为 L1586 `[0,52]`：2024年实现销售收入人民币862,072百万元，同比增长22.4%。净利润为人民币62,574百万元。 | 现有有限计量reader只支持比较词起句，年后强制逗号；首个收入事实未建导致同比无先行指标，后句“为”也未解释。 | cjk_measurement_requirements._PERIOD/read_cjk_measurements及CJK谓词框架。净利润跨句是否共享年度须独立证明，不能静默借2024。 |
| 顺丰 L920 `[0,71]`：於12月31日，金額單位：人民幣千元。各項分別列示2024年金額、佔總資產比，2023年金額、佔總資產比，金額同比變動、佔總資產比重同比增減。 | compact已保存两年4列及金额变化，但日期和末尾比重变化未消费，继而T projection incomplete与叙事兜底pending。 | compact_requirements.read_compact_schema/_controls。保留月日basis和第二变化列；该句未印比重变化单位，不得猜百分点。 |

这些问题继续区分文字投影、reader与audit不一致、关系承接、真正缺失语义、已有解释未接比较及授权文字歧义。实际Alibaba L2353的共享名词head歧义仍保留原文和候选解释，未用PDF或强制附着选答案；同一分句的根因和随后无事实、无关系、无disposition不会当作多个独立语法任务。

最小复现入口是 `software-validation.json` 内记录的完整pytest命令，以及 `source-export.json` 内的16进程source-only编译命令。编译器拒绝覆盖现存派生目录；本轮仅在保留修前诊断快照后重建唯一current目录，成功写出全部173份后移除临时旧派生目录，没有保留平行索引或归档错误评分产品。

继续工作应从以上确切来源和首个失败函数修复通用实现，再沿完整expected生产链回到全部同类范围。所有非授权未决语义和相应独立比较验收真正通过后，才按原批准计划进入八组真实交付链、16进程保存输出评分及受限CPU后处理回放；阶段限制不代表以后永久禁止回放。本轮没有执行真实候选比较、真实回放、模型、GPU、TTS、服务操作、部署或公开API修改。Git交付按后续独立用户指令执行。
