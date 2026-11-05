# 三层评测的保存格式与文字诊断

本记录保留现有选择声明、canonical expected文字、保存native和实际service Markdown可定位的软件缺陷例子，不保留已删除评分派生产物的版本身份、检索计数或局部判定。没有读取PDF、图片、文字层或OCR，没有推理、服务操作、候选或参考改写。正式状态由[评测索引](../reports/README.md)维护；本页不声明当前版本已完成真实样本验收。

## 保存格式与证据边界

原生格式与适配职责由[管线文档](../../docs/pipelines/README.md)维护。保存输出可以是Docling引用图及typed cells、Paddle parsing_res_list、GLM json_result、DocVortex typed容器或视觉SDK ContentBlock[]，不能用同一HTML换管线标签代替真实格式读取。原始run.json、observation、正文与计时应分别保全，读取器不能依赖expected为候选补答案。

[独立格式反例](../../tests/unit/test_three_layer_native_formats.py)固定了原字、原行列、头格角色、引用、GLM主视图与审计视图隔离、typed父子以及空图片邻居等软件边界。明确thead、th/scope、ARIA及headers声明可作为候选证据；首行td、等列数或相邻格不能自动成为表头。合法数据格没有额外HTML id时，不能因此丢掉自己已有的headers声明；来源路径也不等于跨格式稳定业务身份。这些是读取要求，不能代替真实选段完整验证。

## 日期时间与网址不能按内部标点再次拆值

`nvidia-meeting-notice-toc-p015-016`的现有选段是源页15-16，对应canonical `complex-nvidia-2025-annual/expected.md` L361-390及L392-441。L363打印`Date and time: Wednesday, June 25, 2025 at 9:00 a.m. Pacific Time`；L364打印`Location: Virtually at www.virtualshareholdermeeting.com/NVDA2025`。

曾出现的错误是把时间内部冒号再当字段分隔，只留下`00 a.m. Pacific Time`，或把网址数字尾部2025单独当值。这是解释器损坏完整值的缺陷，不能称作候选漏字。

| 保存候选入口 | 日期时间与地点原字位置 |
| --- | --- |
| P03 native.json | `#/pages/0/raw/res/parsing_res_list/2`及`/3` |
| P05 native.json | `#/pages/0/raw/json_result/0/1`及`/2` |
| P07 native.json | `#/pages/0/raw/blocks/3`及`/4` |
| P08 native.json | `#/pages/0/raw/3`及`/4` |
| P07 baseline/current实际final.md | L9及L11 |
| P08 baseline/current实际final.md | L13及L15 |

上述native文件位于`benchmark/runs/lite/artifacts/Pxx/measured-quality800-r1/nvidia-meeting-notice-toc-p015-016/native.json`；service正文位于各自`benchmark/runs/lite/service/baseline或current/p07或p08/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/final.md`。这些位置保存完整日期时间及地点文字，不证明其他字段或整篇转换没有损失。

同样本P01的`#/documents/0/document/texts/1`是`Date and time:`、`/texts/2`是`Location:`、`/texts/3`是完整日期时间、`/texts/4`是完整地点。两个键先于两个值，文字存在不能证明键值关系；不能把紧邻下一块自动当值，也不能按正确值挑配对。标签与正文交错的另一类原生证据见[保存正文归因](service-prose-assembly.md)。

## 多轴表头不能缩成数字存在性

`huawei-financial-summary-p007`的canonical范围是L158-240。L161的销售收入要求完整`2024年，美元百万元：118,162`，L162另要求人民币百万元。P01 `#/documents/0/document/tables/0`保存2024跨列头、独立货币单位头和销售收入行头；P03同表将两种完整货币单位印在一个colspan=2格中。两者的绑定证据不同，不能靠数值一致抹平差别。

`sf-revenue-operating-cost-tables-p035-036`对应expected L736-765及L767-799。候选打印年度结束口径、两年度、金额/比例列，以及行业、经营分部、地区等行分组。营收与成本还有各自实际标题，不能从比例分母或相同金额独自推定金额所属业务表。具体原格、单位缺口、截断年度、双币种歧义及额外未命名数值见[矩阵诊断](three-layer-matrix-readback.md)，实际service路径表达见[表头路径诊断](service-header-path-readback.md)。

完整格文字、来源跨度和数值存在只能证明文字来自哪里；指标、年度、单位、币种、分组、父记录和业务范围仍需分别证明。来源切片不符必须阻断，不能修改候选或放松guard。候选额外未绑定数字与reference尚未解释要求也须分开，见[裸数字边界](extra-numeric-readback.md)。

## 要求编译器自身的来源与枚举缺陷

要求图的严格校验曾检出已有期间、币种、否定与条件缺少自己的来源。其中Huawei紧凑年度叶项没有承接打印年度的跨度，SF列说明中的单位派生了币种却未保存币种子跨度。另一个Huawei财表错误将“人民币”的来源指向数值开头，而非L1792打印的单位声明。修复只承接实际声明、数值子串和操作符的来源，不新增币种、期间或业务答案。内联比例单位与列说明的真实重述分别保留，只有同一对象、同一单位的有限别名可以共享投影，错单位不能折叠。

NVIDIA `complex-nvidia-2025-annual/expected.md` L3762的枚举读取曾把前面的OR标签用于后续只有逗号的范围，随后又被较弱的modal读取当作一个大业务值。Pingan `complex-pingan-2024-annual/expected.md` L456中的“or more”也不能拆成两个OR对象。读取器现在要求实际连接词的来源与枚举边界一致；未知尾部与数量阈值保留整句B/L未决，公共入口不能用另一条较弱规则抹掉该未决。修复后的实际文字范围已经检查，未凭其他行仍有阻塞就宣称这些范围已修复。

这些是expected派生要求模型的软件缺陷，不是候选错误或语料错误。来源校验通过仍不能证明复杂正文已完整解释，也不构成任何后处理的交付增益。

## 输入边界与未解释关系

受控输入边界反例中，报告标题及单位仅声明在第1页，Revenue字段仅声明在第2页；只选第2页时，不能静默把第1页单位、年度或标题变成候选必须补印的内容。上文可作有来源的非计分解释，实际单位和期间义务仍须查选中内容自己的声明。真实五例的完整选择声明与原文起首保留在[输入边界](three-layer-input-boundary.md)，不能通过软件计数消除未知范围。

目录页码、父链、跨页连接和重要业务正文同样不能以非空对象、字段数量或软件测试代替语义解释。目录实际字面及父关系边界见[目录诊断](three-layer-toc-readback.md)，业务前句被当字段范围的缺陷见[前句诊断](prose-preamble-readback.md)。读取已有明确表达失败属于软件解释缺口；候选确实缺失关系、自身歧义和额外未裁定文字须保留不同原因。局部读取或来源修复不构成完整覆盖、转换收益或正式成绩。
