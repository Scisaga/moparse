# P01 华为裸数字的候选自有证据边界

本记录保留`P01/huawei-financial-summary-p007`的一处软件缺陷例子，只以未改动的保存原生结构和observation为定位依据，不保留已删除评分记录的局部判定、计数或运行身份。没有读取PDF、图片、文字层或OCR，也没有改动expected或候选。

## 实际字面、角色和父引用

[P01 native.json](../runs/lite/artifacts/P01/measured-quality800-r1/huawei-financial-summary-p007/native.json)中，下列对象明确打印`label="text"`、`content_layer="body"`、`children=[]`：

| 原生JSON pointer | 实际text与orig | 实际parent |
| --- | --- | --- |
| `#/documents/0/document/texts/5` | `636,807 642,338` | `{"$ref":"#/pictures/0"}` |
| `#/documents/0/document/texts/6` | `862,072` | `{"$ref":"#/pictures/0"}` |
| `#/documents/0/document/texts/7` | `891,368` | `{"$ref":"#/pictures/0"}` |

`#/documents/0/document/pictures/0`的label是picture、parent是`#/body`，children列出`#/texts/5`至`#/texts/20`；captions、references、footnotes及annotations均为空。这里仅记录容器和引用，没有打开image字段或解释图形。原始[observation.json](../runs/lite/artifacts/P01/measured-quality800-r1/huawei-financial-summary-p007/observation.json)提供同一保存执行的观察入口。

相邻`#/texts/3`和`#/texts/4`是同层section_header，字面分别为`䨭ਜ਼ᩣڒ`及`CAGR: (1)%`，父引用仍为`#/body`。这些来源没有为上述每个数字声明完整业务属性和年份，不能用expected替换乱码，也不能靠数值相同或相邻顺序补出指标身份。

## 软件缺陷与保留边界

曾出现的错误是把无属性额外数字编成重要业务事实和空谓词关系端点。数字必须连同实际来源保留为文字；没有属性或谓语时，不能凭空生成Revenue等业务身份，也不能自动认定为幻觉、正确业务事实或零影响。候选额外未绑定文字与reference自身尚未解释的要求必须分开处理。

[独立受控反例](../../tests/unit/test_three_layer_extra_numeric_contract.py)固定了这些边界：独立Revenue字段不能由另印裸数字救回；reference自身只有裸数时不能成为完整空业务范围；`Revenue increased 17`已有业务词和谓语，读取失败应保留为软件解释缺口，不能降成额外裸数。这里不引用这些反例或旧评分轨迹作为真实样本验收结论。
