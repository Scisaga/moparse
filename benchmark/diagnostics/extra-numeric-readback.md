# P01 华为裸数字的候选自有证据边界

本次只读检查针对`P01/huawei-financial-summary-p007`，最终软件身份及遍历状态以[当前诊断索引](../runs/lite/diagnosis/three-layer-current/index.json)为准。这是软件原因诊断，不是正式评分、完整覆盖声明或语料判断。没有查看图片/PDF，没有读取坐标来推断业务关系，没有改动原生、observation、expected或保存正文。

## 实际字面、角色和父引用

在 [P01 原生 native.json](../runs/lite/artifacts/P01/measured-quality800-r1/huawei-financial-summary-p007/native.json) 中，以下三个对象都明确打印 `label="text"`、`content_layer="body"`，`children=[]`：

| 原生 JSON pointer | 实际 text 与 orig | 实际 parent |
| --- | --- | --- |
| `#/documents/0/document/texts/5` | `636,807 642,338` | `{"$ref":"#/pictures/0"}` |
| `#/documents/0/document/texts/6` | `862,072` | `{"$ref":"#/pictures/0"}` |
| `#/documents/0/document/texts/7` | `891,368` | `{"$ref":"#/pictures/0"}` |

该文件 `#/documents/0/document/pictures/0` 自己的 `label` 为 `picture`、`parent` 为 `#/body`，children 明确列出 `#/texts/5` 至 `#/texts/20`。其 `captions`、`references`、`footnotes`、`annotations` 四项均为空。这里读取的是保存结构中的容器类型与引用，没有打开它的 image 字段或推断其图形含义。

相邻 body children 是 `#/texts/3`、`#/texts/4`、`#/pictures/0`。前两个对象均为 `level=1` 的 `section_header`，其实际字面分别是 `䨭ਜ਼ᩣڒ` 和 `CAGR: (1)%`，父引用都仍是 `#/body`。保存结果未声明这两个同层标题与各个数字之间的属性/期间绑定。不能用 expected 里的正确业务名称替换乱码，也不能从数字出现在其他位置、列表顺序或临近标题中补出它是哪一年的哪个指标。

[原始 observation.json](../runs/lite/artifacts/P01/measured-quality800-r1/huawei-financial-summary-p007/observation.json)和[当前只读 observation](../runs/lite/diagnosis/three-layer-current/private/observations/P01/quality800-r1/huawei-financial-summary-p007.json)保留了上述三个对象的text、`kind="text"`、`native_path`、`parent_id`和`native_parent`。例如text/7的完整父地址是`#/documents/0/document/pictures/0`，其`native_children=[]`，`native_references`的captions、footnotes、references也为空。因此有来源的容器归属存在，但明确业务属性与年份并没有随之成立。图片语义解释不属于本轮工作。

## 实际软件阻塞及应保留的边界

已修复的核心缺陷是把text/5、text/6、text/7的无属性额外数字误建为B重要正文和空L端点，从而产生`unclassified_business_prose`及空`lexical_anchor`的`prose_endpoint_role_collision`。当前读取将这些完整字面作为`unbound_numeric`留在T和`unadjudicated_extra_content`中，不创建没有属性的B事实或空L端点；[该样本当前诊断](../runs/lite/diagnosis/three-layer-current/private/scores/P01/quality800-r1/huawei-financial-summary-p007.json)保存实际来源及其他仍未解决的要求。

这些数字仍是候选实际打印的文字，T 读取必须保留字面和原生来源。它们没有自行提供能定位 `Revenue` 等属性的声明，因此既不能用于救回一个缺失字段，也不能因软件没有给它们建立业务身份，就自动阻断其他已明确、可独立判定的 B 要求。本诊断没有把这些额外文字认定为幻觉、插入错误、零影响或正确业务事实；T 的额外字面及其尚未裁定状态应继续可追溯。

这一处理只限于候选侧没有属性/谓语的额外裸数字。若同样的裸数字本身出现在 reference 授权范围，要求仍未被解释，必须阻断而不是降成空 B 分母。若候选实际打印 `Revenue increased 17`，句子已有明确业务词与谓语，当前读取器无法解释它就是软件不支持，不能为了放行已知字段而把整句改称“额外裸数字”。

## 独立固定测试

[新增公开入口测试](../../tests/unit/test_three_layer_extra_numeric_contract.py) 全用受控文字/结构，正确结论由手工固定，没有读取真实材料或用被测编译器产生答案：

| 固定输入 | 固定要求 |
| --- | --- |
| reference `Revenue: 17`；candidate 正确字段外另印 `891368`、两个分组裸数或同块数字串 | 唯一 B 要求仍为 Revenue=17，并可独立判正确；额外文字及 source 留在 T 的未裁定明细中；不能制造空谓语端点碰撞 |
| reference `Revenue: 17`；candidate 仅印 `17` | Revenue 要求明确不正确，实际候选字段为空；不能以正确数字救位置，也不把缺失字段改成软件未知 |
| reference 自己只印 `891368` | 仍有要求解释缺口，B 软件阻断，不能当作完整空范围发布 |
| reference 或 candidate 实印 `Revenue increased 17`，读取器尚不支持其业务解释 | 保留实际全文及软件阻断，不能当成额外裸数字放行 |
| native-like candidate 将 `891368` 明确放在 picture 父容器中，另有独立 `Revenue:17` | 保留数字的 text 类型和 native source；父容器不能凭空提供 Revenue 属性 |

同一固定oracle的八项测试现已全部通过，包括reference裸数和未支持业务句仍须阻断的反例；它们没有按新输出改写正确答案。该修复不构成华为样本正式质量结果或完整保存输出验收。

当前软件`21ebba9c70e11bdae557c94cca4686df99e6432228a545d24354c93ec57d6f63`的P01保存轨迹已重新读取：上述text/5、text/6、text/7分别作为`unbound_numeric`留在`text_evidence.candidate_atoms`，并以同一原生来源进入`candidate_issues`的`unadjudicated_extra_content`，这三个来源没有额外的软件blocker。记录保持`diagnostic_only=true`、`quality_scores_withheld=true`，主分及层分/分子均为空；即使本样本内部层状态complete，也不发布局部质量分或推导全范围覆盖。
