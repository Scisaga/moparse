# MO-Parse Lite：第四阶段固定5份独立验收

新增5份已完成独立审查：0份通过、5份修复后通过、0份退回、0份受外部条件阻塞。未完成审查0份。

接手HEAD为`091eb05e421f7362ae80a0b0fa065b40a0710b01`，工作区干净；最终HEAD未变，修改保留在本地，未提交或推送。接手软件身份与旧记录一致，旧记录git_head早于公开提交不使其自动失效。固定成员、完整selection、原始来源及接手生成视图身份保存在[来源诊断](../../runs/lite/requirements/validation/actual-source-diagnosis.json)的`phase4_independent_acceptance`；未替换成员、裁段或改变正式manifest及分母。

| 固定完整样本 | 独立来源case | 固定B：接手 → 当前 | 固定L：接手 → 当前 | 结论 |
| --- | ---: | ---: | ---: | --- |
| huawei-compliance-management-p051-053 | 61 | 52 → 52 | 109 → 109 | 修复后独立source-only验收通过 |
| huawei-management-toc-p014 | 20 | 18 → 18 | 36 → 41 | 修复后独立source-only验收通过 |
| tencent-conditions-entity-payment-definitions-p108-114 | 90 | 90 → 90 | 182 → 179 | 修复后独立source-only验收通过 |
| tencent-redemption-bearer-payments-p135-140 | 55 | 51 → 51 | 123 → 103 | 修复后独立source-only验收通过 |
| tencent-registered-tax-default-trustee-p141-148 | 70 | 62 → 62 | 153 → 129 | 修复后独立source-only验收通过 |

296个授权来源在生产编译前均有逐条手写的实质断言，声明正文、标题、列表父链、导航、允许表示、完整内容范围和限定。华为合规每项措施分别承担责任；未完整解释的正文保留完整有序内容，不捏造SVO或重复业务票。腾讯定义不转成已发生事实，付款、条件、主体、期间、例外、AND/OR和交叉引用均留在各自条款及完整父链内。原文ISDA定义中2021分支仍写2006的文字保持，不作业务修订。目录18项使用字面导航身份，5个ICT子项各有父归属，并有17条不使用页码取值的顺序责任；图注保留且不解释图像。来源断言在`tests/validation/lite_stage4_assertions.py`，统一入口仍为`tests/validation/lite_source_oracle.py`。

实际修复集中在既有读取和比较路径：`expected_readback.elements`保留列表续段的当前项父级；`reference_compiler.plan_reference_sources`与`toc_evidence`绑定完整章节目录的已有声明；`source_obligations._toc_source_bindings`逐槽核验页码在前的标题、页码及父级来源；`requirement_ast.compare_document_ast`只折叠父链已有空白，使合法软换行保留归属；`source_obligations.source_selection`保留章节目录原有声明以支持保存视图独立校验；`document_ast_comparison.navigation_order_requirements`只使用固定retained责任集合，避免局部分析事实造成初次生成与再校验不一致；`document_ast_comparison._without_grammar_analysis`在两端原始来源唯一且完整内容顺序路径存在时，将重复正文顺序转为唯一所有者证明；同一完整陈述内的印刷条款标签、正文归属及非重叠子句顺序亦逐来源转为该内容的证明。独立反例和更严格的来源Oracle曾直接否决腾讯两份的局部谓词及重复L，失败保留在stage4-labelled-source-failures.json；没有把这些局部角色自动枚举为已验收要求。目录顺序由同一文档合同下的导航身份比较承担，页码仍不是数量；候选必须提供自己的目录证据，不能继承expected标签。混合目录/正文的候选保留真实列表来源，不能借邻条款逃过父链验证。

独立失败证据包含接手生成视图对最终来源断言的实际失败：华为合规3处、目录18处、腾讯定义2处、赎回13处及税务受托人6处来源失败。全量重建还曾检出1份集合外目录的责任清单自校验失败，独立合成父子目录复现并修复固定责任集合选择后重新全量验证，未安装失败暂存视图；失败记录保留在stage4-source-export-failure.json。初始声明的缩进段落kind抄录差异单独保留，不作为软件修复收益。83个独立合成最终比较场景覆盖正确表达、合法分块、删除、错父级、漏成员、重复、错值、错编号、错主体、删条件、删例外、邻来源借用、关系反向及未知改写；所有固定B/L分母保持，错值conflict、明确缺失missing、未知改写unresolved均被实测。可发布的受控证据经过validate_evidence，未决证据继续拒绝发布；全部场景的序列化输入及最终outcomes独立重放相等；明确空目录判缺失，读取未完成时不能据此证明缺失。完整材料在[受控比较证据](../../runs/lite/requirements/validation/stage4-controlled-outcomes.json)，均为合成软件验收，未使用真实expected作为candidate。

原56份最终使用相同源码重新执行并全部通过，五处BIS/IEA局部来源亦通过。必要回归发现旧腾讯L1680、L1693父链少了其所在插值条件，按原文四/六空格续段及条件文字加强为`[1674,1676]`和`[1684,1685,1689]`；旧失败保留，未放宽为任一表示。页码在前的同源修复还使原华为前言“目录”下L39–L50的12项取得完整类型化导航责任，逐项补充更严格的标题、字面页码及顺序断言，其他正文断言保留。这里没有重做原56份人工普查，也没有把额外样本加入本轮固定集合。

1639项完整计量的原值、单位、期间、限定、来源及完整payload逐项保持，丢失0；全部2341项原retained数字payload也核对保持。顺丰221项原payload及责任方式保持：161项typed、60项既有完整内容；L742/L781/L920声明保持。华为L1586三项、平安C首句一项类型化命题和4条关系、`[76,538]`互斥余段及混合顺序均保持。五个输入范围逐项核对原始文字、来源和外部声明保持，Alibaba L2353双附着不变。证据在[baseline-preservation.json](../../runs/lite/requirements/validation/baseline-preservation.json)的`phase4`。

60份视图的固定B/L发生变化，净B +0、L -425，B净下降样本0份。每项旧事实、完整payload保留、唯一内容所有者、派生父链变化及分量均在`stage4-preservation.json`；原始字节、目标身份、位置和selection保持，派生父归属的真实修正没有被误报为“全部派生身份不变”。集合外新达到责任完整的样本仅列为待独立验收，不自动授予整样本通过。

最终完整受控回归：4618 passed in 296.91s (0:04:56)。16个CPU分析进程同版重建173份JSON/XML，来源完整性失败0；退出码2反映保留的真实阻塞，未删目标或改变门禁求0。唯一current安装后，原56份加固定5份的61份完整Oracle重新编译并与current逐一相等，全部来源及合同验收通过。45项比较能力绑定本次实际通过JUnit case；源码、测试、手写断言和索引身份均经末尾复核。

software_id=`d80e8f8a84421e8bed360af4bd216d2e6f4bc7114401b8bb1f8ce954c1177206`；tests_sha256=`c5373478526ace58fafc5776144d61990f99c2f9c7db950cabceb76facf3eec0`；手写断言聚合SHA-256=`7500ffd30f2bb21a78eb7e60cf0ab1fb53f73dccc3623fa8b0fffdae4a8f13be`；current索引SHA-256=`6070f34a53c0e121e0329b23606df8d21e23079b37bb8bb098150f7674c05763`。绑定证据在`stage4-final-binding.json`、`oracle-validation.json`、`comparison-validation.json`和`mutations-validation.json`。

当前173份中独立来源及合同验收61份，比较责任仍有缺口112份，责任完整但缺独立整样本验收0份，保留输入范围目标5个。原第三阶段接手的118份缺口已在上一阶段降为112份；本轮5份通过不代表这118份全局完成。全局仍为structure_blocked，正式质量成绩及排名继续暂停。

五份样本的来源审查、独立Oracle、来源重建和83个本轮比较场景未读取真实PDF、图片或PDF字层。未调用OCR、模型或裁判，未执行实际候选比较、八组真实native→final回放、正式保存输出评分、GPU/TTS/在线服务操作、部署、公开API修改、提交或推送。canonical expected、映射、selection、页包、语料、有效native outputs、历史交付正文及原始成本只读。通用检查排除语料、datasets、reference-decisions、runs和reports；下列原始成本正文保持原字节。

执行边界偏差：沿用既有全量受控回归时，运行了创建、读取、渲染合成PDF及图像fixture的测试，路由测试还读取了合成PDF字层；这不符合本轮禁止读取PDF、图片及字层的字面边界。材料均为测试自行生成的临时fixture，没有读取真实来源，也未用于五份样本的验收判断。撤回“本轮完全未读取PDF、图片或字层”的笼统表述；具体执行case与源码位置记录在[执行范围说明](../../runs/lite/requirements/validation/stage4-execution-scope.json)。后续source-only任务须在执行前检查受控命令是否包含此类测试，不能因沿用旧回归清单而忽略当前边界。

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
