# 业务前句被误作字段范围的读取诊断

本记录只保留可由expected文字和未改动候选定位的软件缺陷，不保留已删除评分派生产物的同版核对、局部判定或检索数量。没有读取PDF、图片、文字层或OCR，没有模型、候选回放或服务操作。验收定义由[评测任务](../evaluation-tasks.md#three-layer-evaluation)维护。

实际例子为`alibaba-shareholder-letter-p004-005`。canonical expected位于`pdf_sample/parsing/expected/complex-alibaba-2025-annual/expected.md`第94行；P05自己的段落保存在[native.json](../runs/lite/artifacts/P05/measured-quality800-r1/alibaba-shareholder-letter-p004-005/native.json)的`#/pages/1/raw/json_result/0/7`。以下范围为原段零起点、左闭右开文字跨度，不是PDF坐标。

| 原文位置 | 实际业务内容 | 曾出现的错误解释 |
| --- | --- | --- |
| L94首句`[0,209]` | 陈述正在增加投资，并枚举AI与云基础设施、基础模型与原生应用、既有业务AI转型三个方向 | 字面保留，但业务枚举没有被语义承接，也没有同源未支持说明 |
| L94后句`[210,386]` | 陈述未来投资将超过此前投资 | 解释后句而遗漏前句，不能证明整段已解释 |
| 首句前缀`[0,72]` | `To realize this vision, we are ramping up investments in three key areas` | 被当成字段标签并用于后句范围定位 |

前缀的实际文字存在，不证明它是字段标签。该前缀本身已经陈述业务内容，把它当作后句身份会将答案内容混入定位，同时遗漏前句。来源或路径校验不能替代这一语义分类。

[独立公共入口反例](../../tests/unit/test_three_layer_prose_contract.py)使用扩展三类运营、优先三个项目、投资三个地区等发明文本，要求业务前句与枚举均被承接，未支持时保留整段同源未决；短`Admission: You will need Control.`另用于区分明确字段。没有冒号的合段也不能在文字拆句后丢掉未支持子句。这些是软件应满足的边界，不是当前真实段落已经完整解释或候选质量通过的声明。
