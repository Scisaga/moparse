# Service表头路径表达的读回缺陷

本记录只保留未改动的native结构与实际service Markdown中可定位的表达，以及由它们暴露的读取缺陷。已删除的评分JSON、软件身份、检索计数和局部T/L/B判定不再作为证据；本页不提供成绩、完整覆盖或转换收益。没有读取PDF、图片、文字层或OCR，没有新推理、回放或服务操作。

## 顺丰：完整路径不能整体当成属性名

样本为`sf-revenue-operating-cost-tables-p035-036`。下列保存正文均在L89打印同一业务记录：

| 组 | 实际文件 |
| --- | --- |
| P07 baseline | [final.md](../runs/lite/service/baseline/p07/candidate/artifacts/quality800-r1-sf-revenue-operating-cost-tables-p035-036/final.md) |
| P07 current | [final.md](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-sf-revenue-operating-cost-tables-p035-036/final.md) |
| P08 baseline | [final.md](../runs/lite/service/baseline/p08/candidate/artifacts/quality800-r1-sf-revenue-operating-cost-tables-p035-036/final.md) |
| P08 current | [final.md](../runs/lite/service/current/p08/candidate/artifacts/quality800-r1-sf-revenue-operating-cost-tables-p035-036/final.md) |

原句片段是`按地區劃分: / 中國港澳台；截至12月31日止年度 / 2024年 / 金額人民幣千元：9,467,291`及`截至12月31日止年度 / 2023年 / 金額人民幣千元：9,134,850`。同一行还打印两个年度的佔營業收入比和`金額同比變動：3.64%`。这些字面本身没有在最终正文中丢失。

曾出现的读取错误是把`按地區劃分`当成普通属性，把`/ 中國港澳台`当值，再将`截至12月31日止年度 / 2023年 / 金額人民幣千元`整体当作金额属性，未承接其中的主体、期间、单位和币种。不能把这类读取失败称作服务转换删除，也不能从expected补回缺少的角色。

同一候选自己的原生表可用于区分实际数据对象和表头来源：

| native文件 | 数据源 | 本格自己的行列来源 |
| --- | --- | --- |
| [P07 native.json](../runs/lite/artifacts/P07/measured-quality800-r1/sf-revenue-operating-cost-tables-p035-036/native.json) | `#/pages/0/raw/blocks/6/content/0/content::html/cell[132]`，row23/col3 | 同表`cell[129]`为中國港澳台，`cell[117]`为按地區劃分:；`cell[1]/[4]/[7]`打印截至12月31日止年度、2023年、金額人民幣千元 |
| [P08 native.json](../runs/lite/artifacts/P08/measured-quality800-r1/sf-revenue-operating-cost-tables-p035-036/native.json) | `#/pages/0/raw/6/content::html/cell[132]`，row23/col3 | 同表`cell[129]`、`cell[117]`及`cell[1]/[4]/[7]`分别保存上述行、组和列路径 |

[矩阵诊断](three-layer-matrix-readback.md)中的C136属于P05另一序列化：`#/pages/0/raw/json_result/0/4/content::html/cell[136]`，row24/col3，行头C133、组头C121、列头C1/C4/C7。局部格号不是跨格式身份，不能按金额相同选格。

L89原始列表正文去掉`- `后，`9,134,850`位于`[120,129]`，年度口径、年份、单位和币种字面分别在`[90,101]`、`[104,109]`、`[114,119]`和`[114,117]`。这些是实际文字定位，不能代替业务关系验收。同行同比没有明确打印from/to角色，不能仅按相邻两个年度猜起止期。

## 华为：行标签与年度单位路径承担不同角色

`huawei-financial-summary-p007`的P07/P08 baseline/current正文L13均打印`销售收入；2024 / (美元百万元)：118,162；2024 / (人民币百万元)：862,072`，之后继续其他年度。实际入口包括[P07 current final.md](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-huawei-financial-summary-p007/final.md)。

这里打印的是销售收入行指标，列路径只有年份和单位，没有独立的金额列标签。曾出现的错误是将`销售收入；2024 /`当属性，把后续各期吞入同一个值，仅留下首个美元单位。不能机械套用顺丰的“主体+金额列”语义，也不能从expected补出一个未打印的主体或金额列。

| L13实际字面 | 去掉列表标记后的局部跨度 |
| --- | --- |
| 销售收入 | `[0,4]` |
| 第一列年度2024、单位美元百万元、币种美元、值118,162 | `[5,9]`、`[13,18]`、`[13,15]`、`[20,27]` |
| 第二列年度2024、单位人民币百万元、币种人民币、值862,072 | `[28,32]`、`[36,42]`、`[36,39]`、`[44,51]` |

后续年度的`（单位：(人民币百万元)）`还暴露了后置单位与嵌套括号读取边界。单位必须完整打印且括号匹配；未知尾部、冲突单位或未知字段应保留未决，不能跨列借首个单位。文字层保留实际`2024`，不能因业务等价而补成候选未打印的`2024年`。

## 软件验证边界

[路径模块](../../moparse_eval/header_path_requirements.py)及[独立受控反例](../../tests/unit/test_header_path_requirements.py)承接这类路径、后置单位和冲突边界。后续共同评分仍须先证明候选自己的主体、完整属性、表范围、分组、期间、币种和单位，再比较值，并独立复核全文文字来源与关系；不能以旧局部定位成功解除其他未解释范围，也不能把评分读取修复算成交付内容增加。本记录不声明当前版本已完成这些真实样本的验收。
