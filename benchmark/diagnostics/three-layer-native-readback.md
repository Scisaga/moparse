# 三层评测的保存格式与文字诊断

本记录只读取现有选段声明、canonical expected文字、保存的native.json及observation.json。没有读取PDF、图片、文字层或OCR，没有模型执行、服务操作、候选改写或参考复核。本记录用于发现测量软件问题，不发布人工成绩，也不恢复此前成绩。正式成绩和完整覆盖状态由[评测索引](../reports/README.md)维护；矩阵、目录和输入边界的具体证据分别由[矩阵文字诊断](three-layer-matrix-readback.md)、[目录文字诊断](three-layer-toc-readback.md)及[选段输入边界](three-layer-input-boundary.md)维护。以下区分已实现的有限读取与仍未成立的真实绑定，不把早期不支持状态沿用为当前全部范围。

## 入口与独立格式测试

保存原生入口为`expected_evaluation.native_observation(run, case)`，调用`read_saved_native(native, observation)`按每页声明的branch进入`adapters.READERS`，再调用`read_native_relations`。两个读取函数都不接收expected。保存原始时长与资源观测不因分析读取而改变。`run.json`中`phase=measured`且`suite=quality800`的声明确定本次原生组；P07/P08的实际正文从各自`service/baseline/`和`service/current/`的run.json指向final.md读取，不能用内部对象替代正文。

[独立格式测试](../../tests/unit/test_three_layer_native_formats.py)分别使用五种实际保存载体的合成内容：Docling引用图及typed table cells、Paddle的res.parsing_res_list、GLM的json_result页面区域列表、DocVortex typed容器及table_body/caption、视觉SDK ContentBlock[]。测试明确断言6个格的文字、原始行列、头格角色、唯一来源、GLM主视图与审计视图隔离、typed容器父子和空图片邻居保全。五个入口均贯通新三层核心：Name=Delta、Revenue=17、Profit=5的角色与要求固定，另将各自实际原生载体的Profit改为6，断言仅对应B项错误。这些测试证明限定的读取行为，不证明五种格式的全部业务表达均能评分，也不替代管线标签公平测试或真实样本完整链路诊断。

`adapters._HTMLCells`现忠实读取thead、th/scope、td的ARIA columnheader/rowheader及headers引用，保留原始属性和声明来源，不推断未声明的首行td为表头。Paddle实际载体链的Status/Ready双列表头、Blocked/No数据行反例已验证：Status=Ready不能通过，Status=Blocked可以读取。合法数据格没有额外HTML id时，B仍可依据自己的headers引用读取值；L要求独立对象身份的场景另有支持边界，不要求候选为了评分器增加id。

## 已复现的参考解释问题

`nvidia-meeting-notice-toc-p015-016`现有选段声明为源页15和16，对应canonical expected的L361-390和L392-441。实际文字为：

| expected位置 | 实际要求 | 旧record解释的可观察错误 |
| --- | --- | --- |
| `complex-nvidia-2025-annual/expected.md:L363` | `Date and time: Wednesday, June 25, 2025 at 9:00 a.m. Pacific Time` | 把`Wednesday, June 25, 2025 at 9`当列属性，值只剩`00 a.m. Pacific Time` |
| 同文件L364 | `Location: Virtually at www.virtualshareholdermeeting.com/NVDA2025` | 把网址前缀当列属性，值只剩`2025` |
| 同文件L368 | `Ratification of the selection of PricewaterhouseCoopers LLP as our independent registered public accounting firm for fiscal year 2026` | 把整句前缀编成列属性，值只剩年度`2026` |

上述行为来自已经删除的旧record解释逻辑对外层值再次拆分及隐式数字后缀匹配。新核心重新解释完整文字，实读本样本后，Date and time的值保持`Wednesday, June 25, 2025 at 9:00 a.m. Pacific Time`，Location的值保持完整网址；没有再将时间内部冒号或网址数字编成字段层级。这是参考解释修复，不是候选输出改善；该样本其他重要业务句和关系尚未全部可靠解释，不能据此发布成绩。

对应实际候选已保存完整日期时间和地点：P03位于`#/pages/0/raw/res/parsing_res_list/2`及`/3`，P05位于`#/pages/0/raw/json_result/0/1`及`/2`，P07位于`#/pages/0/raw/blocks/3`及`/4`，P08位于`#/pages/0/raw/3`及`/4`。以上日期时间文字均为`Date and time: Wednesday, June 25, 2025 at 9:00 a.m. Pacific Time`，地点均为`Location: Virtually at www.virtualshareholdermeeting.com/NVDA2025`。这些原文足以复现参考编译缺陷，不能将错误拆分产生的比较失败称为解析缺失。

当前软件`21ebba9c70e11bdae557c94cca4686df99e6432228a545d24354c93ec57d6f63`的四组service轨迹及其实际final.md已重新读取：P07两组日期/地点仍在L9/L11，P08两组仍在L13/L15；四组编译要求均保留完整Date and time和Location值，记录均撤分。此复核只支持这两项文字的解释和现存原文，不证明其他要求或整篇转换没有损失。

同样本P01的`#/documents/0/document/texts/1`为`Date and time:`，`/texts/2`为`Location:`，`/texts/3`为完整日期时间，`/texts/4`为完整地点。文字层可保全这些字面；关系层仍需证明键和值的联系，不能只把相邻下一个块当作值，因为这里两个键先于两个值。该入口须保留真实顺序、父引用和已有关系，并据候选证据判断，不能按expected的正确值挑配对。

## 真实矩阵及单位读取范围

`huawei-financial-summary-p007`源选段仅第7页，canonical expected为L158-240。销售收入在L161要求`2024年，美元百万元：118,162`，在L162要求`2024年，人民币百万元：862,072`。P01的`#/documents/0/document/tables/0`保留了明确column_header和row_header，首行2024跨两列，第二行分别是美元和人民币单位，销售收入为第三行行头。该矩阵必须按两个轴及跨度读取，不能以数值相同推定单位或期间。

P03同表为`#/pages/0/raw/res/parsing_res_list/2`，两种货币在一个colspan=2格中打印为`（美元百万元）（人民币百万元）`；P05的`#/pages/0/raw/json_result/0/1`、P07的`#/pages/0/raw/blocks/2/content/0`和P08的`#/pages/0/raw/2`则分别打印两个单位格。这些HTML的表头均以td表示。当前`matrix_evidence`已支持有明确业务轴和兼容记录的有限全td schema，并按完整头链和跨度暴露实际对象，不再因缺少th一概阻断。单格中的两个单位仍不能凭列序或正确数值分配；该样本的已读取单位、真实缺失和候选歧义见[逐项矩阵证据](three-layer-matrix-readback.md#华为五个业务要求及其候选范围)，不能把相同数值存在当作身份已确认。

`sf-revenue-operating-cost-tables-p035-036`源选段为35和36页，对应expected L736-765及L767-799。expected L744的原文为`營業收入合計：2024年284,420,059、100.00%；2023年258,409,403、100.00%；金額同比變動10.07%。`，L742明确期间、人民幣千元及金额/占比列说明。候选保留三层列头`截至12月31日止年度`、`2024年/2023年`、`金額人民幣千元/佔營業收入比`，并在行轴另有`按行業劃分`、`按經營分部劃分`和`按地理區域劃分`分组。P01来源为`#/documents/0/document/tables/0`，P03为`#/pages/0/raw/res/parsing_res_list/6`，P05为`#/pages/0/raw/json_result/0/4`，P07为`#/pages/0/raw/blocks/6/content/0`，P08为`#/pages/0/raw/6`。参考列表层级不能直接编成候选同一行路径。

上述P05保存表格在完整`營業收入合計`数据行前另有一行`284,420,059 / 100.00% / 258,409,403 / 100.00%`。这是可观察的重复文字，不凭此判断内部成因。当前矩阵读取将没有记录绑定的这四格保留为`unadjudicated_extra_content`，其他命名行继续独立读取；T保留实际字面和来源，不能把它们按正确数值认领为下一行，也不能自动称为幻觉。P01华为原生picture容器内的额外无绑定数字及reference同类要求必须继续阻断的区别，另见[裸数字证据边界](extra-numeric-readback.md)。

字段和表头的有限单位读取现共用`measurement_evidence`：`17人民币千元`中的数值仍为`17`，保留完整单位及其中明确打印的币种，不做倍率换算。`Revenue(17%)`和`Count(17人)`的括号含数量，不能被当成单位声明；身份值`17美元`保持完整，`$17`只保留自己的符号单位，不推断USD。矩阵值内的分段使用该对象自己的`value_source`及`qualifier_sources`，逐段核对实际cell文字和有限容量，来源不符时阻断而不重建答案。这些是独立受控行为，不能作为上述实际样本所有单位已可靠对应的证明。

## 输入边界的最小复现

纯合成文档L1为`# 2024年报告`，L3为`单位：万元`，两者仅映射到第1页；L5为`- Revenue: 17`，仅映射到第2页。只选第2页时，旧`read_expected`仍返回`context=[2024年报告]`、record.unit=`万元`、field.period=`2024年`。原因是更新标题和限定状态发生在选段covering检查之前。

这些上文可以帮助解释参考，但没有证明候选实际输入包含它们。新读取器保留选段外上下文的实际范围；祖先标题作为非计分解释，不要求候选补印根标题。单位和期间依赖须另查当前选中内容是否自己已有充分声明，未解除的依赖继续以`input_scope_context`阻断，不能静默继承或删题。真实华为样本首个选中标题`五年财务概要`的旧context含选段外完整报告根标题，不能仅据该根标题在context中就持续阻断局部已明确的叶要求。跨页段落只输入一侧是另一种尚未解决的问题，具体五个样本及其现有声明见[选段输入边界](three-layer-input-boundary.md)；此处不判定实际PDF是否包含任何标题或文字。

## 当前有限实现与仍缺的判定条件

下列范围已不再全部处于未实现状态。已实现的读取必须继续保留真实来源及独立对照；候选确实缺少限定、候选自身歧义、额外未裁定文字和软件无法解释已有表达须分别归因。只有最后一种或尚未解决的reference要求阻止正式发布，不能用统一软件unsupported掩盖已能读取的候选错误，也不能仅改原因名称放行未知要求。

| 范围 | 已实现的有限行为 | 仍缺的条件与实际边界 |
| --- | --- | --- |
| 多层头链、跨度、单位和分组矩阵 | `matrix_evidence`读取实际row/column角色、完整头链、跨度和分组，保持每个独立data对象；同一已证明头链中正交currency/scale字面可有源组合 | 华为已有单位来源缺失、双货币单格的`matrix_header_qualifier_ambiguous`及截断年度，不能从邻列或expected补全；候选歧义保留受影响对象和备选字面。具体区别见[矩阵诊断](three-layer-matrix-readback.md) |
| 全td数据角色 | 支持明确property/value结构，以及有实际期间/单位业务轴和兼容记录的有限全td schema | 网格及重复数字本身不证明业务角色。未建立schema时仍保留`matrix_data_roles_unproven`；字段/记录身份不明与缺少实际header引用分别保留具体原因 |
| 紧凑五指标、父指标叶及年度标量 | `compact_requirements`按明确列说明展开两个年度金额、占比和同比五项；有来源父指标可限定年度叶，T按实际对象给有限标签alias；`series_requirements`读取有明确属性的年度标量及独立原因/增减字段 | 无列说明的多值tuple、缺少指标、未知selector和未证明的比较期继续pending；不能按最大年度或数字顺序补全。plain父指标的实际行来源与主体locator需分开，不把所有父项都改成metric声明 |
| T字面与来源容量 | 完整数值、单位、币种符号和标签保留原文跨度；共享schema只按实际data对象扩展，普通重复文字不合并 | 来源跨度不匹配或投影不完整继续阻断；数量级、货币、百分比与千分比不由文本宽度或单位换算抹平。软件测试证明的是固定反例，不能替代全选段文字覆盖 |
| L独立对象和字段绑定 | `relation_correspondence`在独立对象端点已经成立时检查headers、字段和限定作用域；值错字不自动抹掉绑定，跨表示不要求复制HTML id | 仍须候选自己证明端点、必要父范围和引用方向；存在headers文字不等于对象已定位，来源路径也不等于跨格式业务身份。未能解释的native引用继续保留软件阻塞 |
| 标题、普通正文和列表范围 | 读取候选自身标题stream、实际父引用及连续文字片段；只在完整范围检查通过时对应另一合法表示 | NVIDIA多个键先于多个值，不能邻接补配；未知同级标题、另一分组或父项直接事实不能借给子项。原生已交错的标签也不能在读取器里按expected重排，见[保存正文归因](service-prose-assembly.md) |
| 目录条目与父路径 | `toc_evidence`已接公共入口，支持明确Contents/目录、Title+Page schema及native document_index；页码slot、完整条目和候选实际父路径分别保留 | 无目录角色不能仅凭尾部数字猜目录；条目和页码读到也不证明parentage。NVIDIA未声明的父链、华为无明确目录schema等边界见[目录文字诊断](three-layer-toc-readback.md)，零个已编Page不等于空验收 |
| 必要跨页续接 | 读取器保留已保存的continues/merge_prev声明及来源 | 尚未完成所有必要连接的端点、范围和跨表示对应。识别到无法解释的续表表达仍以`cross_page_relation_interpretation_unsupported`阻断，禁止仅凭相邻、等列数或相似文字合并 |
| 重要业务正文和逻辑描述 | 支持有限明确实体描述和subject/action/modal语法，保留条件、否定、例外及purpose，并将L作用域与B内容比较分开 | 复杂复句、未证明粒度的AND动作及其他未解释业务叙述仍须软件阻断。没有业务属性的候选额外裸数可单独保留，但`Revenue increased 17`等完整未读业务句不能被改称额外裸数放行 |

这些实现和限制由实际文字诊断及独立受控反例分别记录。新三层评分入口、16进程编排及正式报告入口仍须保留真实软件阻塞；局部读取成功不解除[输入可答范围](three-layer-input-boundary.md)或其他未解释要求。本记录不引用未完成的全量诊断数字或任何暂算成绩，也不把旧版保存诊断当作当前代码已经冻结的证据。

正式分数解锁前，仍须在同一冻结版本证明授权范围内的完整要求、候选原位置、允许等价及逐项排除理由，覆盖已读、未读、定位失败和软件无法解释的范围。受控测试、原始执行、目标数量、报告生成及本记录本身均不构成完整语义验证。
