# Service表头路径表达的读回缺陷

本记录读取保存的native结构、实际service Markdown和公共检索JSON；缺陷定位以两样本的P07 current作candidate-only `read_candidate_markdown`读取，修复审读另直接调用路径模块检查八条保存正文，没有传入expected或重新评分。未读取原PDF、图片或文字层，没有OCR、视觉判断、新推理或服务操作。以下是读取软件的缺陷诊断，不是正式成绩或转换损失统计。

score的唯一入口为[当前诊断](../runs/lite/diagnosis/three-layer-current/)的`private/scores/组名/quality800-r1/样本名.json`。本轮软件为`21ebba9c70e11bdae557c94cca4686df99e6432228a545d24354c93ec57d6f63`；已逐份直接读取下述SF六组及华为四个service组的十份新原子JSON，重新核对无金额查询、全部召回对象的身份和排除、唯一接受源、数值与单位及年份的原字跨度、对应L/T和pending，没有用旧版本结果或单独scalar校验代替公共trace。十份记录均无`saved_reader_or_grader_failure`，全部保留撤回的主分及三层score、numerator，不能发布成绩。本次只确认这些case已完成并可读，不核根index、不宣称全范围遍历或评分冻结完成；最终运行状态由根会话核对唯一current的terminal index。保存正文及expected始终未改，未重新运行评分。

原缺陷复现的软件为`461edd576cd3ab5c4cd6421204d9b98ff7b4f920be6ab58999e3ad4911134967`，下文仅保留其错误读取方式作为软件缺陷说明。旧score不沿用、不另存副本；当前公共判定均来自上述21eb记录，局部观察不构成全量完成或质量成绩。

| 本次实际核对范围 | 每份outcomes记录条数T/L/B |
| --- | --- |
| 华为P07/P08 baseline/current四份service | 272 / 258 / 67 |
| 顺丰P07/P08 native及四份service | 649 / 596 / 126 |

这些计数均来自本轮逐份读取的实际outcomes，只用于核对当前JSON轨迹内容；同样的计数不代替源切片和身份检查，不证明全部expected语义已被解释，也不构成质量统计。具体接受源、排除维度和仍待决内容见下文。

## 顺丰S4：正文已写完整，路径被当成属性名

样本为`sf-revenue-operating-cost-tables-p035-036`。四份实际正文均在L89打印同一条记录，下列链接分别指向实际文件。

| 组 | 实际文件 | 原句位置 |
| --- | --- | --- |
| P07 baseline | [final.md](../runs/lite/service/baseline/p07/candidate/artifacts/quality800-r1-sf-revenue-operating-cost-tables-p035-036/final.md) | L89 |
| P07 current | [final.md](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-sf-revenue-operating-cost-tables-p035-036/final.md) | L89 |
| P08 baseline | [final.md](../runs/lite/service/baseline/p08/candidate/artifacts/quality800-r1-sf-revenue-operating-cost-tables-p035-036/final.md) | L89 |
| P08 current | [final.md](../runs/lite/service/current/p08/candidate/artifacts/quality800-r1-sf-revenue-operating-cost-tables-p035-036/final.md) | L89 |

原句中的两个金额片段为`按地區劃分: / 中國港澳台；截至12月31日止年度 / 2024年 / 金額人民幣千元：9,467,291`及`截至12月31日止年度 / 2023年 / 金額人民幣千元：9,134,850`；同一行还实际打印两年的佔營業收入比及金額同比變動。分组、主体、年度口径、年份、金额标签、币种、数量级和金额没有从这条正文丢失。

461版四组S4查询均按主体`中國港澳台`、属性`金額`、地区分组、2023年、人民幣千元、人民幣、年度口径及实际营业收入范围定位，没有把正确金额放进查询。但检索`candidates=[]`，结果为incorrect。candidate-only读取揭示了原因：`按地區劃分`被读成一个普通属性，其值为`/ 中國港澳台`；金额属性被整体读成`截至12月31日止年度 / 2023年 / 金額人民幣千元`，`subject=''`、`qualifiers={}`、`identity_facets={}`。金额字面虽然在该错误fact中，正确的业务位置没有建立。四组L89均没有覆盖此读取缺口的candidate blocker或pending；其他位置的软件blocker使整组仍禁止发布，不能因此把本条误拒当作转换loss。

原生P07/P08的同一业务位置已有独立行列证据，本轮21eb记录中的S4逐项B为correct，源头及其实际header/row evidence已独立核对：

| native入口 | 实际数据源 | 本格自己的行与列证据 |
| --- | --- | --- |
| P07 | `#/pages/0/raw/blocks/6/content/0/content::html/cell[132]`，row23/col3 | row header `cell[129]`为中國港澳台；row group `cell[117]`为按地區劃分:；列头`cell[1]`、`cell[4]`、`cell[7]`依次为截至12月31日止年度、2023年、金額人民幣千元 |
| P08 | `#/pages/0/raw/6/content::html/cell[132]`，row23/col3 | 同一实际表内`cell[129]`、`cell[117]`及`cell[1]/[4]/[7]`分别保留上述行、组和完整列路径 |

既有[矩阵诊断](three-layer-matrix-readback.md)中的C136是P05保存对象：`#/pages/0/raw/json_result/0/4/content::html/cell[136]`，row24/col3；其行头C133、组头C121、列头C1/C4/C7分别打印中國港澳台、按地區劃分：、年度口径、2023年、金额人民幣千元。这些局部编号属于各自序列化，不是跨格式身份；不能把P05的C136冒充P07/P08源对象，也不能按金额相同找位置。

### SF当前公共入口：21eb六组S4可定位，同比仍待决

本轮直接读取21eb版的P07/P08 native及P07/P08 baseline/current六份完成记录，S4均从50个同属性金额候选中只接受各自的`B:87`，逐项B outcome为correct。已重新核对native实际`header_evidence`及`row_evidence`、service当次原字快照和标量子串，不沿用旧版接受源。“50个”仅指这六组的本次检索集合，不涉及P05或完整expected覆盖。查询只有中國港澳台、金額、財務回顧和營業收入范围、按地區劃分、2023年、年度口径、人民幣千元和人民幣，没有value或金额；其余49项均有明确拒绝维度，subject、scope、分组和qualifiers的冲突出现次数分别为48、44、44和25，同一候选可以有多个冲突。这些身份核对在值比较之前完成。

被接受的native源分别仍为P07/P08各自的`cell[132]`、row23/col3；四份service源均为`markdown:L89:22`、`lines=[89,89]`，数值原字`9,134,850`位于`[120,129]`。当次按各份`source_fragments`中的列表正文核对，限定来源如下，均为零起点、左闭右开，不包括Markdown列表标记。

| 本字段限定 | 21eb版L89真实跨度 | 原字 |
| --- | --- | --- |
| period_basis | `[90,101]` | 截至12月31日止年度 |
| period | `[104,109]` | 2023年 |
| unit | `[114,119]` | 人民幣千元 |
| currency | `[114,117]` | 人民幣 |

六份记录中，S4的`field_binding`与年度口径、期间、单位、币种的四条`qualifier_scope`均为correct，对应L:401至L:405，均绑定各自的实际值对象。四份service同一L89的`金額同比變動：3.64%`在`[165,177]`仍有同源`header_path_comparison_periods_unresolved` blocker及pending。原文没有明确from/to角色，未从相邻两年补出起止期，不能将金额项正确称作整条记录解释完整。每份service的完整候选pending共有25项同比期间待决（包括L89）、2项业务前言待决和6项路径字段语法待决；原生两份均保留2项业务前言待决，没有用当前金额定位替代这些范围的解释。

T检查使用各份21eb记录自己的`source_cells`及`source_fragments`，没有套用旧版本跨度；完整T来源与有限alias容量检查均通过。四份service各有25个L89文字atom，其中18个为bounded alias；各origin与原字切片一致，alias的`origin + data_object`组合唯一，数据对象均指向本行实际字段范围；数值origin各有独立来源且没有被alias复制。这里核对的是有限来源容量，没有通过删掉待决同比或去重普通数值改善T。六份完整记录仍均为`publishable=false`、`quality_scores_withheld=true`，主分及三层score、numerator均为null；本次收益属于读取软件识别既有表达，不能写成service新增内容或转换优化收益。

## 华为：相同路径语法，行标签承担指标角色

`huawei-financial-summary-p007`的四份P07/P08 baseline/current正文也都在L13打印`销售收入；2024 / (美元百万元)：118,162；2024 / (人民币百万元)：862,072`，随后同条继续2023至2020及各自单位。一个实际入口为[P07 current final.md](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-huawei-financial-summary-p007/final.md) L13。

此处首部实际打印销售收入，而列路径只有年份与单位，没有额外的金额列标签。461版把属性误读成`销售收入；2024 /`，把首个数值及后续全部年份吞进一个value，只留下首个美元单位限定；`subject=''`。四组2024年两币种的销售收入要求均召回零候选，L13同样没有本地candidate blocker。它与SF属于同类现有路径表达读取缺口，但角色不能机械套用：SF自己打印了金额列标签及中國港澳台主体，华为自己打印了销售收入行指标及年度、单位列路径。读取器须从各自语法证明角色，不能用expected补出属性、主体、年度或币种，也不能跨记录借单位。

### 华为当前公共入口：21eb四份记录已实际重核

本轮直接读取P07/P08 baseline/current四份华为score JSON，确认`scoring_software_id`均为`21ebba9c70e11bdae557c94cca4686df99e6432228a545d24354c93ec57d6f63`。四组2024双币种的逐项B outcome均为correct；每个查询都召回L13的六个同属性对象，分别只接受本币种、本年度对象，其余五项，即另一个2024币种及2023至2020对象，均以`qualifiers`冲突拒绝。被接受项的reason为`identity_and_context_verified_before_value_comparison`；查询只有空subject、销售收入属性、五年财务概要范围与分组、2024年、单位及币种，没有value或金额。以下接受源、数值原字及其`value_source`、单位和年份限定源、L关系、T原字与pending均从这四份新记录检查，没有继承旧版本判定。

| 被定位的实际对象，四组一致 | 数值原字跨度 | 同行自己的年度、单位与币种来源跨度 |
| --- | --- | --- |
| L13的`B:0`，美元百万元，原字`118,162` | `[20,27]` | 年度`[5,9]`为`2024`，单位`[13,18]`为美元百万元，币种`[13,15]`为美元 |
| L13的`B:1`，人民币百万元，原字`862,072` | `[44,51]` | 年度`[28,32]`为`2024`，单位`[36,42]`为人民币百万元，币种`[36,39]`为人民币 |

这些source均为各自`markdown:L13:2`、`lines=[13,13]`的列表正文，跨度相对去掉Markdown列表标记后的原字，零起点、左闭右开。销售收入的实际行标签在`[0,4]`；范围及分组证明来自候选自己的L7五年财务概要标题，当前范围止于下一实际标题L57，没有从expected补候选分组或借后面的同名对象。

L层对应两项的`field_binding`与period/unit/currency `qualifier_scope`关系共八条，均定位到L13并判为correct，保留实际行标签及年度、单位头的独立来源。完整T来源与有限alias容量检查均通过，四份L13投影各有24个文字atom，其中18个为bounded alias；各origin与自己的`source_fragments`原字切片一致，alias的origin与实际data_object组合唯一。候选业务qualifier也保留原字`period=2024`，没有把B的年历等价变成补字。两个2024文字片段对应required的`2024年`，各自保留`S=0,D=1,I=0`及incorrect；其他年度原字也未补“年”。

21eb四份记录的L13没有同源blocker或pending，但整条仍均为`publishable=false`、`quality_scores_withheld=true`，主分及三层score、numerator均为null：每份L37仍有六项`header_path_row_metric_unproven` pending，完整blocker列表另有1项`unclassified_business_prose`及3项`prose_endpoint_role_collision`。这里只确认2024双币种的实际召回、排除和源绑定；没有将局部correct扩写为华为选段完成或四组可发布。SF六份同版记录已独立重核并列于上节，不由华为结果代替。

## 模块审读与定向复核方法

独立模块审读发现，初版路径读取能分开华为2024两币种，但后四个年度的`（单位：(人民币百万元)）`被完整保留为`header_path_scalar_syntax_unsupported`。现已在路径模块内支持完整打印的后置Unit声明和正确配对的嵌套括号，没有改shared measurement语法；未知单位、括号不配对、尾随未知文字仍保留整段pending，header与声明、inline与声明的单位冲突也保留pending，不覆盖其一。独立最小反例先失败，修复后模块34项测试及Ruff通过。

直接读取八条实际正文时，华为四版L13均暴露六个销售收入测量，保留原来打印的`2024`至`2020`年度字面以及各自单位、币种和准确value/unit/currency跨度；没有从expected补“年”字或借首列美元单位。SF四版L89均暴露两个年度的金额、比例及一项同比；最后同比只有自身`unit=%`，原文没有明确from/to角色，仍保留`header_path_comparison_periods_unresolved`，不从相邻年份猜起止期。两类记录的`consumed_spans`都逐字恰好覆盖一次，Markdown列表标记前的offset也保持准确。这只验证模块读取和文字记账，不证明公共T/L/B评分已修复或整条无blocker。

从仓库根目录执行以下命令，只读八条已保存原句，复核模块角色、限定、pending和实际跨度。它不加载expected、不评分，也不输出整份候选或完整trace。

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from moparse_eval.header_path_requirements import read_header_path_requirements

for sample, number in [("sf-revenue-operating-cost-tables-p035-036", 89),
                       ("huawei-financial-summary-p007", 13)]:
    for pipeline in ("p07", "p08"):
        for stage in ("baseline", "current"):
            path = Path(f"benchmark/runs/lite/service/{stage}/{pipeline}/candidate/artifacts/quality800-r1-{sample}/final.md")
            raw = path.read_text().splitlines()[number - 1]
            assert raw.startswith("- ")
            text = raw[2:]
            result = read_header_path_requirements(text, {"path": str(path), "lines": [number, number],
                                                           "text_span": [2, len(raw)]})
            covered = [0] * len(text)
            for item in result["consumed_spans"]:
                a, b = item["span"]
                assert item["text"] == text[a:b] and item["source"]["text_span"] == [a + 2, b + 2]
                for index in range(a, b):
                    covered[index] += 1
            assert covered == [1] * len(text)
            print(sample, pipeline, stage, [(f["subject"], f["attribute"], f["qualifiers"])
                                             for f in result["facts"]],
                  [item["reason"] for item in result["pending_requirements"]])
PY
```

统一同版重跑时，只读取已经写完的下列score路径：SF的P07、P08 native及四个service组，华为的四个service组。本轮已按此范围核对十份21eb记录；根会话仍须在终态核对`current/index.json`与各份`scoring_software_id`。对SF按`subject=中國港澳台 / attribute=金額 / period=2023年`、华为按`attribute=销售收入 / period=2024年`定位outcome，查询不能带金额。检查召回候选的subject、属性、分组、scope、unit、currency、basis及其原字来源，再看值；同时检查L89或L13的blockers与pending，以及共享表头文字的T投影和报告source guard。不能只看S4由incorrect变成correct。

下面的定向读取只打印软件身份、单项状态、召回数及该行待决原因，不输出质量分数；写入中的JSON跳过，根index闭合前不读。

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path

root = Path("benchmark/runs/lite/diagnosis/three-layer-current/private/scores")
service = ("P07-baseline", "P07-current", "P08-baseline", "P08-current")
for sample, line, subject, attribute, period, groups in [
    ("sf-revenue-operating-cost-tables-p035-036", 89, "中國港澳台", "金額", "2023年", ("P07", "P08", *service)),
    ("huawei-financial-summary-p007", 13, None, "销售收入", "2024年", service),
]:
    for group in groups:
        path = root / group / "quality800-r1" / f"{sample}.json"
        try:
            record = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        rows = [row for row in record["outcomes"] if row["layer"] == "B"
                and row["expected"].get("attribute") == attribute
                and row["expected"].get("qualifiers", {}).get("period") == period
                and (subject is None or row["expected"].get("subject") == subject)]
        local = [item["reason"] for item in record["blockers"]
                 if item.get("source", {}).get("lines") == [line, line]]
        print(sample, group, record["scoring_software_id"],
              [(row["outcome"], len(row.get("retrieval", {}).get("candidates", []))) for row in rows], local)
PY
```

S4的旧零召回不能作为交付正文损失，源码读回修复也不能计作交付正文优化收益。SF六份及华为四份21eb新记录仅提供有限公共验证；旧score及副本不保留，全量终态与其余范围仍由根会话统一核对，不能用这十份局部观察替代其余范围或解除发布门禁。
