# 三层评测的保存格式与文字诊断

本记录只读取现有选段声明、canonical expected文字、保存的native.json及observation.json。没有读取PDF、图片、文字层或OCR，没有模型执行、服务操作、候选改写或参考复核。本记录用于发现测量软件问题，不发布人工成绩，也不恢复此前成绩。正式成绩和完整覆盖状态由[评测索引](../reports/README.md)维护。

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

同样本P01的`#/documents/0/document/texts/1`为`Date and time:`，`/texts/2`为`Location:`，`/texts/3`为完整日期时间，`/texts/4`为完整地点。文字层可保全这些字面；关系层仍需证明键和值的联系，不能只把相邻下一个块当作值，因为这里两个键先于两个值。该入口须保留真实顺序、父引用和已有关系，并据候选证据判断，不能按expected的正确值挑配对。

## 真实矩阵及单位读取范围

`huawei-financial-summary-p007`源选段仅第7页，canonical expected为L158-240。销售收入在L161要求`2024年，美元百万元：118,162`，在L162要求`2024年，人民币百万元：862,072`。P01的`#/documents/0/document/tables/0`保留了明确column_header和row_header，首行2024跨两列，第二行分别是美元和人民币单位，销售收入为第三行行头。该矩阵必须按两个轴及跨度读取，不能以数值相同推定单位或期间。

P03同表为`#/pages/0/raw/res/parsing_res_list/2`，两种货币在一个colspan=2格中打印为`（美元百万元）（人民币百万元）`；P05的`#/pages/0/raw/json_result/0/1`、P07的`#/pages/0/raw/blocks/2/content/0`和P08的`#/pages/0/raw/2`则分别打印两个单位格。这些HTML的表头均以td表示。读取软件只支持th时，不能把已存在的文字、跨度和表格表达全部算作候选缺失；同时，一格中的两个单位如何分配必须有候选自己的明确证据，不能用expected或数值反选。支持边界须通过独立合成正反例和完整检索轨迹验证。

`sf-revenue-operating-cost-tables-p035-036`源选段为35和36页，对应expected L736-765及L767-799。expected L744的原文为`營業收入合計：2024年284,420,059、100.00%；2023年258,409,403、100.00%；金額同比變動10.07%。`，L742明确期间、人民幣千元及金额/占比列说明。候选保留三层列头`截至12月31日止年度`、`2024年/2023年`、`金額人民幣千元/佔營業收入比`，并在行轴另有`按行業劃分`、`按經營分部劃分`和`按地理區域劃分`分组。P01来源为`#/documents/0/document/tables/0`，P03为`#/pages/0/raw/res/parsing_res_list/6`，P05为`#/pages/0/raw/json_result/0/4`，P07为`#/pages/0/raw/blocks/6/content/0`，P08为`#/pages/0/raw/6`。参考列表层级不能直接编成候选同一行路径。

上述P05保存表格在完整`營業收入合計`数据行前另有一行`284,420,059 / 100.00% / 258,409,403 / 100.00%`。这是可观察的重复文字，不凭此判断内部成因。T须保留候选出现次数的诊断，L/B分别检查对象与关系，不能只因有一个正确值便忽略另一位置，也不能把重复文字自动称为幻觉。

## 输入边界的最小复现

纯合成文档L1为`# 2024年报告`，L3为`单位：万元`，两者仅映射到第1页；L5为`- Revenue: 17`，仅映射到第2页。只选第2页时，旧`read_expected`仍返回`context=[2024年报告]`、record.unit=`万元`、field.period=`2024年`。原因是更新标题和限定状态发生在选段covering检查之前。

这些上文可以帮助解释参考，但没有证明候选实际输入包含它们。新读取器保留选段外上下文的实际范围，新核心将其标为`input_scope_context`并阻止正式发布，不再借旧record静默继承单位和期间。真实华为样本首个选中标题`五年财务概要`的旧context含选段外的完整报告根标题；此处只记录软件继承范围，不据此判定实际PDF是否包含任何标题。

## 新核心仍未支持的测量范围

下列项目尚缺可靠的对应和判定实现。它们是测量软件阻塞，不能作为候选零分、N/A或删目标的依据，也不能仅改原因名称解除。

| 范围 | 最小证据与影响 | 尚缺条件 |
| --- | --- | --- |
| 多层列头、跨列单位和分组矩阵 | 华为保存原生的2024跨两列、美元/RMB第二层单位；顺丰的截至年度/年度/金额及占比三层列头与行分组 | 用候选自己的完整头路径、跨度、单位及分组建立两轴关系；当前以`spanning_header_or_group_semantics_unsupported`、`compound_header_semantics_unsupported`等阻断 |
| 全td表格的语义角色 | 上述HTML保存了完整文字及跨度，但没有th、thead或ARIA角色 | 统一且独立验证的数据角色证明，不能依赖唯一邻格或expected选方向；当前`untyped_grid_semantics`阻断，文字仍保全 |
| 紧凑五指标要求 | 顺丰expected L742给出列说明，L744把两个年度的金额/占比及同比合写 | 将五个独立重要要求与明确限定完整展开，保持合写/拆写权重一致；当前`compact_multi_metric_requirement_unsupported`阻断，不能把整串压成一道题 |
| L的独立对象端点 | 保留字面而只交换明确headers或父引用，值本身不能命名其对象 | 可跨合法序列化对应的端点身份；有headers而缺少独立对象身份时须保留具体不支持状态，不能把来源路径等同于跨格式业务身份 |
| 标题、正文及列表的范围关系 | NVIDIA多个键先于多个值；真实格式存在类型标题和跨块正文，参考还有选段外根标题 | 读取候选自己的明确关系和连续范围，验证排除理由；不能只拿相邻块或其他章节同值补答 |
| 必要跨页续接 | 原生读取可保留已有continues/merge_prev声明，但新关系解释未完成端点、范围及必要连接的统一对应 | 完整跨页正例与缺失连接反例，禁止凭相邻、等列数或相似文字合并；当前识别到续表表达以`cross_page_relation_interpretation_unsupported`阻断 |
| 重要业务正文和逻辑描述 | NVIDIA的重要普通业务句、顺丰带条件的业务叙述不只是可直接冒号拆分的字段 | 独立固定角色与要求、条件和否定解释及等价判定；当前未支持表达显式阻断，不能把全部句子随意当指标 |

这些限制由实际文字诊断和独立受控例子暴露。新三层评分入口、16进程编排及正式报告入口均必须保留阻塞；本记录不引用未完成的全量诊断数字或任何暂算成绩。

正式分数解锁前，仍须证明以上不同形态在统一程序中的正确要求集合、候选原位置、允许等价及排除理由，覆盖已判对、已判错及未定位项。格式测试通过、原始执行完成、目标数量齐全和本诊断记录本身均不构成该证明。
