# 目录保存输出的定向读回诊断

本记录仅保留未改动的expected选段和保存输出可定位的软件缺陷例子。旧评分派生记录已删除，本页不保留其软件身份、目录对象数、检索判定或完整运行断言，也不将它们改称新版本已验证。没有读取PDF、图片、文字层或OCR，没有推理、候选回放或服务操作。

## NVIDIA：页码字面不能补出目录父链

样本为`nvidia-meeting-notice-toc-p015-016`，canonical `complex-nvidia-2025-annual/expected.md`选段为L361-390及L392-441。L394是根条目DEFINITIONS、Page 3；L397是PROXY STATEMENT、Page 12；L400的Director Qualifications and Nomination of Directors、Page 17位于L397与L399 Proposal 1—Election of Directors构成的明确父链下。

保存候选包含平面Title/Page表达。以下只列自己的目录、Page声明与实际页码格，不把平面表的存在当作必需多级父链已经保留。

| 组及原始入口 | 目录与Page声明 | Director条目页码位置 |
| --- | --- | --- |
| [P01 native.json](../runs/lite/artifacts/P01/measured-quality800-r1/nvidia-meeting-notice-toc-p015-016/native.json) | `#/documents/0/document/texts/22`；表内`data/table_cells/1`为Page，另保存native document-index声明 | `#/documents/0/document/tables/0/data/table_cells/15`，row7/col1 |
| [P03 native.json](../runs/lite/artifacts/P03/measured-quality800-r1/nvidia-meeting-notice-toc-p015-016/native.json) | `#/pages/1/raw/res/parsing_res_list/0`含NVIDIA Corporation和Table of Contents；同表`cell[1]`为Page | `#/pages/1/raw/res/parsing_res_list/1/block_content::html/cell[15]`，row7/col1 |
| [P08 native.json](../runs/lite/artifacts/P08/measured-quality800-r1/nvidia-meeting-notice-toc-p015-016/native.json) | `#/pages/1/raw/1`为目录文字，`/2`为独立Page声明 | `#/pages/1/raw/3/content::html/cell[13]`，row6/col1 |
| [P07 baseline final.md](../runs/lite/service/baseline/p07/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/final.md) | L49为Table of Contents，L51为Page，表在L61-108 | GFM row7/col1 |
| [P07 current final.md](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/final.md) | 同一保存正文的上述行号和声明 | GFM row7/col1 |

Page 17确已打印，但页码是待比较内容，不能用来选择同名条目或补父。必须分别证明完整title、目录自身范围、页码slot和候选自己的parent身份；平面根声明与未证明父身份也不能混同。此处不保留旧软件对根条目或Director条目的正确/错误判定。

P01另有可独立定位的文字缺口：同表`table_cells/92`实际标题为`PPENDIX A—Amended and Restated Certificate of Incorporatio`，`table_cells/93`打印`A-1`。完整页码不能补齐标题。P03的`cell[92]/cell[93]`、P08的`cell[90]/cell[91]`及P07保存GFM的row46/col0-1可分别定位完整APPENDIX标题与A-1；它们属于各自输出，不能替P01补字。

## 华为：数字前缀不独立证明页码与父级

样本为`huawei-management-toc-p014`，canonical `complex-huawei-2024-annual/expected.md`选段为L382-403。L384是`13 愿景、使命与战略`；L387的`16 运营商市场`和L388的`21 政府和企业市场`位于L386的`16 ICT基础设施业务`之下；L401是根条目`62 财务风险管理`。这些要求不能因读取器未建立Page角色而退出。

| 组及原始入口 | 保存的对应文字位置 |
| --- | --- |
| [P01 native.json](../runs/lite/artifacts/P01/measured-quality800-r1/huawei-management-toc-p014/native.json) | `#/pages/0/raw/json_result/0/1`的文字行1、7、9、35，政府条目前缀为`21、` |
| [P03 native.json](../runs/lite/artifacts/P03/measured-quality800-r1/huawei-management-toc-p014/native.json) | `#/pages/0/raw/res/parsing_res_list/1`的文字行1-8和10-19，政府条目前缀为`21 ` |
| [P08 native.json](../runs/lite/artifacts/P08/measured-quality800-r1/huawei-management-toc-p014/native.json) | `#/pages/0/raw/1`、`/5`、`/6`、`/20` |
| [P07 baseline final.md](../runs/lite/service/baseline/p07/candidate/artifacts/quality800-r1-huawei-management-toc-p014/final.md)与[current final.md](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-huawei-management-toc-p014/final.md) | L5、11、13、39，含`21、政府和企业市场` |

这些保存文字没有随上述条目提供本次目录模块所需的明确Contents/Page轴或独立document-index schema。任务标签、文件名、重复数字前缀和expected父树不能补成候选自己的目录声明。文字存在与目录语义解释完整是两件事，不能以零个已编Page要求当作空范围通过，也不能把软件解释缺口改称候选零分。

## 独立软件边界

[父身份受控反例](../../tests/unit/test_toc_parentage_contract.py)区分明确平面文字、Title/Page schema、实际目录根引用、命名父引用和破损显式引用。unknown空path不证明root；显式父引用破损不能回退平面schema；只有SDK明确body路径或结构容器角色能排除非业务父对象。实际标题、Page字面及来源仍须保留，完整关系尚未解释时应保留未决。本记录不提供当前软件版本的真实样本验收或全范围运行状态。
