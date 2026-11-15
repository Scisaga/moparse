# MO-Parse 固定Native/Final独立诊断

## 第十五阶段：评测文字读取与匹配修复

2026-11-15，已完成实际评测代码修改和固定九选段的全部72组配对回归；72份Native与72份Final均重新独立读取并比较，没有重新解析或转换。所有最终trace使用评测源码`ad49afdc37e3bfb2489ec2768638d6b4d7bd18920f57610addc7ad3b1ebda72e`；`diagnostic_only=true`、`publishable=false`，不发布质量分数或排名。当前HEAD为`f4c884d14061eb3ffee6a561cafb9f5592ee2f66`。

实际调用保持`read_candidates → read_candidate/read_candidate_markdown → three_layer._text_layer → literal_readback.match_text`，候选读取先通过`literal_readback.text_readback`暴露自身片段。`_finish`此前保留的完整对象有时跨原生分块合并，或把标题/标签和邻近文字组成一个T单元，导致已有局部文字不能独立对应；它本身与Expected编译保持不变。本轮读取视图复用`source_fragments`、locator、`block_lines`和局部跨度，保留整个原单元；句界、完整括号标签及有标签列表中的显示路径只从候选生成，不接收Expected、不增B/L事实、不改正文。`match_text`优先完整精确责任，保留各次真实出现及父子视图共享容量；同字面重复按有限出现数量及自身上下文对应，仍有多个合法范围时留歧义，不能借同名另一位置。完整trace复核独立重建读取视图与消费记录，拒绝伪造跨度或重复消费；旧直接调用的贪心分支已移除。

### 五个真实锚点

| 案例 | 修复前实际问题 | 本轮真实结果及边界 |
| --- | --- | --- |
| U02，S2/P03，T68 | Final贪心选择页首同名标题，独立复核为未决；Native原来正确 | Native仍正确；Final明确未决，没有接受标题。公司名在L91，媒体告警“图片未交付。”在L93，董事会/日期在L95/L97，不能跳过中间实际段落构造签名 |
| U03，S4/P03，T32 | 232字符要求位于677字符原生对象内部，Native整单元未可靠对应；Final已正确 | 两侧均正确。Native为`#/pages/2/raw/res/parsing_res_list/4`、`block_lines=[1,1]`、局部`[0,232]`；Final为`markdown:L65:32`、`[0,232]`。其余条件、否定和文字保留；不接受未知法律父链 |
| U04，S9/P01，T86 | Native已正确，Final显示行路径中的本源标签未认领 | 两侧均正确。Native为table8/cell62、row8/col1；Final为`markdown:L501:381`、`[28,33]`中的“资本充足率”。原格尾部空白仍保留严格差异，不生成第二次出现；不接受整条业务关系 |
| U05，S7/P08，T1 | Native正确；Final标题与后续媒体告警处于较大文字单元，未正确定位 | 两侧均正确。Final为`markdown:L9:4`、`[0,24]`的实际标题；中英文边界空白沿用原canonical政策，没有新空白规则、标题层级或多栏顺序推断 |
| U10，S8/P01 GLM，T5 | 两侧完整括号文字中标签未独立进入对应，原审查为未决 | 两侧均正确。Native为`#/pages/0/raw/json_result/0/7`、`[1,5]`；Final为`markdown:L15:7`、`[1,5]`。地址、括号及剩余文字保留，没有新增B层责任 |

表中T编号均为完整`projected-text:N:sentence:0`。修复前复现保留实际旧比较器结果和当时独立责任状态；修复后使用完整最终回归trace，不在侧车中手工指定correct。见[修复前锚点](../../runs/lite/diagnostics/text-readback-phase15/anchors-before.json)、[修复后锚点](../../runs/lite/diagnostics/text-readback-phase15/anchors-after.json)、[实际候选读取](../../runs/lite/diagnostics/text-readback-phase15/full-reading/candidate-reading.json)及[完整比较执行](../../runs/lite/diagnostics/text-readback-phase15/full-comparison/diagnostic-execution.json)。

### 完整回归变化及反例

固定九selection的28,608条配对要求保持原ID、文字范围及分母；每侧T为12,616条、L为11,456条、B为4,536条。144份比较没有新软件异常或绑定失败，L/B的所有原始outcome及载荷逐条完全相同。4,112条T记录改变了状态或实际对象，对同一新版本逐项分类核对如下；同状态换位置也在其中，不可全部计作新修复。

| 变化机制 | 记录数 | 核查依据 |
| --- | ---: | --- |
| 读取候选自己的语法片段 | 490 | 实际对象等于候选阶段生成的连续片段；本轮正确项均符合未改canonical，保留剩余文字 |
| 完整出现重新分配 | 307 | 实际对象仍为原完整视图，来源容量有限；包含原来已正确但位置变化的记录 |
| 明确出现或视图歧义 | 1,820 | 多个合法候选，未选actual、未发布分数，保留所有命中及来源 |
| 既有阈值下非等价对象对应改变 | 1,411 | 实际对象来自自身候选，仍按原0.35阈值及字面编辑保留错误，没有变成正确 |
| 容量占用或未定位，无缺失证明 | 84 | 不声称候选缺字；保留原要求，审查仍未决或blocked |

原始比较器状态中539条incorrect转correct、258条correct仍correct但换位置；这些均从实际候选视图重建验证，没有手工通过。1,820条明确歧义包括909条incorrect转unresolved、911条correct转unresolved。49条correct转incorrect均没有actual：原正确对象在新读取表中逐字保持，已被另一条同字面要求消费，全部有实际容量持有者；它们属于有限出现重新分配，审查状态保留未决，不能解释为本轮候选内容丢失。历史责任或结构限制不因新T对应撤销，且没有只改变侧车审查边界而无核心读回变化的记录。完整[变化清单](../../runs/lite/diagnostics/text-readback-phase15/changed-comparisons.json)、[逐类复核](../../runs/lite/diagnostics/text-readback-phase15/transition-review.json)、[49条容量持有者](../../runs/lite/diagnostics/text-readback-phase15/capacity-transition-review.json)及[新旧审查状态汇总](../../runs/lite/diagnostics/text-readback-phase15/regression-summary.json)保留不同层次。没有未解释的批量状态变化；这些诊断不重做历史产品阶段归因，也不证明所有其他未决已解决。

实际负例保持：S9/P02的T23/T31仍把Expected邮箱`pabdsh@pingan.com.cn。`与本源实际`abdsh@pingan.com.cn`定位后判错；T238/T241/T244仍分别比较`25,321/91,674/185,838`与本源`5,321/1,674/85,838`，Native和Final共10条均错误，没有借其他单元格或补首字。S2/P01、P02的T25仍是Native含CRLF正确、Final内部空格错误；产品允许该显示规范化，T政策并未改。独立合成反例同时验证否定、条件、例外、数值、日期、代码、引用、重复容量和插入正文/标题/列表/媒体/表格屏障，Final没有借IR或其他阶段补文字。详见[真实负例](../../runs/lite/diagnostics/text-readback-phase15/negative-controls.json)及`tests/unit/test_literal_readback.py`。

最终`source-only-frozen`通过99个受影响已审查模块、2,249项测试；81个排除模块未收集，73个其他允许模块未运行。旧测试/Oracle断言不变，仅新增独立合成测试及其source-only清单条目。测试和真实诊断使用串行、8 CPU上限、8 GiB、GPU不可见及禁网隔离，候选读取时Expected被屏蔽；最终审计无违规。完整[测试回执](../../runs/lite/diagnostics/text-readback-phase15/source-only-frozen.json)、[开发过程](../../runs/lite/diagnostics/text-readback-phase15/development-attempts.json)和[最终绑定](../../runs/lite/diagnostics/text-readback-phase15/final-binding.json)保留实际范围，历史267/4282不计入本轮。

### Native范围与正式门禁

[冻结准备记录](../../runs/lite/diagnostics/text-readback-phase15/native-research-preparation.json)首先固定S3/S4/S6三个完整既有selection、全部P01–P08的24个Native组合，再给各层状态，不按成功要求重新定义分母。逐条包含原生工件、observation、原配置、页分支/主视图/来源许可、当前比较器、完整要求视图和历史独立验收依据、未就绪要求ID及trace、失败/缺失/软件限制/歧义的分开处理，以及原始成本和共享TTS工作负荷不受控等限制。历史独立来源验收未重签为当前通过；三个selection已有开发暴露，不是留出测试或完整Lite代表。媒体未交付不自动阻断独立T，T也不代表三层总质量。

正式执行尚需批准上述完整研究范围、同版独立验证与具体不确定性处置、授权并绑定正式scoring freeze。当前正式`evaluate_saved`仍拒绝diagnostic以外的`sample_ids`；原Lite声明及`requirements/current`保持，不裁manifest、不建active current、不造获准freeze。准备记录提供本轮实际运行的候选读取/比较命令；正式命令为空并列出不可执行原因。107份责任缺口、3份待独立验收、5个输入范围仍保留，不要求全部清零才允许有限研究准备。

四类身份分别保留：原Native为`c6e7f5c0cdcbb8801d17595c515fcbe7794111c396bfe58a6d0ab71a199db28e`，公共Final转换为`f8bcef05feaa4406189d395219a4db50afb8cc9446600ee11adce7fb403e0f1f`，历史phase13诊断为`8eb9d431864ea4c0baec2cb661c726ba457490b852b682d286a9786c4ac29146`，本轮评测为`ad49afdc37e3bfb2489ec2768638d6b4d7bd18920f57610addc7ad3b1ebda72e`。727份绑定工件、九份要求视图、72份Final/Storage和83份生产支持源码保持；详见[只读保全](../../runs/lite/diagnostics/text-readback-phase15/preservation.json)。没有模型、公共转换、PDF/图像、OCR、网络、GPU/TTS、在线服务、部署、正式评分、提交或推送。

## 第十三阶段（历史）：固定Native/Final独立诊断

以下保留phase13原始结论与当时身份；“当前”“本轮”和计数均属于该历史阶段。本轮读回诊断以上述第十五阶段为准，历史原始trace及产品阶段证据未覆盖。

固定9个选段、72条Native/Final诊断已完成；实际可诊断要求11525项，未决或软件阻塞17083项；正式成绩仍未发布。

2026-11-15。本报告限固定8份文档、9个独立selection、72条selection/pipeline及64个唯一document_id/pipeline组合。统计单位是已有要求在每条选段/管线链上的诊断状态；不等于正式分母、T/L/B分数或解析器排名。D5的S5（68–70）与S6（14）保持独立授权、读回、正文和要求。

`diagnostic_only=true`、`publishable=false`、`quality_scores_withheld=true`。唯一正式质量状态仍由[Lite报告](report.md)维护，仍为`structure_blocked`；107份责任缺口、3份完整责任待独立整样本验收和5个输入范围保留。

## 身份、输入与执行

接手及当前HEAD为`d77087f531d085de1d1c79fbcb8b67e5e95f5fb1`，接手工作区干净。72份Final的实际公共转换software_id均为`f8bcef05feaa4406189d395219a4db50afb8cc9446600ee11adce7fb403e0f1f`；当前诊断源码为`8eb9d431864ea4c0baec2cb661c726ba457490b852b682d286a9786c4ac29146`。初始HEAD中的转换源码、Python和依赖已对照原最终绑定核验，没有回退或重新转换。Native运行仍为`20261026-lite-v3`，其原software_id保留`c6e7f5c0cdcbb8801d17595c515fcbe7794111c396bfe58a6d0ab71a199db28e`。

[输入绑定](../../runs/lite/diagnostics/native-final-phase13/input-binding.json)、[接手核验](../../runs/lite/diagnostics/native-final-phase13/intake-verification.json)、[最终绑定](../../runs/lite/diagnostics/native-final-phase13/final-binding.json)保存72份native/observation/Final SHA、各自selection、实际producer/configuration、物理页/分支映射、stage evidence和delivery state。所有Final均来自phase12同版明确绑定；没有读取旧baseline补齐、复制开发正文到current或制造active索引。

候选读取进程先在Expected被屏蔽的只读挂载中读Native JSON/配对observation及实际final.md，再保存独立候选图。独立比较进程使用这9份既有要求视图，流式定位canonical Expected的授权行，仅向比较器暴露原source-map选中的文字；定位所经前缀不解析、不缓存。S5/S6不会互相导入文字或外部上下文。比较使用现有Requirement AST、Document AST、三层比较器及trace storage；没有重编译Expected，没有将Expected传入生产Adapter、IR、Semantic、FinalContent或Storage。

已执行72份Native及72份Final内容诊断。完整[执行状态](../../runs/lite/diagnostics/native-final-phase13/diagnostic-execution.json)、[Native记录](../../runs/lite/diagnostics/native-final-phase13/native-diagnostic.json)、[Final记录](../../runs/lite/diagnostics/native-final-phase13/final-diagnostic.json)及[逐要求配对](../../runs/lite/diagnostics/native-final-phase13/paired-differences.json)引用原始对象locator、各自trace、实际Final行号及字符范围。共享trace须由`moparse_eval.trace_storage.read_score`展开后解释JSON Pointer。

## 实际软件阻塞与修复

实际诊断暴露两类软件缺陷：已有原生/SDK标题层级未完整进入共同候选图，或缺层级时留下默认层级猜测；以及同一Native Markdown字段内的不同段落共享路径，来源身份遗漏block_lines，误读另一段文字。标题修复只暴露本对象已存字段，撤回无依据的层级；源文字、数值、关系答案均未补造。block_lines修复只补足既有来源定位键，不改T/L/B定义、权重、等价规则或正式分母。

GLM分支的真实反例中，第三行数字`10028161`曾错误解析为第一行公司名的前8字，导致10份Native比较软件阻塞；该问题与五个管线编号中的同一GLM分支有关。原失败、修复及[受影响侧重比](../../runs/lite/diagnostics/native-final-phase13/compare-source-closed/diagnostic-execution-complete.json)分别保留，没有计候选零分。未受影响输入仅在完整候选图相等、比较器不变，或新增来源键在要求和候选图中均不存在的严格不变性回执下复用同一当前工件的旧trace；不是回退旧Final。

[267项相关source-only回归](../../runs/lite/diagnostics/native-final-phase13/source-only-frame-identity-final.json)通过，范围为7个已审查模块；历史4282项未重跑，也不计入本轮。源切片缓存仅在一次串行诊断内复用实际候选切片，现有S4/P01的362条完整trace与无缓存版本完全一致，见[缓存对照](../../runs/lite/diagnostics/native-final-phase13/cache-equivalence.json)。测试失败、调试中断及元数据检索偏差均见[过程记录](../../runs/lite/diagnostics/native-final-phase13/development-attempts.json)。

可同时给Native与Final明确正确/错误状态的要求/管线记录为11525项；其余17083项含既有责任blocked或任一侧unresolved。Native单侧可诊断13206项，Final单侧可诊断15114项；最终执行软件阻塞链为0。归因H还包括两侧虽有比较状态但无法证明同一错误或变化来源的记录，不能与17083项混同。

## T/L/B逐要求状态

| 层 | 要求/管线记录 | Native正确 / 错误 | Native未决或阻塞 | Final正确 / 错误 | Final未决或阻塞 |
| --- | ---: | --- | ---: | --- | ---: |
| T | 12616 | 4796 / 1676 | 6144 | 4420 / 3733 | 4463 |
| L | 11456 | 575 / 3991 | 6890 | 585 / 4086 | 6785 |
| B | 4536 | 320 / 1848 | 2368 | 325 / 1965 | 2246 |

原比较器的完整outcome保持原样。诊断侧另保留具体责任依赖、原生父链/顺序未知和有来源证明的读回限制；只撤回无法成立的质量判断，不增加质量通过。尤其是未匹配到一对一文字单元，不能证明Native或Final缺字；本对象的实际Final跨度若仍含原字，也不能认定Final漏字。相同字面不能借另一对象补位置。`requirement_status=accepted`仅表示已有比较责任可用，不代表整样本或正式质量验收通过。

## Native到Final的实际归因

A/B/C/D/E/F/G/H/I分别保留原生正确并保留、原生错误并保留、有证据恢复、最终退化、共同不完整、无依据新增、重复、无法判断、交付受限。文字表达或匹配状态变化与识别内容修复分开；阶段信息流保全也不替代Expected正确性。每项变化可定位到实际阶段，或明确earliest_change_unknown，不用最终形状反推最早故障。

**已证退化D：2条。** S2/P01、P02的同一个表头来源格`#/documents/0/document/tables/0/data/table_cells/2`原生为“本次回购后\r\n拟注销数量”，现有T合同判正确；Adapted首次变为“本次回购后 拟注销数量”，后续各阶段及Final沿用该内部空格，T判错误。P01的实际Final跨度包括[1036,1047]。这证明文字保真退化，未证明数字或业务关系损失；其L/B责任缺口单独保留。

**有来源的表达恢复C：7条。** S9的P01/P03/P04/P05/P06/P07/P08将同一原生表内“流动性比例”和“外币”的表头路径表达为“流动性比例 / 外币”，符合已有T文字要求。两格原生身份、父表及共同Semantic row_headers记录均已绑定；IR中未出现组合标签，Semantic首次出现，Final保留。P06的来源为同表cell[11]（rowspan=3）与cell[20]，Final第490行。两词及原表关系早已存在，这是公共表达恢复，不是识别模型修正，也不证明该表全部关系正确。

**共同错误保留B。** S4/P01第一定义原生使用直引号、引号内额外空格，并将三段定义放入一个对象；Final[0,243]保留同一原生对象的文字。相对Expected的字面差异始于Native。逐要求B分类须有相同实际错误载荷和本源Final跨度或同一结构载荷证明，不能只因Native/Final都判错误或整体字符来源账本已验证就认定保留。

**保留正确A与读回限制。** S6/P01有独立要求支持的局部文字保留；逐要求证据保留原生来源和实际Final行号，不据此接受所有目录页码或导航。S4/P03/P04的一条232字符法律句子原本已在677字符Native对象中，各阶段没有改变；不能算产品恢复。S9/P01“资本充足率”仍在本源Final[9214,9219]，不能算丢字。S2/P03/P04的公司名、董事会与日期也分别保留在各自Final跨度，但文字单元匹配仍未决，不能借页首同名标题接受整段。

**最早阶段与未决。** 2条已证退化最早为Adapted，7条组合标签表达恢复最早为Semantic；同一错误载荷保留的来源为Native。没有独立证据的IR、Semantic业务错绑、FinalContent丢失或Delivery正文丢失保持unknown，不能据此宣称零缺陷。874条B与4,268条A之外，23,457条归因仍为H；这与要求责任或某一侧未决的计数不同，不能相互替代。

**原生格式的局部限制。** P01的S4正文对象只有一般容器父链，不能证明法律定义父链；P03/P04某些SDK标题与独立文本片段能够支持局部保留，但整句读回仍会受分块影响；MinerU的HTML合并格保留了S9独立来源，页镜像locator须经显式native_document与全部原始字段相等才能连接完整文档；缺全局顺序证据时继续unknown。P08缺乏明确层级的对象不能套用默认标题层级。这些是本固定开发集合的局部证据，不能推出解析器总体优劣或一般结构风险排名。

**合法显示与未决内容分开。** 原生HTML单元格及最终表头路径、普通段落与多个独立签名行可以有不同显示形式，但必须分别服从T字面、L结构和B关系合同；标签仍在不等于整个关系已正确。一对一检索未定位到字句不证明遗漏；相同字面出现多次不能抵消另一原生对象的缺失。未证实F无依据新增、G重复关系或E原生执行不完整的实例不记为零缺陷；原生执行记录72份completed与Final交付partial分开。

完整[逐阶段归因](../../runs/lite/diagnostics/native-final-phase13/stage-attribution.json)与[实例证据](../../runs/lite/diagnostics/native-final-phase13/case-review.json)给出具体引用。表示形式的最早变化与质量错误的最早阶段分别保留。已有反向字符来源账本不等于语义零错误证明；未判定额外文字、重复关系及缺失阶段证据继续未决。

## 固定复杂结构

S4的200个含if/unless/except/provided/not/no/only的原生对象保留独立身份与Final跨度，原生父链不足时不按Markdown缩进或Final反推。S9八组各9张物理表保留各自表头、空格、单位、期间、同字面格及来源，没有独立续表证据就不强制合并。逐对象证据见[结构证据](../../runs/lite/diagnostics/native-final-phase13/fixed-structure-evidence.json)。

S1检查正文顺序和跨页续接；S2检查变化列、日期、单位、空格与列表；S3检查原生文字、视觉区域声明和媒体交付；S5检查括号负数、期间、附注和合计；S6检查字面目录页码及导航顺序；S7检查双语、多栏、签名与同字面不同来源；S8保留网格、印章和scan-like声明，来源仍为unknown，未认定为真实扫描来源。没有读取PDF、图像或像素，不进行图片语义解释。

## Expected责任阻塞

| 选段 | 比较责任完整 | 既有义务阻塞记录 | 既有分析限制阻塞记录 | 输入范围待确认 |
| --- | --- | ---: | ---: | ---: |
| S1 | 否 | 5 | 1 | 0 |
| S2 | 否 | 5 | 3 | 0 |
| S3 | 是 | 0 | 0 | 0 |
| S4 | 是 | 0 | 0 | 0 |
| S5 | 否 | 0 | 7 | 0 |
| S6 | 是 | 0 | 0 | 0 |
| S7 | 否 | 3 | 4 | 0 |
| S8 | 否 | 3 | 2 | 0 |
| S9 | 否 | 159 | 190 | 0 |

S3/S4/S6已有独立整样本源/合同验收；其余6个选段有具体责任缺口，并非历史107份缺口全部属于本集合。表中义务与分析限制记录可能重叠，不能相加为新分母。9个选段均不包含那5个待确认输入范围，全局5项仍保留，不能自动解除；全局3项待独立整样本验收同样保留。B或L缺口不自动阻断独立T，但依赖结构定位的具体判断仍保留阻塞，见[责任及读回限制](../../runs/lite/diagnostics/native-final-phase13/requirement-blockers.json)。

## 各管线诊断摘要

| 管线 | 链数 | Native可诊断 | Final可诊断 | 均正确A | 同一错误保留B | 表达恢复C | 退化D | 归因未决H | 软件阻塞链 | delivery partial |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P01 | 9 | 1737 | 1722 | 468 | 200 | 1 | 1 | 2906 | 0 | 8 |
| P02 | 9 | 1688 | 1696 | 412 | 203 | 0 | 1 | 2960 | 0 | 8 |
| P03 | 9 | 1656 | 1973 | 599 | 65 | 1 | 0 | 2911 | 0 | 9 |
| P04 | 9 | 1665 | 2007 | 653 | 71 | 1 | 0 | 2851 | 0 | 9 |
| P05 | 9 | 1469 | 1791 | 364 | 115 | 1 | 0 | 3096 | 0 | 6 |
| P06 | 9 | 1672 | 1959 | 604 | 84 | 1 | 0 | 2887 | 0 | 7 |
| P07 | 9 | 1675 | 2002 | 593 | 72 | 1 | 0 | 2910 | 0 | 7 |
| P08 | 9 | 1644 | 1964 | 575 | 64 | 1 | 0 | 2936 | 0 | 9 |

按P01–P08固定顺序列示，不按计数排序；这些是要求级状态数，没有百分比、总分或排名。各管线版本、producer及分支按原输入绑定读取，不能把GLM分支的软件读回缺陷归给管线名称所指的另一原生解析器。

## 各文档诊断摘要

| 文档 | 独立选段 | 链数 | 均正确A | 原生错误保留B | 表达恢复C | 退化D | 无法独立归因H | 媒体声明 / 交付 | delivery partial |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| D1 万科债券利息 | S1 | 8 | 146 | 48 | 0 | 0 | 622 | 2 / 0 | 5 |
| D2 万科股份变动 | S2 | 8 | 229 | 93 | 0 | 2 | 1092 | 12 / 0 | 7 |
| D3 振业票面利率 | S3 | 8 | 130 | 51 | 0 | 0 | 275 | 2 / 0 | 8 |
| D4 腾讯债券计划 | S4 | 8 | 1236 | 232 | 0 | 0 | 1428 | 0 / 0 | 3 |
| D5 华为年度报告 | S5, S6 | 16 | 914 | 80 | 0 | 0 | 10782 | 14 / 0 | 16 |
| D6 华为技术跨版 | S7 | 8 | 131 | 30 | 0 | 0 | 343 | 34 / 0 | 8 |
| D7 浦发银行封面 | S8 | 8 | 62 | 39 | 0 | 0 | 235 | 72 / 0 | 8 |
| D8 平安财务报告 | S9 | 8 | 1420 | 301 | 7 | 0 | 8680 | 34 / 0 | 8 |

适配、IR、Semantic、Final和Delivery的可证错误分别写在逐要求stage_evidence与earliest_change_stage。某类没有已证实例，不代表全局零缺陷；缺阶段证据时保持unknown。D5统计16条链，但S5/S6正文及页范围始终分开。

## 交付、保全与正式就绪状态

72份Final与各自实际Storage result.md已重新核对UTF-8字节一致；正式交付仍为9份completed、63份partial，170项媒体声明没有验证或交付图片字节。partial还包括必要顺序、未知用途或关系责任，不是质量零分；completed也不是质量通过。729份受保护文本工件及9个已用要求视图保持原SHA，正式requirements索引仍为`09918d7c652aee0d306dc603cbf7c827c6ca01996b8a436d72fb8d4f803b6884`。

Native正式评分：不具备条件。Product正式比较：不具备条件。仅本固定9个选段的有界诊断已闭合，仍缺全局责任及独立验收、统一正式freeze和交付准入；没有解除structure_blocked，没有启动quality800重评、正式聚合、排名或八组正式回放。

未进行解析模型、公共转换重跑、PDF/图像字节读取、PDF字层、OCR/VLM、网络请求、GPU/TTS/在线服务、部署、提交或推送。曾有一次普通检索因历史分类工件单行存储而返回全域诊断元数据；该偏差已单列，未打开额外canonical Expected、未用于答案判断，后续诊断访问被限制为固定9选段。调试中断时对不存在的<unknown>伪源码读取被审计拒绝，未读取输入内容。

资源及访问证据见[最终比较审计](../../runs/lite/diagnostics/native-final-phase13/source-frame-final-audit.json)、[候选隔离审计](../../runs/lite/diagnostics/native-final-phase13/candidate-validated-audit.json)、[保全](../../runs/lite/diagnostics/native-final-phase13/preservation.json)和[最终绑定](../../runs/lite/diagnostics/native-final-phase13/final-binding.json)。内容比较使用串行单worker、最多8 CPU与8 GiB地址空间、独立网络命名空间和空GPU可见性；新诊断耗时仅作为分析成本保存，没有写入原Native或Product处理成本。
