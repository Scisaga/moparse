# 三层矩阵的真实文字与位置诊断

本记录是软件诊断，既不提供人工成绩，也不是新的Gold、评分目标索引或语料复核。只读canonical expected、现有选段、保存的native.json及observation.json，经`compact_requirements`和`matrix_evidence.read_matrix`观察实际要求与候选证据；没有读取PDF、图片、文字层或OCR，没有模型执行、服务操作、候选改写或参考修改。验收定义仍由[评测任务](../evaluation-tasks.md#three-layer-evaluation)维护。

当前分析软件身份为`21ebba9c70e11bdae557c94cca4686df99e6432228a545d24354c93ec57d6f63`。已逐份实际复核本版华为P01-P08及顺丰P01-P08共16份完整native诊断记录，均为`status=completed`，声明`diagnostic_only=true`和`quality_scores_withheld=true`，主分及三层分数、分子均已撤回；各项来源、检索数量和拒绝原因均由本版记录重新读取，没有继承旧版判定。记录位于`benchmark/runs/lite/diagnosis/three-layer-current/private/scores/Pxx/quality800-r1/样本名.json`；只读取原子写出后的`.json`，不读`.part`或运行新评测。T/L/B成绩继续撤回，两个样本的局部轨迹不能作为全范围诊断完成、正式冻结或完整expected覆盖的声明。

以下十条要求按实际业务身份、属性、期间、币种和分组选择，查询不包含待比较的正确数值。先检查候选自己的头格和行对象，再读取值。表内引号中的值与标签是实际保存的cell.text，原始尾部空格和换行继续保存在证据对象；`qualifiers`和`identity_facets`是读取结果，不冒充原生SDK已经提供的语义字段。没有完整身份的位置保持未确认，同值不提供位置证明。

## 输入、位置和缩写

华为样本为`huawei-financial-summary-p007`，原有选段为第7页，canonical文件为`pdf_sample/parsing/expected/complex-huawei-2024-annual/expected.md`，实际声明范围L158-240。顺丰样本为`sf-revenue-operating-cost-tables-p035-036`，原有选段为第35-36页，canonical文件为`pdf_sample/parsing/expected/complex-sf-2024-annual/expected.md`，声明范围L736-765及L767-799。这些范围来自现有声明，不重新验证其与原件的关系。

每条原生文件位于`benchmark/runs/lite/artifacts/Pxx/measured-quality800-r1/样本名/native.json`，同目录observation.json提供保存的执行元数据。下列JSON路径均从对应文件根开始。行列均为保存网格的零起点，不能解释为原PDF坐标。

| 缩写 | 样本和组 | 原生表路径 | 格路径写法 |
| --- | --- | --- | --- |
| H01 | 华为P01 | `#/documents/0/document/tables/0` | `C11`表示该表`/data/table_cells/11` |
| H02 | 华为P02 | `#/documents/0/document/tables/0` | 同上 |
| H03 | 华为P03 | `#/pages/0/raw/res/parsing_res_list/2` | `C23`表示该块`/block_content::html/cell[23]` |
| H04 | 华为P04 | `#/pages/0/raw/res/parsing_res_list/2` | 同上 |
| S01R | 顺丰P01营收表 | `#/documents/0/document/tables/0` | `/data/table_cells/编号` |
| S01C | 顺丰P01成本表 | `#/documents/0/document/tables/1` | 同上 |
| S05R | 顺丰P05营收表 | `#/pages/0/raw/json_result/0/4` | `/content::html/cell[编号]` |
| S08R | 顺丰P08营收表 | `#/pages/0/raw/6` | 同上 |

## 华为：五个业务要求及其候选范围

这里的要求由相应父指标和原始叶文字共同解释。`compact_requirements`对五条叶项均保留了完整指标、期间和明确限定；例如L161编译为`attribute=销售收入`、`period=2024年`、`unit=美元百万元`、`currency=美元`，没有把“百万元”丢成普通“美元”。

| 项 | canonical expected实际要求 | 不携带正确值的位置查询 | 候选自己的头链与限定 | 定位后观察到的实际文字及诊断 |
| --- | --- | --- | --- | --- |
| H1 | L160父项`销售收入`；L161`2024年，美元百万元：118,162` | 指标销售收入，2024年，美元及百万元 | H01行头C10`销售收入 `；头C1`2024 `跨两列，C7`（美元百万元） `仅覆盖美元列。读取q为`{period:2024年,unit:美元百万元,currency:美元}` | 数据C11，row2/col1，原字面`118,162 `。当前公共轨迹B:0逐项核对6个候选后只接受该对象；指标、期间、币种、数量级和实际标题范围均有本候选来源，随后完整断言比较一致。这不是全表或完整三层验收 |
| H2 | L160父项`销售收入`；L162`2024年，人民币百万元：862,072` | 指标销售收入，2024年，人民币及百万元 | H02行头C8`销售收入 `；头C1`2024 `跨两列，C7原文仅`人民币百万元） `且跨六列。两列读取q都为`{period:2024年,unit:人民币百万元,currency:人民币}` | row2/col1的C9为`118,162 `，row2/col2的C10为`862,072 `。当前公共轨迹B:1保留这两个同身份对象，按完整断言集合报告冲突，没有按expected值挑第二格。孤立右括号的单位补读已修；USD头未保存及跨六列的实际绑定没有被改写 |
| H3 | L167父项`营业利润`；L170`2023年，人民币百万元：104,401` | 指标营业利润，2023年，人民币及百万元 | H04行头C16`营业利润`；C2`2023`为row0/col3且rowspan2，人民币百万元的另一单位格从col4开始，只覆盖cols4-6。col3实际没有单位头，q仅`{period:2023年}` | row3/col3的C19为`104,401`。当前公共轨迹B:8拒绝该对象的原因是缺unit和currency；指标、2023年及本候选自己的标题范围已经通过独立核对。不能从2022列、其他组或expected给2023列补单位；这是保存输出的限定缺口，不是已有单位的词法补读失败 |
| H4 | L174父项`营业利润率`；L175`2024年，美元列：9.2%` | 指标营业利润率，2024年，美元列，百分比 | H03行头C22`营业利润率`；头C1`2024`跨两列，C6为单格`（美元百万元）（人民币百万元）`并跨两列，没有独立的货币至列关联。两值的q均为`{period:2024年,unit:%}`，币种选择保留candidate_ambiguity | row4/col1的C23及row4/col2的C24都实际打印`9.2%`。当前公共轨迹B:12对两者均指出缺`column_currency=美元`；指标、期间、百分比单位和本候选标题范围通过核对。同值不能决定美元列，也不能把金额单位当成百分比单位；其他明确列继续读取 |
| H5 | L160父项`销售收入`；L166`2020年，人民币百万元：891,368` | 指标销售收入，完整2020年，人民币及百万元 | H02保存的年度头为`2024`、`2023`、`2022`、`2021`及截断的`202`，没有完整2020。C5的原文是`202`，不能补最后一位。当前公共轨迹B:5保留6个销售收入文字命中和5个有明确年度的候选，全部未通过2020身份核对 | 2020的位置查询未成立。原生col6的C14仍打印`891,368`，其值字面及C5的`202`均保留在当前T证据；C14没有因数值相同而进入该要求的已定位对象。此前模块级`attribute=202`观察不能代替当前公共轨迹，也不能成为新的参考要求 |

H2不是“值862,072没有识别”，H3不是“值104,401没有识别”，H4也不能因为两个百分值相同就确认币种绑定。以上分别暴露同身份冲突、限定来源缺失和候选自身歧义，不能合并成几个相互独立的数字识别错误。H5的正确数值字面不能替代完整年度身份。

本版已重新核对[H1的P01记录](../runs/lite/diagnosis/three-layer-current/private/scores/P01/quality800-r1/huawei-financial-summary-p007.json)、[H2/H5的P02记录](../runs/lite/diagnosis/three-layer-current/private/scores/P02/quality800-r1/huawei-financial-summary-p007.json)、[H3的P04记录](../runs/lite/diagnosis/three-layer-current/private/scores/P04/quality800-r1/huawei-financial-summary-p007.json)和[H4的P03记录](../runs/lite/diagnosis/three-layer-current/private/scores/P03/quality800-r1/huawei-financial-summary-p007.json)。H1保留6条文字命中和6个候选，只定位C11；H2保留6条文字命中和5个候选，其中C9/C10构成两值冲突；H3保留13条文字命中和12个候选，C19缺unit/currency；H4保留12条文字命中和12个候选，C23/C24缺column_currency，后两例均以qualifiers拒绝而实际标题范围通过；H5保留6个文字命中与5个显式年度候选，2020位置仍未成立。范围核对记录自己的heading事件、来源和结束边界，没有从expected填入候选，也没有因范围索引优化而视为恢复缺失的单位或币种绑定。

### 数量级是否真的存在

本次逐源读取了这个华为样本P01-P08的单位头及相邻已保存文字。P01、P05、P06、P07、P08都在实际表头直接打印`美元百万元`和`人民币百万元`，数量级没有依赖expected补入。P03打印了包含两种完整单位的同一跨列格，问题是单位至列的关联歧义。P04的2023列没有受到另一人民币单位格覆盖。P02保留了完整`人民币百万元`字面但丢失USD独立头，并有`202`截断；未把它改回完整年度。本诊断没有发现该样本中“只打印美元/人民币，另有共享百万元说明”的实际保存形态，也没有据此对未读样本作结论。

独立合成表达另暴露了读取软件对分布式单位的支持缺口，因此矩阵模块增加了受限组合：只有同一已证明头链中的currency-only字面和scale-only字面，或调用者提供的有来源且有边界的当前表单位说明，才组合成完整单位。例子是实际打印的`美元`和`百万元`组成`美元百万元`；数值17保持17，不乘百万。`qualifier_compositions.unit.components`保留两个原字面和两个来源。完整`美元百万元`与冲突的`人民币`不会通过组合被修正。该机制有独立正反例，但没有被冒充为上述真实样本的输出改善。

## 顺丰：五个业务要求及其候选范围

本版已重新核对顺丰P01-P08，其中S1/S2/S5的P01实际头链、成本范围拒绝，S4的P05及P07/P08完整检索，以及S3的P08父subtotal缺口均已复核。S3的负号、from/to期间和共同basis仍由本候选表达，但缺少第二层父组来源的对象继续被拒绝。

营收表的列说明来自expected L742，成本表来自L781，均明确`截至12月31日止年度`、`人民幣千元`以及两年度金额、占比和同比列。编译按明确列说明解释同一行的五个独立要求；下面各取一项诊断，并不缩小其他要求的正式分母。

| 项 | canonical expected实际要求 | 不携带正确值的位置查询 | 候选自己的头链、范围和限定 | 定位后观察到的实际文字及诊断 |
| --- | --- | --- | --- | --- |
| S1 | 营收表L744`營業收入合計：2024年284,420,059、100.00%；2023年258,409,403、100.00%；金額同比變動10.07%。`中的2024金额 | 营收范围，主体營業收入合計，金額，2024年，人民幣千元，年度结束口径 | S01R行头C13`營業收入合計 `；头C1`截至12月31日止年度`、C4`2024年 `、C8`金額\r\n人民幣千元`。q为`{period_basis:截至12月31日止年度,period:2024年,unit:人民幣千元,currency:人民幣}` | C14，row3/col1，为`284,420,059 `。当前P01公共轨迹B:0先核对44个候选，仅接受C14，再比较完整断言；当前营收标题和全部限定均有本组来源 |
| S2 | L745分组`按行業劃分`；L746物流及貨運代理的2023年佔營業收入比`97.18%` | 主体物流及貨運代理，行业分组，佔營業收入比，2023年，百分比及相同年度口径 | S01R行头C25`物流及貨運代理 `、分组C19`按行業劃分：`；头C1年度basis、C5`2023年`、C11`佔營業\r\n收入比`。q为`{period_basis:截至12月31日止年度,period:2023年,unit:%}`，facet为`{group:按行業劃分}` | C29，row5/col4，原值`97.18% `。当前P01公共轨迹B:8核对38个候选，仅接受C29。百分号来自本值，不从旁边金额单位推成货币；分组和列属性分别有行轴及列轴证据 |
| S3 | L748/L749要求分组`按經營分部劃分`及父记录`速運及大件業務分部`；L753冷運及醫藥的同比`-4.86%` | 冷運及醫藥，完整两层业务范围，金額同比變動，2023年至2024年，百分比及年度结束口径 | S08R行头C63`冷運及醫藥`及分组C33`按經營分部劃分:`；同比头C2、实际年份头C3/C4。两个年份头都有同一`截至12月31日止年度`祖先，因此可从候选自己的比较关系保留basis | C68，row12/col5，原值`-4.86%`，负号完整；q包含unit%、from2023、to2024及共同basis，逐项限定检查通过。但facet只证明一级分组；当前P08公共轨迹B:39核对25个候选后没有接受对象，并明确以完整group及scope后缀未证明拒绝C68。HTML没有第二层父subtotal引用，不能因附近曾出现速運及大件業務分部就猜父项 |
| S4 | L762分组`按地區劃分`；L764中國港澳台的2023金额`9,134,850` | 中國港澳台、地区分组、2023年金额角色、人民幣千元及年度结束口径 | S05R行头C133`中國港澳台`、分组C121`按地區劃分：`；头C1年度basis、C4`2023年`、C7原文`金额人民幣千元`。q完整保留period、unit、currency、basis | C136，row24/col3，为`9,134,850`。候选属性实际是简体`金额`，expected列名是`金額`；本版B以共用的有限完整属性角色对应核对，再凭自己的行头、分组、期间、单位和范围定位。T继续保留原字面，不能用数值去定位。表前未绑定的四个金额字面保持额外未裁定内容，不抢该命名记录身份 |
| S5 | 成本表L784分组`按行業劃分`；L785物流及貨運代理的2024金额`238,694,175` | 成本范围，物流及貨運代理、行业分组、金額、2024年、人民幣千元及年度结束口径 | S01C前有实际`#/documents/0/document/texts/13`标题`營業成本`，本表另打印`佔營業成本比`列；这与S01R的`營業收入`及`佔營業收入比`不同。行头C43、分组C37、年度头C4、金额头C14、单位头C20/C26均保留 | C44，row8/col1，为`238,694,175 `。当前P01公共轨迹B:100核对44个候选，仅接受C44；另一营收表C26虽有同主体、同2024年度、同币种、单位和年度basis，仍以scope冲突拒绝，不能借随后出现的成本标题。比较限定是该字段的2024期间，不制造同比要求；重复单位头不生成额外业务题 |

S3单独暴露了一个软件补读问题：此前读取器已经依据同一表的两年度头解释同比from/to，却没有读取这两个年度共有的basis。现只在两个实际期间源都受同一个完整basis头约束时补读，并保存`comparison_period_basis`头格证据。去掉其中一个期间的覆盖就不会补。这个修复没有恢复缺少源声明的父subtotal关系，也没有修复或重写`-4.86%`。

S4当前保存诊断来自完整公共入口`compile_expected → read_saved_native → read_candidate → grade_layers`，本次只读其轨迹，没有重新运行评分。检索前固定主体`中國港澳台`、属性`金額`、年度`2023年`、分组`按地區劃分`、单位`人民幣千元`、币种`人民幣`、年度口径`截至12月31日止年度`和范围`財務回顧 > 營業收入`；查询不携带`9,134,850`。P05的B:87保留38条文字命中及38个候选，逐项核对后只接受实际C136，另37项均保留主体、属性、候选上下文、scope、group及全部四个qualifier的核对和拒绝理由，详见[当前P05样本完整检索轨迹](../runs/lite/diagnosis/three-layer-current/private/scores/P05/quality800-r1/sf-revenue-operating-cost-tables-p035-036.json)。保留对象自己的行头是C133，分组是C121，期间、口径和单位头分别为C4、C1、C7；没有按相同数值从别处挑位置。此处C136属于P05的row24/col3；本轮另核的P07/P08 native各为75条文字命中、50个候选，分别拒绝49项后只接受各自row23/col3的C132，不能混用格号或候选数。P07对应`#/pages/0/raw/blocks/6/content/0`，P08对应`#/pages/0/raw/6`，各自完整限定和范围均来自自己的保存来源。

这次软件读取保留实际的`金额/金額`字面区别：B的本版S4轨迹明确记录`recall=declared_business_role_equivalence`，T中C136的金额标签`bounded_alias`明确来自C7，其`text=金额`、原格`cell_text_span=[0,2]`，没有改成`金額`或凭expected增加容量。候选自己的三个相邻同级标题`管理層討論與分析`、`財務回顧`、`營業收入`及原位置形成有界来源证据，公共范围核对据此确认当前表属于`財務回顧 > 營業收入`。独立反例同时要求缺父标题、未知同级标题隔断、North与South的同名叶范围及父项直接事实与子项事实不能互借；明确分组必须有本对象自己的行轴来源。该轨迹记录的是未获正式评测冻结的开发读取行为，没有发布样本或管线成绩，也没有候选字节改写、输出改善或语料判断。

S1/S2/S5的本版公共轨迹见[当前P01样本记录](../runs/lite/diagnosis/three-layer-current/private/scores/P01/quality800-r1/sf-revenue-operating-cost-tables-p035-036.json)，S3见[当前P08样本记录](../runs/lite/diagnosis/three-layer-current/private/scores/P08/quality800-r1/sf-revenue-operating-cost-tables-p035-036.json)。本轮重新核对仍保留S3父subtotal来源不足的拒绝，以及S5成本C44独立定位、营收C26范围冲突的区别。这些局部已定位或拒绝的要求不消除各组其余软件blocker，也不构成完整表或样本的质量成绩。

## 未裁定内容和候选歧义的具体边界

华为P03的双货币头为H03 C6，位于row1/col1、colspan2。其候选歧义影响rows2-12、cols1-2的22个数据对象，每个issue保留实际数据源、这个头格ID及原印备选单位；其他明确货币列不因此成为软件失败。百分比值自己的`%`仍是明确证据，未确定的是美元/人民币列身份。正式程序应对所需绑定不能成立的要求保留分母判错，不能向expected索取映射，也不能用全表软件unsupported掩盖候选自身的歧义。

顺丰P05在第一个命名数据行前保存了row3的四个字面：col1`284,420,059`、col2`100.00%`、col3`258,409,403`、col4`100.00%`，路径依次为S05R C9-C12。它们没有独立记录标签，不是下一行的表头，也不能按值与營業收入合計相同就认领该记录。本组后续完整表头、命名行和分组自有来源，故四格分类为`unadjudicated_extra_content`并保留到文字诊断，其他命名记录继续暴露；没有称为幻觉，也没有静默删除这些字面。

真正未能读取已有明确表达的情况继续分类为`software_unsupported`并阻止正式发布。独立反例分别检查：单位歧义只影响其源头覆盖的数据对象；明确拆出两个单位格后歧义消失而数据位置和值不变；额外数字行补上实际记录名后成为独立record；未知文字范围不能被统一改名为额外数字内容。分类依据是实际头链、对象和范围证据，不是为了发布成绩修改原因名。

## 原格padding导致的来源跨度缺陷

一次完整诊断暴露了三个读取运行时失败。原生格和独立保存的原字均完整，错误来自矩阵读取器先对数值格去首尾空白，再把去空白字串的局部跨度直接挂回原格。`scalar_evidence`据原格切片拒绝这些声明是正确行为，不能放宽guard、改错误理由或修改候选以绕过。下列跨度均为原格局部的半开区间；引号内空格属于实际原字。

| 保存样本 / 管线 | 实际格来源 | 原raw字面 | 旧value span → 新value span | 旧unit span → 新unit span | 旧错误声明数 / 修后通过的声明标量数 |
| --- | --- | --- | --- | --- | --- |
| `huawei-statements-p068-070` / P02 | `#/documents/0/document/tables/0/data/table_cells/74`，page1、row18/col2 | `" (597) "` | `[0,5]` → `[1,6]`，值仍为`(597)` | 本格无inline unit | 1 / 95 |
| `nvidia-management-estimates-ratio-table-p128-132` / P01 | `#/documents/0/document/tables/0/data/table_cells/14`，page3、row4/col2 | `" 72.7 % "` | `[0,4]` → `[1,5]`，值仍为`72.7` | `[5,6]` → `[6,7]`，单位仍为`%` | 17 / 40 |
| `nvidia-management-estimates-ratio-table-p128-132` / P02 | `#/documents/0/document/tables/0/data/table_cells/14`，page3、row4/col2 | `" 75.0 % "` | `[0,4]` → `[1,5]`，值仍为`75.0` | `[5,6]` → `[6,7]`，单位仍为`%` | 15 / 42 |

定位该缺陷的定向来源检查记录了三个case合计33个旧错误来源声明；修后95+40+42共177个已声明标量通过原来源guard。矩阵读取改为直接把原格字面交给统一measurement helper，数值、单位、币种及缺值单位分别保留原格局部跨度和来源绝对跨度；原raw、金额字形、数量级、百分号及候选字节不变。该修复不按公司、文件名或管线身份选择读取规则。

[独立原跨度反例](../../tests/unit/test_three_layer_matrix_raw_spans.py)使用手写原字、值、单位和跨度，旧版9项中7项失败、2项通过；修后9项均通过。它包括括号数、分离百分号、tab和首尾空白、非零来源偏移、typed候选入口，以及guard继续拒绝旧去空白跨度的负例；正确跨度不从被测编译器生成。

当前软件的完整只读链`read_expected → native_observation(analysis=None) → grade_expected`已另行完成，这三个本版保存诊断文件也已写出；本轮逐份读取并确认`status=completed`，没有上述来源异常或`saved_reader_or_grader_failure`。当前`outcomes`记录条数为：华为P02共755条（T452、L229、B74），NVIDIA P01和P02各426条（T154、L243、B29），分别见[华为P02](../runs/lite/diagnosis/three-layer-current/private/scores/P02/quality800-r1/huawei-statements-p068-070.json)、[NVIDIA P01](../runs/lite/diagnosis/three-layer-current/private/scores/P01/quality800-r1/nvidia-management-estimates-ratio-table-p128-132.json)和[NVIDIA P02](../runs/lite/diagnosis/three-layer-current/private/scores/P02/quality800-r1/nvidia-management-estimates-ratio-table-p128-132.json)。755/426是逐层outcome行数，177是前述定向来源校验对象数量，均不是质量分或完整语义覆盖证明；三个case仍有未支持范围，主分和分子继续撤回，不从这里推导全量完成或冻结。

## 本轮诊断的实际结论

这十条文字诊断发现并验证了单位包装词法补读、正交currency/scale组合、同比共同basis读取，以及S4完整公共入口对有限属性角色对应和有来源范围的实际读取。P02候选绑定冲突和年度截断、P04单位来源缺失、P03币种列歧义及P08父subtotal关系不足仍有明确证据；S4读取成功不消除这些其他缺口。没有发布T/L/B成绩，没有用相同数值代替身份和位置确认，也没有把这些例子或格数当成完整expected覆盖证明。正式重评、覆盖、报告和暂停状态仍由[评测索引](../reports/README.md)维护。
