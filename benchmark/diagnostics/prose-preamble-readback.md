# 业务前句被误作字段范围的读取诊断

本记录只读保存输出及expected文字，记录要求编译和来源使用缺陷及当前失败关闭行为，不提供质量成绩。没有打开PDF、图片、文字层或OCR，没有模型、候选回放、服务操作或候选改写。验收定义由[评测任务](../evaluation-tasks.md#three-layer-evaluation)维护，最终软件身份以[当前诊断索引](../runs/lite/diagnosis/three-layer-current/index.json)为准。

实际例子为`alibaba-shareholder-letter-p004-005`。canonical expected位于`pdf_sample/parsing/expected/complex-alibaba-2025-annual/expected.md`第94行；[P05当前轨迹](../runs/lite/diagnosis/three-layer-current/private/scores/P05/quality800-r1/alibaba-shareholder-letter-p004-005.json)保留同源要求解释与pending。以下范围均为原段零起点、左闭右开文字跨度，不是PDF坐标。

| 原文位置 | 实际业务内容 | 修复前错误行为 |
| --- | --- | --- |
| L94首句`[0,209]` | 陈述正在增加投资，并枚举AI与云基础设施、基础模型与原生应用、既有业务AI转型三个方向 | T保留完整首句；该业务内容没有对应B要求或同源未支持声明 |
| L94后句`[210,386]` | 陈述未来投资将超过此前投资 | 仅此句生成一项`description`，属性为`exceed`；B来源`[210,385]`排除句末标点 |
| 首句前缀`[0,72]` | `To realize this vision, we are ramping up investments in three key areas` | 被标为`printed_field_label`，进入后句检索的`scope` |

P05候选自己的实际段落位于`#/pages/1/raw/json_result/0/7`。字段来源证明正确读到了这段原文的冒号前缀，但存在字面前缀不能证明它是业务字段标签。该前缀本身已经陈述被测业务内容，将其用于定位后句会把答案内容变成范围身份，同时让前句枚举退出B。该缺陷发生时，expected L94及候选该块均没有本地blocker；其他位置阻止整条记录发布，也不能证明本段已经解释完整。

独立反例固定在[公共入口测试](../../tests/unit/test_three_layer_prose_contract.py)的`test_business_preamble_and_enumeration_cannot_become_the_later_statement_field_identity`，使用以下三个发明场景，不含实际公司、文件名或参考答案特例。

| 通用场景 | 必须承接的前句内容 | 后续明确句 |
| --- | --- | --- |
| 扩展三类运营 | 货运、快递和仓储 | 资本配置将超过此前支出 |
| 优先三个项目 | 太阳能发电、储能和电网控制 | 委员会应审查资金 |
| 投资三个地区 | North、South和West | 管理层必须公布计划 |

修复前，这三个反例均保留T，却仅为后句建立一项B要求，没有同源阻断，并把完整业务前缀放入检索scope；短`Admission: You will need Control.`字段正例同时通过。这说明缺陷在于普通业务前句与字段标签的分类和内容承接，不能靠放宽或取消source/path校验处理。

当前修复保留全部T原文和来源。明确句式的业务前缀不再成为字段scope，整段及枚举在`pending_requirements`中保留，并以同源`business_preamble_interpretation_unsupported`阻断B/L。没有冒号的业务前句与后续modal合段时，原始整段解释中未支持的clause也保留阻塞，不能在T拆句后消失。短明确字段及实际标签来源仍保留，不是一概禁用冒号。

同一固定oracle的三个前缀反例、一个无冒号反例及短字段正例现已通过。软件`21ebba9c70e11bdae557c94cca4686df99e6432228a545d24354c93ec57d6f63`的新P05保存轨迹已重新读取：expected L94及候选`#/pages/1/raw/json_result/0/7`各有一条同源B/L阻塞和一条完整pending，业务查询不再含该前缀，全部主分及层分/分子撤回。这是修复错误的覆盖和定位声明，没有宣称三个投资方向已正确语义解析，也没有提供空B的N/A或成绩。其余组与整轮遍历仍以最终当前索引为准，不能继承中断诊断。
