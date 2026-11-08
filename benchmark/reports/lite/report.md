# MO-Parse Lite：文档 AST 对应与验收合同接入

文档AST对应、四态判定和版本化验收门禁已完成本轮source-only软件接入；真实候选比较、回放及质量评分仍未执行。华为、顺丰、中石化在同一当前源码及唯一current下重新通过原有完整来源Oracle。173份中21份比较责任完整，只有3份具备本轮绑定的独立样本验收；全局门禁继续拒绝实际执行。

## 对应、判定与独立证据

两个问题均先在完整生产链复现并保存[失败记录](../../runs/lite/requirements/validation/document-reproduction.txt)。培训改写在compare_content_ast为unresolved，旧文档对应却返回missing；两项连续要求合为一个候选块时，旧B为0/2。修复后，未支持改写沿compare_document_ast、grade_document_content及grade_layers保留unresolved，validate_evidence拒绝不完整发布；合块保持两项要求及2/2正确，分别消耗块内[0,14)及[14,36)，不重复消费。

1:1、1:N、N:1及有界N:M均由独立合成文本通过read_expected、来源审计、要求图、evaluation_projection、候选独立读取、grade_layers及最终证据重放验证。容量使用原始来源半开跨度，阅读顺序使用实际块序及块内位置。同块反序保留两项B正确并使相应L顺序错误，不能按expected重排。所有检索候选、范围拒绝、容量冲突、切分依据、已消费及未消费跨度和8块上限均保留。无文字图片和表格也保留为结构屏障；不跨标题、列表父级、插入正文或独立范围拼接。

完整原文和既有18/18.0等价正常通过；已支持的19小时、错误单位、年度或限定正常判conflict。可检查范围为空、或已被其他独立要求排他覆盖时判missing；低于0.65检索阈值、未知改写、重复身份或超出分块支持时保留unresolved，完整要求分母不变且相关层成绩为空。文字不同本身不证明业务不同义，正确数值也不能消除重复身份。跨新标题的部分残句旧测试由incorrect改为unresolved，因为没有完整身份或删除证明；原有三份来源Oracle断言没有随之改写。

混合块只替代内容要求实际拥有跨度内的局部语言解释。完整财务数量及关系继续由已有类型化比较器负责；合块中一项正确、一项错误仍独立出结果。独立反例还覆盖未消费插入内容、未知限定及治理引号分析：被内容合同替代的引号分析不再阻断邻接数量，保留的类型化事实仍声明自己的比较能力。

## 合同与门禁

拥有定义见[评测任务](../../evaluation-tasks.md#文档-ast-与内容比较)。semantic/1保持原语义完整条件；document_ast/1分别验证授权来源、结构、固定比较责任、具体未决归属、逐样本独立来源断言和能力用例。源码、索引、生成视图、覆盖及证据摘要须一致；未知或不一致合同拒绝。content_comparison_ready、状态布尔值、未决改名或reason前缀均不能代替独立验收。source_obligation_pending等只有追溯到固定内容要求、完整来源及所关联义务并有独立断言时才可保留为语言分析限制，来源、范围、结构、数量绑定及要求覆盖缺口继续阻断。

原semantic_complete与分析未决保持真实。合成正例验证内容合同已独立验收而semantic_complete=False仍可准入；反例验证无逐样本断言、能力用例、完整覆盖或正确身份均拒绝。正式加载入口沿同一门禁执行，worker只接收receipt/2中的合同与摘要，不获得expected路径或答案；主机每次仍重验原证据。门禁支持不授予执行权限，当前实际source-only状态已验证会拒绝实际请求，没有生成实际worker回执。

## 当前来源基线与分母

当前绑定的[独立Oracle](../../../tests/validation/lite_source_oracle.py)保留华为52个来源、122项事实及9个非计票操作数，顺丰40个来源、133项事实及12个非计票操作数，中石化202个来源、191项财务要求、60项培训属性和73项治理内容。中石化仍为semantic_complete=False，不宣称通用中文语义解析完成。A/B/C原有范围、全部173份业务节点及关系payload均与接手current一致。

| 样本 | 分析视图T/L/B节点数 | 当前合同比较B/L要求数 | 独立来源验收 |
| --- | --- | --- | --- |
| 华为 | 407/575/122 | 122/575 | 通过，完整类型化语义及来源 |
| 顺丰 | 585/708/133 | 133/708 | 通过，完整类型化语义及来源 |
| 中石化 | 910/1284/272 | 324/1352 | 通过，文档内容及已有财务语义 |

中石化B为191+60+73=324；75项内容要求含2项只计L的标题，不能把旧分析B=272直接用作合同分母。T分析节点数也不是实际文字字符分母。候选拆块、合块、候选数量及错误不会改变同一固定expected与合同的要求身份、outcomes集合及分母。

精确跨度归属另显式纠正3份旧整块清理造成的漏计，原文、业务语义节点及关系均未改写。这些是要求投影纠正，不是匹配更容易或管线表现导致的分母变化；逐来源原文、恢复的类型化要求和剩余内容跨度见[实际来源诊断](../../runs/lite/requirements/validation/actual-source-diagnosis.json)的comparison_denominator_changes。

| 授权样本及来源行 | 旧有效比较B/L | 当前固定比较B/L |
| --- | --- | --- |
| catl-nev-battery-markets-p127-132 L1779, 1793 | 64/133 | 66/137 |
| midea-business-p013-024 L283, 287 | 68/143 | 74/161 |
| sinopec-operations-p013-024 L519 | 364/994 | 366/1002 |

## 173份覆盖状态

下列维度可重叠，不相加推导覆盖率。完整来源及结构、固定比较责任、独立能力证据、样本独立验收、语言分析和输入范围分别记录于actual-source-diagnosis.json的comparison_contract_coverage。168份含语义分析未决不等于168个新增语法包；本轮没有启动平安或其他公司的新语法工作包。

| 维度 | 当前数量 |
| --- | ---: |
| 来源或文档结构不完整 | 0 |
| 比较义务或未决责任仍有未覆盖 | 152 |
| 已声明比较能力尚缺独立受控证据 | 0 |
| 比较要求完整但缺少独立样本验收 | 18 |
| 已按声明合同独立验收 | 3 |
| 仅保留语言分析限制 | 16 |
| 包含五个既定输入范围问题的视图 | 5 |
| 既定输入范围目标 | 5 |

已执行独立受控用例绑定40种比较能力，当前视图实际声明33种。这里验证的是比较器能力；真实格式适配、全范围保存输出读取诊断及实际回放仍未验收，不能把受控能力证据等同于八种原生交付链通过。三个全局门禁继续not_passed，完整质量成绩继续暂停。

## 同版验证与交付边界

[完整受控回归](../../runs/lite/requirements/validation/software-validation.json)为 `4357 passed in 249.56s (0:04:09)`，179个测试文件；源码与测试执行期间均未变化。测试身份为 `94da6d7cbf5296bfb24b28476657a91a6dc78aa9643a3ea68f06e98244be7249`，源码software_id为 `d37c6d84db70f85b2811c11fe0c9146787e676865f5905514f4c7abeca550415`，HEAD保持 `180e91889ec19179878a4fe969cf430e2a0666a3`。接手工作区干净；接手源码software_id与上轮fcb47409记录一致，旧记录git_head早于已审查提交不据此被否定，但上轮4280项不充当本轮结果。

[173份JSON/XML](../../runs/lite/requirements/current/index.json)以16个分析进程重建，耗时139.12秒，来源完整性失败0；索引摘要为 `2a4d564c787c2315608c7619e86a88308b1642a06f12ce7170ea5a7e4161e0f5`。全部授权来源数组、原始传输清单、selection、语义投影身份及五个输入范围保持，已替换唯一current并删除失效生成视图。编译返回2表示仍有比较责任缺口，不是来源读取失败。

来源复验命令为 `PYTHONPATH=/opt/moparse .venv/bin/python tests/validation/lite_source_oracle.py --output benchmark/runs/lite/requirements/validation/oracle-validation.json --diagnosis-output benchmark/runs/lite/requirements/validation/actual-source-diagnosis.json`。完整测试命令、逐文件身份和输出在software-validation.json；regression.xml、comparison-validation.json、mutations-validation.json及baseline-preservation.json保存重放与独立断言入口。Ruff、非语料Markdown政策及diff检查通过。续做入口为[expected output optimization](../../../docs/engineering/prompts/expected-output-optimization.md)。

本轮只进行source-only软件工作及独立合成候选比较。canonical expected、映射、selection、页包、语料、有效native、历史交付及原始成本只读；未读取原始PDF、图片或字层，未执行OCR、VLM、模型裁判、真实候选比较、真实回放、正式保存输出评分、推理、GPU/TTS/在线服务操作、部署、公开API修改、提交或推送。P01—P08标签参数化只证明公共比较器一致；原生横向比较与P07/P08真实历史baseline/current配对仍分开。

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
