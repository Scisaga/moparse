# MO-Parse：S1-S9保存Native连续AST研究

2026-11-17，按用户随后确认的“扩大到全部72组”，已使用同一版本实际比较S1-S9 × P01-P08的72份保存Native。两边独立建树、模糊节点对应、T字符编辑、L关系分项和B关键值保护已进入原有`native-evaluate → grade_layers`调用链。`benchmark=native`，`scope=S1-S9`，`research_only=true`，`full_lite_score=false`，`publication_authorized=false`。完整Lite正式成绩继续撤回，未激活current。

本报告只陈述本方法在已暴露选段上的内容保留与关系比较。低分、缺少对应和原生结构未知须结合逐项证据解释，不能一概称为解析器漏识；方法变化不代表模型或交付文本变好。未决项目保留原分母，其他项目照常计分。

## 研究范围与完整责任

| 选段 | selection | 原页 | T字符 | L要求 | B要求 |
| --- | --- | --- | ---: | ---: | ---: |
| S1 | vanke-interest-p001-002 | 1,2 | 1112 | 44 | 22 |
| S2 | vanke-repurchase-share-changes-p001-003 | 1,2,3 | 2196 | 66 | 40 |
| S3 | zhenye-coupon-seals-p001-003 | 1,2,3 | 734 | 22 | 13 |
| S4 | tencent-conditions-entity-payment-definitions-p108-114 | 108,109,110,111,112,113,114 | 22751 | 179 | 90 |
| S5 | huawei-statements-p068-070 | 68,69,70 | 4572 | 603 | 162 |
| S6 | huawei-management-toc-p014 | 14 | 165 | 41 | 18 |
| S7 | huaweitech-editorial-spread-p002 | 2 | 1134 | 27 | 11 |
| S8 | spdb-cover-declaration-p001-002 | 1,2 | 495 | 17 | 10 |
| S9 | pingan-financials-p001-004 | 1,2,3,4 | 7336 | 536 | 263 |

每条管线共T 40,495字符、L 1,535项、B 629项；原S3/S4/S6子集仍为23,650字符、242项L和121项B，原来被排除的98项source-form B全部纳入。九选段的旧视图尚未承接的来源义务由只读同源文字生成扩展所有者，原要求身份和票数保留；新增所有者及旧义务回指在[责任绑定](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/binding/requirements.json)与[完整共同集合](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/binding/common-set.json)。Expected、Oracle、source-map、selection、manifest及五个未决输入范围未改。

九个选段来自八份文档，S5/S6共享文档但范围独立，共26个原输入页。S4占扩展后T字符责任的56.18%，原24组中则占96.20%；扩大范围后的数字不能直接与旧24组数字相减来说明质量变化。它们已经用于开发和诊断，不是独立留出集，也不代表800页完整Lite。各组使用自己的Native、observation、producer、configuration、页分支及来源许可，见[72组输入绑定](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/binding/inputs.json)。

## 计分方法

拥有定义见[连续AST计分合同](../../evaluation-tasks.md#固定native研究的连续计分2026-11-17授权)。固定相似度下限0.35、最多8个相邻片段，允许1:1、1:N、N:1和有界N:M；定位屏蔽待比较取值，保留原生序列与出现容量。T=`100×max(0,1-(S+D+I)/N_expected)`，未消费的范围内候选文字计I。L在每个原始所有者内部按明确关系分项给分。B精确核对重要字段值及限定，普通陈述按固定字重子句比较内容保留；不能用高文字相似度抵消金额、单位、期间、否定或条件错误。

新增条件标题不能当成展示包装；数字内部空格不能把“2 024年”改成“2024年”。标题合写/拆写及完整双语文字片段只能使用候选自身原文，不能删掉竞争主体或业务父级来制造一致。无法解释完整业务语法的普通正文仍参与比较，不以完整主谓宾分析为前提。

## 三层实际结果

表中普通数字为该完整层的0至100分。“已证x；未决n项”表示其他项目在完整分母上已取得x分贡献，另有n项对应或关系未决；x不是把未决记零的完整分数，也不是已决子集正确率。完整精确分数保留为空，逐项分数和未决都保留。各层独立，具备完整三层分数时总分为三者等权平均；不发布总体排名。

| 配置 | T | L | B | 完整三层平均 |
| --- | ---: | ---: | ---: | ---: |
| P01 Docling V1 + GLM | 76.051 | 已证35.418；未决6项 | 已证16.776；未决20项 | 未决，未生成 |
| P02 Docling V2 + GLM | 73.313 | 已证32.834；未决7项 | 已证15.663；未决10项 | 未决，未生成 |
| P03 PaddleOCR-VL 1.5 | 73.518 | 已证26.355；未决3项 | 已证21.146；未决3项 | 未决，未生成 |
| P04 PaddleOCR-VL 1.6 | 73.387 | 已证25.673；未决3项 | 已证21.205；未决3项 | 未决，未生成 |
| P05 GLM-OCR SDK全页 | 72.816 | 已证25.736；未决3项 | 已证19.926；未决3项 | 未决，未生成 |
| P06 MinerU Standard | 73.298 | 已证26.583；未决3项 | 已证19.734；未决3项 | 未决，未生成 |
| P07 MinerU Advanced | 72.920 | 已证25.681；未决3项 | 已证16.688；未决3项 | 未决，未生成 |
| P08 Visual Blocks | 72.994 | 已证25.508；未决3项 | 已证16.543；未决3项 | 未决，未生成 |

## 全部72组结果

每个选段的分母见前表。完整原文、对应、S/D/I、关系分项与聚合输入均在[研究账本](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/research-results.json)、[汇总与未决清单](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/summary.json)和[72份完整证据索引](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/execution/index.json)；每项可沿`full_evidence`和`outcome_index`回到原分数文件，存储引用用现有`trace_storage.read_score`无损展开。

| 选段 | 配置 | T | L | B |
| --- | --- | ---: | ---: | ---: |
| S1 | P01 | 20.863 | 38.068 | 0.000 |
| S1 | P02 | 20.863 | 38.068 | 0.000 |
| S1 | P03 | 85.342 | 89.773 | 79.388 |
| S1 | P04 | 88.849 | 89.773 | 81.064 |
| S1 | P05 | 88.399 | 89.773 | 76.767 |
| S1 | P06 | 83.813 | 89.773 | 73.429 |
| S1 | P07 | 83.813 | 69.697 | 0.000 |
| S1 | P08 | 84.263 | 56.818 | 0.000 |
| S2 | P01 | 58.333 | 58.965 | 8.784 |
| S2 | P02 | 59.016 | 58.965 | 8.784 |
| S2 | P03 | 61.749 | 54.419 | 47.205 |
| S2 | P04 | 60.929 | 54.293 | 47.205 |
| S2 | P05 | 61.157 | 52.146 | 44.421 |
| S2 | P06 | 61.293 | 46.843 | 22.375 |
| S2 | P07 | 60.474 | 45.328 | 17.375 |
| S2 | P08 | 58.333 | 43.056 | 10.000 |
| S3 | P01 | 74.251 | 89.394 | 77.107 |
| S3 | P02 | 74.251 | 89.394 | 77.107 |
| S3 | P03 | 88.147 | 77.273 | 84.018 |
| S3 | P04 | 88.147 | 77.273 | 84.018 |
| S3 | P05 | 80.109 | 63.636 | 61.266 |
| S3 | P06 | 81.199 | 90.909 | 93.867 |
| S3 | P07 | 81.199 | 90.909 | 93.867 |
| S3 | P08 | 90.872 | 90.909 | 99.403 |
| S4 | P01 | 99.029 | 91.899 | 65.944 |
| S4 | P02 | 99.029 | 91.899 | 65.944 |
| S4 | P03 | 99.881 | 91.899 | 67.694 |
| S4 | P04 | 99.873 | 91.899 | 67.690 |
| S4 | P05 | 97.415 | 89.106 | 64.327 |
| S4 | P06 | 99.908 | 91.899 | 67.778 |
| S4 | P07 | 99.908 | 91.899 | 67.778 |
| S4 | P08 | 99.833 | 91.899 | 67.493 |
| S5 | P01 | 55.927 | 17.302 | 8.513 |
| S5 | P02 | 43.176 | 15.755 | 4.192 |
| S5 | P03 | 21.041 | 3.980 | 3.601 |
| S5 | P04 | 21.019 | 3.980 | 3.601 |
| S5 | P05 | 21.391 | 3.980 | 3.601 |
| S5 | P06 | 20.976 | 4.146 | 4.218 |
| S5 | P07 | 20.888 | 3.897 | 2.984 |
| S5 | P08 | 20.888 | 3.897 | 2.984 |
| S6 | P01 | 98.182 | 85.366 | 72.222 |
| S6 | P02 | 98.182 | 85.366 | 72.222 |
| S6 | P03 | 91.515 | 85.366 | 72.222 |
| S6 | P04 | 91.515 | 85.366 | 72.222 |
| S6 | P05 | 98.182 | 85.366 | 72.222 |
| S6 | P06 | 98.182 | 85.366 | 72.222 |
| S6 | P07 | 98.182 | 85.366 | 72.222 |
| S6 | P08 | 91.515 | 85.366 | 72.222 |
| S7 | P01 | 85.009 | 51.852 | 0.000 |
| S7 | P02 | 85.009 | 51.852 | 0.000 |
| S7 | P03 | 85.009 | 51.852 | 0.000 |
| S7 | P04 | 85.273 | 51.852 | 0.000 |
| S7 | P05 | 85.009 | 51.852 | 0.000 |
| S7 | P06 | 85.009 | 51.852 | 0.000 |
| S7 | P07 | 85.009 | 51.852 | 0.000 |
| S7 | P08 | 86.684 | 61.111 | 9.091 |
| S8 | P01 | 73.737 | 63.725 | 48.880 |
| S8 | P02 | 73.737 | 63.725 | 48.880 |
| S8 | P03 | 77.778 | 63.725 | 49.833 |
| S8 | P04 | 77.778 | 63.725 | 49.833 |
| S8 | P05 | 75.354 | 63.725 | 49.833 |
| S8 | P06 | 75.152 | 63.725 | 49.833 |
| S8 | P07 | 75.152 | 63.725 | 49.833 |
| S8 | P08 | 72.929 | 66.667 | 55.548 |
| S9 | P01 | 29.457 | 已证26.057；未决6项 | 已证0.363；未决20项 |
| S9 | P02 | 22.083 | 已证20.398；未决7项 | 已证0.363；未决10项 |
| S9 | P03 | 22.260 | 已证11.901；未决3项 | 已证0.380；未决3项 |
| S9 | P04 | 21.251 | 已证9.966；未决3项 | 已证0.380；未决3项 |
| S9 | P05 | 26.350 | 已证11.901；未决3项 | 已证0.380；未决3项 |
| S9 | P06 | 22.097 | 已证12.741；未决3项 | 已证0.380；未决3项 |
| S9 | P07 | 20.311 | 已证12.275；未决3项 | 已证0.760；未决3项 |
| S9 | P08 | 20.597 | 已证12.554；未决3项 | 已证0.760；未决3项 |

## 真实原文、对应和扣分证据

以下摘录全部来自实际保存分数；完整节点、原文切口、来源及关系见[真实例证](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/actual-examples.json)。不把格式合同差异或比较器限制直接归因于解析模型。

### S1 / P03

要求`B:content:1`，层B，credit=1.0。

Expected：`"根据万科转债募集说明书的规定，其票面利率为每年1.5%。"`；Candidate：`"根据万科转债募集说明书的规定,其票面利率为每年1.5%。"`。

对应后内容保留=1.0，保护值检查=True，范围检查=True，该分项credit=1.0；编辑=`{"S": 0, "D": 0, "I": 0}`。

Expected：`"2002年度万科转债派息方案为：每10张万科转债（面值1000元）派息15元。"`；Candidate：`"2002年度万科转债派息方案为:每10张万科转债(面值1000元)派息15元。"`。

对应后内容保留=1.0，保护值检查=True，范围检查=True，该分项credit=1.0；编辑=`{"S": 0, "D": 0, "I": 0}`。

### S4 / P03

要求`B:content:0`，层B，credit=0.9777777777777777。

Expected：`"“First Interest Payment Date” means the date specified in the relevant Pricing Supplement;"`；Candidate：`"\"First Interest Payment Date\" means the date specified in the relevant Pricing Supplement;"`。

对应后内容保留=0.977778，保护值检查=True，范围检查=True，该分项credit=0.977778；编辑=`{"S": 2, "D": 0, "I": 0}`。

要求`B:content:1`，层B，credit=0.9746835443037974。

Expected：`"“Fixed Coupon Amount” has the meaning given in the relevant Pricing Supplement;"`；Candidate：`"\"Fixed Coupon Amount\" has the meaning given in the relevant Pricing Supplement;"`。

对应后内容保留=0.974684，保护值检查=True，范围检查=True，该分项credit=0.974684；编辑=`{"S": 2, "D": 0, "I": 0}`。

### S6 / P01

要求`projected-text:2:sentence:0`，层T，credit=1.0。

Expected：`"愿景、使命与战略"`；Candidate：`"愿景、使命与战略"`；编辑=`{"S": 0, "D": 0, "I": 0}`。

要求`projected-text:10:sentence:0`，层T，credit=0.8571428571428572。

Expected：`"政府和企业市场"`；Candidate：`"、政府和企业市场"`；编辑=`{"S": 0, "D": 0, "I": 1}`。

要求`B:0`，层B，credit=1.0。

字段=`"愿景、使命与战略 / Page"`；Expected值=`"13"`；Candidate值=`"13"`。

值、身份、范围与限定的原始判据：`[{"relation": "value", "expected": "13", "actual": "13", "credit": 1, "equivalence": {"required": "13", "actual": "13", "correct": true, "status": "correct", "role_basis": "printed_navigation_reference", "quantity_equivalence_applicable": false}, "identity_correct": true, "scope_correct": true, "qualifiers": [], "restrictive_context": {"correct": true, "unsupported_restrictive_labels": [], "rule": "printed_restrictive_context_must_be_supported_by_same_required_owner"}}]`。

要求`B:4`，层B，credit=0.0。

字段=`"政府和企业市场 / Page"`；Expected值=`"21"`；Candidate值=`"21"`。

值、身份、范围与限定的原始判据：`[{"relation": "value", "expected": "21", "actual": "21", "credit": 0, "equivalence": {"required": "21", "actual": "21", "correct": true, "status": "correct", "role_basis": "printed_navigation_reference", "quantity_equivalence_applicable": false}, "identity_correct": false, "scope_correct": false, "qualifiers": [], "restrictive_context": {"correct": true, "unsupported_restrictive_labels": [], "rule": "printed_restrictive_context_must_be_supported_by_same_required_owner"}}]`。

### S9 / P02

要求`B:9`，层B，credit=0.0。

字段=`" / 电子信箱"`；Expected值=`"pabdsh@pingan.com.cn。"`；Candidate值=`null`。

值、身份、范围与限定的原始判据：`[{"relation": "value", "credit": 0, "reason": "no_corresponding_field"}]`。

要求`B:13`，层B，credit=0.0。

字段=`" / 电子信箱"`；Expected值=`"pabdsh@pingan.com.cn。"`；Candidate值=`null`。

值、身份、范围与限定的原始判据：`[{"relation": "value", "credit": 0, "reason": "no_corresponding_field"}]`。

## 验证、发现的误判及剩余限制

最终同版source-only实际执行8个受影响模块，共448项通过；证据为[测试回执](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/evidence/regression-final-complete.json)。包含各保存原生格式入口到最终分数的独立手写正反例：满分、手算S/D/I、拆合、漏项、重复、顺序、错挂父级、同名不得借值、金额/页码/单位/期间/否定/条件冲突、候选读取失败及完整72组汇总。Ruff、适用的两份拥有文档Markdown政策和限定文件差异检查通过；测试数本身不是实际样本验收。

本轮发现并修复了旧readiness覆盖新分数、语义类别未完成误判为文字读取失败、目录合块无法对应、字段轴在不同原生语法位置时无法定位、标题拆分/双语品牌造成业务正文误归零、L字段存在被误当作轴绑定正确、新增条件标题漏判、电话错误使用数量等价、邮箱字段读取、原生表格源格顺序和局部表前标签归属、数字内部空格错误等价，以及汇总读取旧publishable字段的异常。中间24组和72组尝试、失败、受控反例及中断记录均保留，但没有混入本次分数。

本方法仍是有界内容保留比较，不是任意自然语言改写的完整语义等价。跨表格与展开句时，T继续记录实际字面差异；L/B只使用候选自己明确表达的字段轴、上下文和源格，不从Expected补写候选。原生未表达或无法确认的完整层级、单位/归属与竞争对应必须看逐项证据；未经独立证明不把所有零分称为实际解析缺陷。

本次仍有79条未决责任记录（跨72组，不是独立缺陷数）：`{"('S9', 'L', 'document_scope')": 21, "('S9', 'B', 'source_form_assertion')": 21, "('S9', 'B', 'metric')": 27, "('S9', 'L', 'field_binding')": 10}`。确切要求ID、原文和完整证据见summary.json的`unresolved`，它们未被删除或改判零分。

## 尚未闭合的具体要求

本轮72组全部完成实际执行，其中S1-S8的64组拥有完整三层数值，原S3/S4/S6的24组也全部包含在内。S9的8组仍有79条未决责任：31项L、48项B；所有层的原分母保留。主要包括流动性覆盖率、杠杆率和流动性比例的标准值/年度/年末/月均归属，以及加权平均净资产收益率等重复指标的上下文对应，不能把当前计算完成称为这些业务要求已经验收完成。

例如S9/P01的`L:content:18`、`B:content:18`仍无法唯一对应“流动性覆盖率：标准值≥60；2014年12月31日年末80.25、月均不适用；……”的完整陈述；`B:84`及`L:179`仍有字段归属竞争。确切的全部79项及原文见[未决清单](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/summary.json)，记录数包含同一来源在不同管线或层的责任，不能当作独立产品缺陷数。

S9/P02还有不等同于未决记录的字段读取限制：原生表格确实保留`pabdsh@`、`abdsh@pingan.com.cn`等源格，但这些格子没有已证的完整邮箱字段绑定；本次`B:9`、`B:13`因此为0、原因为`no_corresponding_field`。不能把这两项解释成Native完全没有邮箱文字，不能用邻格或Expected拼出答案，也不能声称所有真实邮箱字段的读取问题已经解决。完整原生声明、原格和现有判定见[补充读取诊断](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/evidence/remaining-readback.json)。

S6/P01的“政府和企业市场”页码Expected与Native均为21；本次该项B为0，来自标题身份及归属证据未通过，不是页码数值错误。其文字对应保留候选多出的“、”并记录一次I。相对地，“愿景、使命与战略”页码13已正确建立对应并获得该项B满分。上述限制及失败来源须与实际解析错值分开。

## 执行身份与边界

有效软件ID：`a6cabfbf336372fa40ce9eca26da167d9817617b8c4cb4e699b2bc363069a990`。[冻结](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/binding/freeze.json)、[用户原文与72组授权绑定](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/binding/authorization.json)、[闭环绑定](../../runs/lite/native-only/s1-s9-continuous-20261117-r7/final-binding.json)保留软件、规则、原输入和验证身份。两次独立Native读取均为72/72，载荷逐份相同，候选阶段Expected/Final访问为false；执行前后重新核对只读输入。

CPU串行执行，限制在同一8 CPU亲和集合、8 GiB地址空间、独立挂载和网络命名空间，禁用GPU可见设备。没有读取PDF或图片字节、OCR/VLM、模型推理、Final、IR或Semantic候选，没有服务操作、部署、网络、提交或推送。图片只保留原有声明/引用，不赋予图像语义。

本轮72个case的评测阶段合计827.86秒，比较进程记录峰值RSS为0.483 GiB。整段执行及Native读取时间另见审计；这些是CPU评测的阶段墙钟，含证据存储，不是原解析耗时。原始解析成本未重新测量，也未重复核查全部2104份成本记录。

下面保留2026-11-16旧方法研究的原有记录，其23项共同B、区间和软件身份均为历史状态，不能替代本次629项B完整责任或作为本方法基线。

<details>
<summary>2026-11-16及此前研究记录（原文保留，历史身份）</summary>

# MO-Parse：固定S3/S4/S6有限Native研究结果

2026-11-16，本报告只记录已获明确授权的内部有限Native研究。`benchmark=native`，`scope=S3/S4/S6`，`research_only=true`，`full_lite_score=false`，`publication_authorized=false`。24个组合全部经原有Native-only入口实际比较，原始4128项要求及trace完整保留。正式Lite成绩继续撤回，未生成T/L/B总分或完整Lite排名，未激活scores/current。

## 1. 研究范围

| 选段 | 固定selection | 原输入页 | 研究问题 |
| --- | --- | --- | --- |
| S3 | zhenye-coupon-seals-p001-003 | 1-3 | 图文混排、票面利率、印章与视觉区域的文本/来源限制 |
| S4 | tencent-conditions-entity-payment-definitions-p108-114 | 108-114 | 法律定义、列表、父子关系、条件、否定、例外、定义引用 |
| S6 | huawei-management-toc-p014 | 14 | 目录、导航、标题、页码、多栏及层级 |

| 配置 | 名称 | S3 | S4 | S6 |
| --- | --- | --- | --- | --- |
| P01 | Docling V1 + GLM | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P01/zhenye-coupon-seals-p001-003.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P01/tencent-conditions-entity-payment-definitions-p108-114.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P01/huawei-management-toc-p014.json) |
| P02 | Docling V2 + GLM | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P02/zhenye-coupon-seals-p001-003.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P02/tencent-conditions-entity-payment-definitions-p108-114.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P02/huawei-management-toc-p014.json) |
| P03 | PaddleOCR-VL 1.5 | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P03/zhenye-coupon-seals-p001-003.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P03/tencent-conditions-entity-payment-definitions-p108-114.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P03/huawei-management-toc-p014.json) |
| P04 | PaddleOCR-VL 1.6 | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P04/zhenye-coupon-seals-p001-003.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P04/tencent-conditions-entity-payment-definitions-p108-114.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P04/huawei-management-toc-p014.json) |
| P05 | GLM-OCR SDK全页 | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P05/zhenye-coupon-seals-p001-003.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P05/tencent-conditions-entity-payment-definitions-p108-114.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P05/huawei-management-toc-p014.json) |
| P06 | MinerU Standard | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P06/zhenye-coupon-seals-p001-003.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P06/tencent-conditions-entity-payment-definitions-p108-114.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P06/huawei-management-toc-p014.json) |
| P07 | MinerU Advanced | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P07/zhenye-coupon-seals-p001-003.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P07/tencent-conditions-entity-payment-definitions-p108-114.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P07/huawei-management-toc-p014.json) |
| P08 | Visual Blocks | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P08/zhenye-coupon-seals-p001-003.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P08/tencent-conditions-entity-payment-definitions-p108-114.json) | [已执行](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/requirements/P08/huawei-management-toc-p014.json) |

| 配置 | S3实际页分支 | S4实际页分支 | S6实际页分支 |
| --- | --- | --- | --- |
| P01 | docling:1页, glm:2页 | docling:7页 | glm:1页 |
| P02 | docling:1页, glm:2页 | docling:7页 | glm:1页 |
| P03 | paddle:3页 | paddle:7页 | paddle:1页 |
| P04 | paddle:3页 | paddle:7页 | paddle:1页 |
| P05 | glm:3页 | glm:7页 | glm:1页 |
| P06 | mineru:1页, glm:2页 | mineru:7页 | glm:1页 |
| P07 | mineru:1页, glm:2页 | mineru:7页 | glm:1页 |
| P08 | visual:3页 | visual:7页 | visual:1页 |

以上是各自原Native的实际页分支，不是新增路由。S6中P01/P02/P05/P06/P07均为GLM分支；S3的P01/P02与P06/P07分别只有一页主后端、两页GLM。结论归于固定配置及实际分支，不能把S6差异归因于未在该页执行的Docling或MinerU后端。

这三个选段已经用于开发和诊断，不是独立留出集，也不能代表完整文档类型。候选只来自各自冻结Native及observation，保留producer、configuration、页映射、来源许可和原SHA；没有读取Final、IR或Semantic工件作为候选。研究只读取授权文本和保存结构，没有读取PDF/图片字节、调用模型、OCR/VLM、网络、GPU/TTS、在线服务或生产转换。

当前HEAD为`242aa672f70686b6c962f5ed9d9454d540e0c8cb`，Native比较软件ID为`3f0f0efea2a57dfda02191fbf7394f967fdf8bb610000bc59171de7d55e7c509`。历史冻结SHA256为`cb8dbc49df2a76c7e472241bca46a5c7fe24768040943a8fc48bb288e00bf0e9`。当前源码、支持源码、Python和依赖与该历史冻结相同，只有完整身份字典中的Git HEAD以及新研究聚合器/测试环境绑定变化；保留历史冻结，执行绑定SHA256为`1e9bd1d166201b4bca3659698075307638d58cf24e299efb57a4892136a9ed1f`。没有重建或重签历史Oracle、Native输入、readiness及原始成本。

[授权记录](../../runs/lite/native-only/s3-s4-s6-20261116/binding/authorization.json)绑定用户本轮附件原文、实际执行freeze及共同集合；[执行索引](../../runs/lite/native-only/s3-s4-s6-20261116/execution-complete/index.json)绑定全部24个实际结果。

首次全量profiling观测尝试在保存10组结果后由本任务主动中断；这些原始文件、KeyboardInterrupt状态及耗时全部保留在execution目录，不计作候选失败或额外研究样本。随后同一软件、输入、授权及共同集合下的execution-complete完整24组执行，才是本报告唯一统计来源。边界计时只观察六个原入口code object，没有替换比较函数。中断原因与身份见[中断尝试说明](../../runs/lite/native-only/s3-s4-s6-20261116/evidence/profiled-attempt-disposition.json)；两次尝试中已保存的10份完整比较载荷逐份相等，见[计时切换一致性证据](../../runs/lite/native-only/s3-s4-s6-20261116/evidence/observer-output-consistency.json)。

## 2. 共同可比较集合

集合由已有Expected责任、独立来源验收、固定来源范围和比较器静态能力决定。先核对这些条件并写入只读共同集合，再执行原入口、读取比较结果。没有使用八组的成功交集、正确率、候选缺失或各管线可比较ID交集选样；每条管线使用同一集合。完整责任分母及正式Lite合同保持原状。

| 选段 | T原始/共同字符 | L原始/共同要求 | B原始/共同要求 |
| --- | --- | --- | --- |
| S3 | 734 / 734 | 22 / 22 | 13 / 5 |
| S4 | 22751 / 22751 | 179 / 179 | 90 / 0 |
| S6 | 165 / 165 | 41 / 41 | 18 / 18 |
| 合计 | 23650 / 23650 | 242 / 242 | 121 / 23 |

T共同字符的96.20%来自S4，分选段结果同时列出。T保留现有canonical字符、原Expected跨度及固定半开字符区间，仍使用既有S/D/I编辑账本；没有新增字符映射框架、改变空白/数字/日期/标识符等价规则，或拆分出额外计票单位。原生读取视图继续共享原始出现容量，不跨正文、标题、列表、表格或媒体屏障拼接。共同集合完整纳入242项L责任：候选是否提供父链、表头、单位或阅读顺序，不参与集合选择。

B统一排除完整source_form_assertion这一类98项责任，具体为S3的8项和S4的90项。现有比较器可以证明完整原文保留，但对合法改写会返回wording_change_requires_semantic_comparison，尚不能可靠判断这一类完整业务等价；因此在查看结果前，对所有管线一致排除，包括之后可能完全逐字保留的候选。其T字符和L责任照常保留，原始B比较照常执行。B共同23项为S3的5项已保留类型化字段与S6的18项导航值责任；S4没有共同B责任，不能据该B集合评价法律定义的完整业务语义，也不能证明S3票面利率整段业务责任全部通过。

Expected责任不完整或参考来源歧义在这三个独立验收选段中没有新增实例。候选侧关系未知、对应歧义、比较器不支持表达以及明确错误保持分开；原生缺少父链声明，不自动等于已证明缺失父链。只有明确穷尽缺失证明才标candidate_missing；没有命中不等于缺失。

共同集合SHA256：`ce776fb8c9a2cad3b7dd5500950bde4c0ae174fd8d34be264a7a933cf5102f7f`。[逐项纳入/排除、canonical区间和理由](../../runs/lite/native-only/s3-s4-s6-20261116/binding/common-set.json)、[六类限制与readiness原因分类](../../runs/lite/native-only/s3-s4-s6-20261116/evidence/intake-and-membership.json)、[结果读取前的冻结审计](../../runs/lite/native-only/s3-s4-s6-20261116/evidence/common-freeze-audit.json)保留完整身份。冻结后没有重新选集合。

## 3. 各管线覆盖能力

“共同集合”是候选无关的责任集合；“已决覆盖”是实际取得可靠正确或错误证据的比例，两者不同。下表另列每条管线在完整原责任上的独立已决范围，T为字符预算，L/B为要求条数。这些不同覆盖分母上的辅助正确率不用于排序。

| 配置 | 独立T已决/完整 | 独立L已决/完整 | 独立B已决/完整 | 共同T覆盖 | 共同L覆盖 | 共同B覆盖 |
| --- | --- | --- | --- | --- | --- | --- |
| P01 | 8458 / 23650 | 3 / 242 | 3 / 121 | 35.76% | 1.24% | 13.04% |
| P02 | 8458 / 23650 | 3 / 242 | 3 / 121 | 35.76% | 1.24% | 13.04% |
| P03 | 22260 / 23650 | 3 / 242 | 61 / 121 | 94.12% | 1.24% | 13.04% |
| P04 | 21563 / 23650 | 3 / 242 | 60 / 121 | 91.18% | 1.24% | 13.04% |
| P05 | 8127 / 23650 | 0 / 242 | 0 / 121 | 34.36% | 0.00% | 0.00% |
| P06 | 22072 / 23650 | 5 / 242 | 64 / 121 | 93.33% | 2.07% | 13.04% |
| P07 | 22072 / 23650 | 66 / 242 | 64 / 121 | 93.33% | 27.27% | 13.04% |
| P08 | 20911 / 23650 | 5 / 242 | 57 / 121 | 88.42% | 2.07% | 13.04% |

24/24份新Native读取均通过独立隔离，Expected/Final访问为false；新读取的完整载荷与冻结准备时载荷逐份相等。[原生语法、标题层级、目录父链、源格和媒体声明证据](../../runs/lite/native-only/s3-s4-s6-20261116/native-capability-evidence.json)记录各配置的自身读取能力。表格标签、源格数量和列表语法只描述原生表达，不据此认定语义数据表正确；数组、bbox或Markdown缩进本身不建立全局顺序或法律父链。

## 4. Native质量比较

以下均为内部有限研究诊断比例，单位固定且不跨T/L/B合并。T的correct/incorrect是既有字符预算扣除可信S+D+I后的余额/扣减量，不是逐要求通过数；未可靠对应的整个原T原子保留其固定字符权重为unresolved。L/B沿用原要求的一票身份。coverage=(correct+incorrect)/N_common；lower=correct/N_common，upper=(correct+unresolved)/N_common。software_blocked独立列示，不计为错误；一旦共同集合发生该阻塞，相应区间留空。resolved_accuracy仅为已决子集的辅助量，不支持不同分母排名。全部候选未消费文字仍在原trace中；这些区间不是完整输出的CER、额外内容正确率或正式T/L/B成绩。

### T

| 配置 | N_common | correct | incorrect | unresolved | software_blocked | candidate_missing | coverage | lower - upper | 辅助已决准确率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | 23650 | 8444 | 14 | 15192 | 0 | 0 | 35.76% | 35.70% - 99.94% | 99.83% |
| P02 | 23650 | 8444 | 14 | 15192 | 0 | 0 | 35.76% | 35.70% - 99.94% | 99.83% |
| P03 | 23650 | 22251 | 9 | 1390 | 0 | 0 | 94.12% | 94.08% - 99.96% | 99.96% |
| P04 | 23650 | 21554 | 9 | 2087 | 0 | 0 | 91.18% | 91.14% - 99.96% | 99.96% |
| P05 | 23650 | 8120 | 7 | 15523 | 0 | 0 | 34.36% | 34.33% - 99.97% | 99.91% |
| P06 | 23650 | 22041 | 31 | 1578 | 0 | 0 | 93.33% | 93.20% - 99.87% | 99.86% |
| P07 | 23650 | 22041 | 31 | 1578 | 0 | 0 | 93.33% | 93.20% - 99.87% | 99.86% |
| P08 | 23650 | 20903 | 8 | 2739 | 0 | 0 | 88.42% | 88.38% - 99.97% | 99.96% |

### L

| 配置 | N_common | correct | incorrect | unresolved | software_blocked | candidate_missing | coverage | lower - upper | 辅助已决准确率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | 242 | 3 | 0 | 239 | 0 | 0 | 1.24% | 1.24% - 100.00% | 100.00% |
| P02 | 242 | 3 | 0 | 239 | 0 | 0 | 1.24% | 1.24% - 100.00% | 100.00% |
| P03 | 242 | 3 | 0 | 239 | 0 | 0 | 1.24% | 1.24% - 100.00% | 100.00% |
| P04 | 242 | 3 | 0 | 239 | 0 | 0 | 1.24% | 1.24% - 100.00% | 100.00% |
| P05 | 242 | 0 | 0 | 242 | 0 | 0 | 0.00% | 0.00% - 100.00% | 未建立 |
| P06 | 242 | 5 | 0 | 237 | 0 | 0 | 2.07% | 2.07% - 100.00% | 100.00% |
| P07 | 242 | 66 | 0 | 176 | 0 | 0 | 27.27% | 27.27% - 100.00% | 100.00% |
| P08 | 242 | 5 | 0 | 237 | 0 | 0 | 2.07% | 2.07% - 100.00% | 100.00% |

### B

| 配置 | N_common | correct | incorrect | unresolved | software_blocked | candidate_missing | coverage | lower - upper | 辅助已决准确率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | 23 | 3 | 0 | 20 | 0 | 0 | 13.04% | 13.04% - 100.00% | 100.00% |
| P02 | 23 | 3 | 0 | 20 | 0 | 0 | 13.04% | 13.04% - 100.00% | 100.00% |
| P03 | 23 | 3 | 0 | 20 | 0 | 0 | 13.04% | 13.04% - 100.00% | 100.00% |
| P04 | 23 | 3 | 0 | 20 | 0 | 0 | 13.04% | 13.04% - 100.00% | 100.00% |
| P05 | 23 | 0 | 0 | 23 | 0 | 0 | 0.00% | 0.00% - 100.00% | 未建立 |
| P06 | 23 | 3 | 0 | 20 | 0 | 0 | 13.04% | 13.04% - 100.00% | 100.00% |
| P07 | 23 | 3 | 0 | 20 | 0 | 0 | 13.04% | 13.04% - 100.00% | 100.00% |
| P08 | 23 | 3 | 0 | 20 | 0 | 0 | 13.04% | 13.04% - 100.00% | 100.00% |

[全部统计与4128项逐要求状态](../../runs/lite/native-only/s3-s4-s6-20261116/research-results.json)及[实际trace、字符账本和出现容量复核](../../runs/lite/native-only/s3-s4-s6-20261116/evidence/trace-and-aggregation-validation.json)保留原始完整分母、原始比较状态、冻结限制及各选段拆分；原始结果没有被研究聚合器改写。candidate_missing为零时仅表示没有取得独立缺失证明，不能解释成没有漏字或漏关系。

完整原始责任中的状态另列如下，B含共同集合排除的98项。软件不支持表达不混作候选错误；Expected blocked在本固定范围为0，完整Lite全局门禁保持。

| 配置 | 层 | 完整N | correct | incorrect | unresolved | 软件阻塞 | 共同集合排除 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P01 | T | 23650 | 8444 | 14 | 15192 | 0 | 0 |
| P01 | L | 242 | 3 | 0 | 239 | 0 | 0 |
| P01 | B | 121 | 3 | 0 | 99 | 19 | 98 |
| P02 | T | 23650 | 8444 | 14 | 15192 | 0 | 0 |
| P02 | L | 242 | 3 | 0 | 239 | 0 | 0 |
| P02 | B | 121 | 3 | 0 | 99 | 19 | 98 |
| P03 | T | 23650 | 22251 | 9 | 1390 | 0 | 0 |
| P03 | L | 242 | 3 | 0 | 239 | 0 | 0 |
| P03 | B | 121 | 61 | 0 | 57 | 3 | 98 |
| P04 | T | 23650 | 21554 | 9 | 2087 | 0 | 0 |
| P04 | L | 242 | 3 | 0 | 239 | 0 | 0 |
| P04 | B | 121 | 60 | 0 | 58 | 3 | 98 |
| P05 | T | 23650 | 8120 | 7 | 15523 | 0 | 0 |
| P05 | L | 242 | 0 | 0 | 242 | 0 | 0 |
| P05 | B | 121 | 0 | 0 | 121 | 0 | 98 |
| P06 | T | 23650 | 22041 | 31 | 1578 | 0 | 0 |
| P06 | L | 242 | 5 | 0 | 237 | 0 | 0 |
| P06 | B | 121 | 64 | 0 | 57 | 0 | 98 |
| P07 | T | 23650 | 22041 | 31 | 1578 | 0 | 0 |
| P07 | L | 242 | 66 | 0 | 176 | 0 | 0 |
| P07 | B | 121 | 64 | 0 | 57 | 0 | 98 |
| P08 | T | 23650 | 20903 | 8 | 2739 | 0 | 0 |
| P08 | L | 242 | 5 | 0 | 237 | 0 | 0 |
| P08 | B | 121 | 57 | 0 | 61 | 3 | 98 |

## 5. 文档结构分析

### S3

| 配置 | T正确/错误/未决 | L正确/错误/未决 | B正确/错误/未决 |
| --- | --- | --- | --- |
| P01 | 283/14/437（N=734） | 3/0/19（N=22） | 3/0/2（N=5） |
| P02 | 283/14/437（N=734） | 3/0/19（N=22） | 3/0/2（N=5） |
| P03 | 630/9/95（N=734） | 3/0/19（N=22） | 3/0/2（N=5） |
| P04 | 630/9/95（N=734） | 3/0/19（N=22） | 3/0/2（N=5） |
| P05 | 602/7/125（N=734） | 0/0/22（N=22） | 0/0/5（N=5） |
| P06 | 420/31/283（N=734） | 3/0/19（N=22） | 3/0/2（N=5） |
| P07 | 420/31/283（N=734） | 3/0/19（N=22） | 3/0/2（N=5） |
| P08 | 591/8/135（N=734） | 3/0/19（N=22） | 3/0/2（N=5） |

本选段31条要求×配置的已定位T错误记录全部是空白差异，可信S/D/I账本合计S=0、D=0、I=123；重复记录不构成31个独立根因。P01/P02各14个字符预算扣减，P03/P04各9，P05为7，P06/P07各31，P08为8。原生图文、印章及视觉区域只使用保存的文本、声明和来源证据，未进行视觉判断。已定位利率句的日期和5.20%附近空格仍按原T合同保留扣分；未取得已定位错数或漏字的独立证据，不等于所有未决内容正确。数字字面保留不自动证明整句业务条件、发行范围或视觉区域的关系正确。签章、媒体内容及实际交付不由本轮Native文字研究认证。

### S4

| 配置 | T正确/错误/未决 | L正确/错误/未决 | B正确/错误/未决 |
| --- | --- | --- | --- |
| P01 | 8153/0/14598（N=22751） | 0/0/179（N=179） | 0/0/0（N=0） |
| P02 | 8153/0/14598（N=22751） | 0/0/179（N=179） | 0/0/0（N=0） |
| P03 | 21613/0/1138（N=22751） | 0/0/179（N=179） | 0/0/0（N=0） |
| P04 | 20916/0/1835（N=22751） | 0/0/179（N=179） | 0/0/0（N=0） |
| P05 | 7510/0/15241（N=22751） | 0/0/179（N=179） | 0/0/0（N=0） |
| P06 | 21613/0/1138（N=22751） | 2/0/177（N=179） | 0/0/0（N=0） |
| P07 | 21613/0/1138（N=22751） | 63/0/116（N=179） | 0/0/0（N=0） |
| P08 | 20304/0/2447（N=22751） | 2/0/177（N=179） | 0/0/0（N=0） |

法律定义的字面对应、列表角色、父链和顺序分别比较。共同T的已决字符预算分别为：P01/P02各8153、P03/P06/P07各21613、P04为20916、P05为7510、P08为20304，N均为22751，可信已决部分没有新增S/D/I扣减。差异首先是可靠对应覆盖，不能把未决字符直接归因为识别错误。L方面，P07确认61项文档归属及2项局部顺序，仍有116项未决；P06/P08各确认同一Native字符串内的2项局部顺序，仍有177项未决；P01-P05各179项未决。已确认顺序的端点为Expected L1509-L1510、L1510-L1511，不代表全七页全局顺序。完整定义文字出现不自动证明条件、否定、例外、定义引用或父子关系正确。90项原始B责任继续在完整trace和独立覆盖视角中保留；共同B未覆盖本选段。不能将这一能力缺口称为法律内容不适用，也不能把原生父链未知计成已证漏结构。

### S6

| 配置 | T正确/错误/未决 | L正确/错误/未决 | B正确/错误/未决 |
| --- | --- | --- | --- |
| P01 | 8/0/157（N=165） | 0/0/41（N=41） | 0/0/18（N=18） |
| P02 | 8/0/157（N=165） | 0/0/41（N=41） | 0/0/18（N=18） |
| P03 | 8/0/157（N=165） | 0/0/41（N=41） | 0/0/18（N=18） |
| P04 | 8/0/157（N=165） | 0/0/41（N=41） | 0/0/18（N=18） |
| P05 | 8/0/157（N=165） | 0/0/41（N=41） | 0/0/18（N=18） |
| P06 | 8/0/157（N=165） | 0/0/41（N=41） | 0/0/18（N=18） |
| P07 | 8/0/157（N=165） | 0/0/41（N=41） | 0/0/18（N=18） |
| P08 | 8/0/157（N=165） | 0/0/41（N=41） | 0/0/18（N=18） |

八组的结果完全相同：T仅标题“管理层讨论与分析”8字得到可靠对应，另157字未决，覆盖4.85%；L的41项及B的18项全部未决。当前Native读取未形成可用toc_evidence条目，不能据此断言原生内容确实不存在。该选段的有效判断范围不足以比较八组目录/导航质量。目录的标题文字、页码字面、导航身份、父路径和顺序分别保留。页面内标题或页码字符串出现，只能证明相应T文字，不证明toc_page绑定、目录父子层级或多栏阅读顺序。未查看原页或使用bbox排序补足这些关系，照片文字标签也不构成图片内容判断。

## 6. 失败模式

| 层 | 研究状态 | 证据归因 | 原要求记录数 |
| --- | --- | --- | --- |
| B | correct | independent_comparison | 312 |
| B | software_blocked | unsupported_business_expression | 47 |
| B | unresolved | correspondence_not_proved | 464 |
| B | unresolved | native_relation_unknown | 145 |
| L | correct | independent_comparison | 88 |
| L | unresolved | correspondence_not_proved | 606 |
| L | unresolved | native_relation_unknown | 1242 |
| T | correct | independent_comparison | 614 |
| T | incorrect | independent_comparison | 31 |
| T | unresolved | correspondence_not_proved | 579 |

已确认的31条错误记录全部属于S3空白差异；其余范围不因未决被改判为正确。原始完整B责任中，P01/P02各19项、P03/P04/P08各3项存在明确的合法改写语义比较软件阻塞，均未计为候选错误；这些发生在共同集合统一排除的source_form_assertion类。共同集合运行时软件阻塞为0，不能据此声称整套比较器没有能力限制。各Native在本固定范围暴露的源格数均为0，缺乏独立确认的数据表比较范围，不能由本研究推断表格解析质量。上表是原要求记录数，用于定位原因，T分母仍为字符。确认错误、未决及软件限制的逐条原文/来源/trace指针见[完整失败证据](../../runs/lite/native-only/s3-s4-s6-20261116/failure-evidence.json)。原始software_failure标记还用于比较器四态未知；必须结合实际reason，不能统一声称执行异常或原生缺失。独立定位失败、原生关系未知、合法改写超出比较器能力均保持各自状态。

文字、数字、结构、表格、列表、顺序、来源和视觉的结论边界分别为：已定位文字编辑按原合同记账；数字/日期/代码不能用空白归一消除差异；结构须有独立原生证据；源格或table标签不能证明语义表格；列表角色与父链分开；顺序不能由数组/bbox猜测；无定位不能宣告缺失；视觉内容及图像语义不在本研究中评分。

## 7. 成本可比性

本轮重新核验2104份原始成本记录，其中2080份为各原执行阶段observation，24份为worker/inference生命周期资源与归属记录。逐轮汇总从原始时钟重新计算，与历史原值相等；初始化、8页三case预热、quality800和perf80三轮保持分开。原始运行ID为`20261026-lite-v3`，原Native执行软件为`c6e7f5c0cdcbb8801d17595c515fcbe7794111c396bfe58a6d0ab71a199db28e`。没有重新运行quality800/perf80或解析模型。

| 配置 | S3原case秒 | S4原case秒 | S6原case秒 | quality800串行时钟和秒 | perf80三轮各时钟和秒 |
| --- | --- | --- | --- | --- | --- |
| P01 | 5.088 | 6.087 | 3.882 | 1565.346 | 201.004 / 199.899 / 199.424 |
| P02 | 5.140 | 5.935 | 4.002 | 1478.303 | 186.266 / 186.332 / 187.188 |
| P03 | 13.369 | 100.704 | 5.431 | 11576.992 | 1001.961 / 893.875 / 937.507 |
| P04 | 15.266 | 102.736 | 5.532 | 11826.903 | 778.186 / 967.767 / 778.310 |
| P05 | 6.828 | 22.159 | 3.751 | 2908.116 | 278.233 / 275.325 / 276.465 |
| P06 | 6.576 | 11.027 | 3.976 | 1619.337 | 202.435 / 202.140 / 202.872 |
| P07 | 7.682 | 16.997 | 3.975 | 2411.696 | 279.992 / 276.897 / 274.570 |
| P08 | 7.233 | 26.700 | 5.096 | 3327.525 | 316.181 / 310.530 / 311.491 |

S3/S4/S6列来自各自原observation，是原case时钟，未按页面比例分摊全局总时长。quality/perf列为串行case处理时长之和，不是整批首尾墙钟；perf重复不增加独立文档样本，也不能直接当作本三个选段各自的完整重复性能试验。CPU时钟、进程RSS、cgroup生命周期峰值、API请求观察、初始化与推理就绪时间及采样覆盖见[原始成本证据](../../runs/lite/native-only/s3-s4-s6-20261116/cost-evidence.json)，保留原字段及缺测，不把缺少重试字段解释为零次重试。没有把父case时钟推算为每页精确耗时。

| 配置 | SDK初始化秒（各自观测） | 推理服务初始化至就绪秒 | 8页预热case时钟和秒 |
| --- | --- | --- | --- |
| P01 | 7.728 | 49.835 | 27.494 |
| P02 | 8.023 | 50.305 | 22.641 |
| P03 | 4.558 | 16.838 | 103.015 |
| P04 | 4.348 | 15.718 | 105.752 |
| P05 | 5.406 | 51.165 | 38.007 |
| P06 | 7.540 | 101.159 | 16.151 |
| P07 | 7.318 | 100.816 | 31.422 |
| P08 | 4.675 | 48.354 | 36.183 |

| 配置 | S3/S4/S6 worker CPU秒 | S3/S4/S6 观察RSS峰值MiB | S3/S4/S6 已记录API响应条数 |
| --- | --- | --- | --- |
| P01 | 20.017 / 32.542 / 9.784 | 3505.13 / 4032.90 / 4706.78 | 8 / 0 / 2 |
| P02 | 20.651 / 32.487 / 10.484 | 3510.40 / 4604.16 / 5308.44 | 8 / 0 / 2 |
| P03 | 2.843 / 6.609 / 1.883 | 687.22 / 1043.64 / 1079.97 | 3 / 7 / 1 |
| P04 | 2.853 / 6.242 / 1.929 | 687.02 / 1063.98 / 999.67 | 3 / 7 / 1 |
| P05 | 24.430 / 56.645 / 9.140 | 2852.14 / 4019.01 / 3944.96 | 16 / 86 / 2 |
| P06 | 26.008 / 46.246 / 9.830 | 3059.59 / 4561.22 / 5332.03 | 8 / 0 / 2 |
| P07 | 24.386 / 46.095 / 10.143 | 2969.54 / 4382.79 / 5207.50 | 9 / 7 / 2 |
| P08 | 2.810 / 6.232 / 2.147 | 755.76 / 1170.68 / 1103.43 | 23 / 102 / 22 |

SDK初始化、推理服务就绪和预热属于不同观测边界，分列保留，没有相加创造初始化总成本。worker CPU秒是工作进程CPU时间，多线程可大于墙钟；不能代表未单独测得的全部推理CPU时间。RSS为各case观察到的工作进程峰值，cgroup生命周期峰值另存，不充当该case全部进程/GPU峰值。已记录响应均保留retry=false；空响应列表只说明没有这些响应记录，不证明整个系统零API或零未观测重试。P03/P04的响应usage未提供，不能视为零token。完整24case CPU、RSS、API、初始化及GPU采样覆盖见[成本观测明细](../../runs/lite/native-only/s3-s4-s6-20261116/cost-resource-api-detail.json)。

历史资源预算保持：CPU预处理8核/8GiB，推理4核/20GiB，自有评测GPU预算16GiB。GPU归属采样为partial，只能解释所观测生命周期窗口的下界，不能给24组合各自独立完整GPU峰值。TTS当时共驻、活动未受控制；起止记录71至76、观察到5个新增任务，短活动可能未被捕捉。现有数据不支持独占GPU、TTS空闲、能耗或24组合完整资源性能排名。后处理与本轮研究读取/比较/聚合不是Native解析成本。

首次中断的全量profiling尝试观测4118.765秒，保存10份完整比较；该额外软件耗时单独披露，不计作Native解析时间、有效研究样本或性能重复。

| 本轮CPU分析阶段 | 观测秒 | 范围 |
| --- | --- | --- |
| Native独立读取 | 7.941 | 一次读取24份及自身序列化 |
| Native实际比较 | 5363.944 | 原grade_layers 24次 |
| 原trace保存 | 684.262 | 24份完整比较trace |
| 入口总观测 | 6144.373 | 含授权/绑定复核、限制保留、审计及边界计时开销 |
| 研究聚合与验证 | 14.260 | 含绑定及trace/字符容量复核 |
| 历史成本读取复核 | 10.312 | 仅当前软件分析耗时 |

这些阶段具有父子包含关系，不相加创造总时长；边界计时及I/O审计开销没有被估计扣除。Native主入口按固定顺序串行调用比较器，最多8 CPU、8GiB地址空间，无GPU可见性、无网络；父进程观测峰值RSS为2882.15 MiB。Native独立读取另有源目录屏蔽和无Expected/Final访问审计。[实际CLI及分阶段观测](../../runs/lite/native-only/s3-s4-s6-20261116/evidence/native-execution-complete-receipt.json)、[执行边界审计](../../runs/lite/native-only/s3-s4-s6-20261116/evidence/native-execution-complete-audit.json)与[17项新source-only测试](../../runs/lite/native-only/s3-s4-s6-20261116/evidence/aggregate-tests.json)分别保留软件、资源及验证身份；测试数不作为质量成绩。

## 8. 研究结论

本轮已经形成可解释的有限Native逐要求研究结果，24个固定组合全部实际执行；共同T/L/B分别为23650字符、242项、23项。P01-P08的T已决覆盖依次为35.76%、35.76%、94.12%、91.18%、34.36%、93.33%、93.33%、88.42%，其中96.20%的共同T字符来自S4。现有T上下界全部互相重叠，不能由这些部分覆盖比例生成八组T质量排名。L确认范围最多的是本选段的P07（66/242，27.27%），具体增量来自S4的61项文档归属；其他管线的不确定关系没有被证实为错误。共同B中七组仅确认3/23，P05为0/23已决，且S6全部未决，不能形成完整业务质量横向结论。证据支持比较这些责任上的可靠文字对应、已定位字符差异和独立证明的局部结构/字段保留；仍存在大量未决关系。共同集合并非八组全部已决的子集，不能用覆盖较少但辅助已决准确率较高来宣称优势。

可以确认的差异须逐层理解：T反映已定位字面与原字符政策下的编辑，不直接给业务关系通过；L反映有原生证明的关系，其余保留父链/顺序/身份未知；B共同只覆盖字段与导航值，98项源文业务责任因比较能力统一排除，不能声称完成法律或票面利率整段语义评价。原生缺字、错值或缺关系须有独立缺失/冲突证据，未决不能归因为解析器错误。

比较器来源明确的限制是合法改写业务等价能力缺口；实际未决还包括对应定位及原生关系证据不足，不能全部归因软件或全部归因解析器。当前证据不足以形成八组总体质量、完整文档类型、完整业务语义或质量/成本综合排名。研究结论仅适用于三个既有开发暴露选段、固定Native输入和此软件冻结，不推广为留出集结论、Product收益、正式Lite质量或模型一般能力。

## 9. 后续决策

本研究的可用决策是保留逐要求证据、按层解释可靠对应与局部差异，并继续撤回完整Lite成绩。真正改变结论所需的是：在独立受控及真实格式证据上验证源文业务合法改写的等价判断，以及补足可审计的原生导航/父链/顺序或对应身份依据。未决不逐条复制为待办，不据本研究选择总体获胜管线；新文档、留出试验、模型运行、完整Lite或Product评价仍需其各自授权与正式门禁。

</details>
