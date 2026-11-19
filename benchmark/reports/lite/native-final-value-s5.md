# MO-Parse：S5 财务表格 Native → Final 公共处理价值研究

续修状态（2026-11-18）：第 1–9 节及其链接保留上一轮研究与修复前结论。本轮已把同格多角色及独立范围处理接入公共链，P06 的实际改善、八配置回归及独立版本证据见[第 10 节](#10-复合表头多角色与独立作用范围的实际修复)；旧问题记录不代表续修后的当前结果。

2026-11-18。接手 HEAD 为 `574805b866877a1cdc183e18f1856da348bdf78f`，工作区初始干净。固定范围为 `huawei-statements-p068-070`、原输入页 68–70、P01–P08 各自的保存 Native 与既有冻结 Final。本报告接续 [Native 质量研究](native-quality-findings.md)，没有重新接入解析器、重建评测框架或扩大到其他选段。

## 1. 研究结论

公共处理在 S5 创造了真实的组织价值：它从原生文字及源格建立可追溯的行名、年度、单位和数值引用，将表格交付为可阅读的财务字段。P03–P08 原生表格没有显式列头声明，但并非没有年度、单位和行列关系证据；公共链通过有界的文字计量表头规则建立关系，Semantic 记录及实际 Final 都能回到自己的源格。这个结果有来源和交付正文支持，不只是评分器更容易匹配。

在收入、销售成本、销售毛利的固定六个年度金额上，八组共 48 个值全部保留到 Final；其中 42 个值同时具备完整单位来源，P02 的 6 个受原生不完整单位影响，未被计入完整单位绑定。附注 8 作为收入记录自己的附注列值保留。这里的 48、42 是同一组代表性字段在八份输出中的实例数，不是独立文档数，也不是全体 148 项业务字段的正确率。

全表仍存在重要边界。P02 的错误日期、缺位金额及破损括号原样传播，公共处理没有恢复缺失信息。P01 无标签小计被保留为物理表，未猜补名称。P06 把“人民币百万元”和“资产”合写的角格用作全表字段前缀，出现“资产：负债 / 借款”，并有 74 个非空日期列值没有单位引用；这不能称为完成了正确的财务关系组织。`converted` 和 `conversion=completed` 都不能替代业务验收。

本轮最小修复了一处单位角色识别缺陷：完整单位文字仅缺一侧展示括号时，不能把它变成业务行标签。只重跑 P01、P02 两条受影响的 S5 保存结果链，分别新增 20、65 个单位绑定，原值和列日期均未改。85 是新增来源引用的实例数，不是新增识别出的金额，也不是 85 项业务要求验收通过。旧 Final 和旧证据全部保留。

相同连续 AST 方法已实际应用于八组 Native、八组冻结 Final 及两组修复 Final，Expected 责任和分母完全相同。然而真实 Final 对象证明了单位、币种、附注和范围读取限制，原始 T/L/B 数字不足以衡量本轮财务价值；完整财务质量结论仍留空。本报告不把分数差当作公共处理收益，不发布八配置排名。

## 2. 对象、版本与证据入口

| 对象 | 身份与用途 |
| --- | --- |
| 原 Native | 原执行 `20261026-lite-v3`；各配置自己的 `native.json`、observation、configuration 和原页映射，与上一轮研究相同 |
| 冻结 Final | 原 `cross-document-normalization-phase12/attempt-05/{pipeline}/huawei-statements-p068-070/`；转换软件 ID `f8bcef05feaa4406189d395219a4db50afb8cc9446600ee11adce7fb403e0f1f` |
| 本轮修复 Final | 仅 P01/P02，保存在本轮 `repaired/`；软件 ID `565bbf2dffc3055bb42f6872835808ce2f53805ed22643538a3862348ee37be2` |
| 本轮共同评分 | 同一 `document-ast-continuous/1`，软件 ID 同上；T=4,572 字、L=603 票、B=162 票；没有改分母、阈值、权重或匹配算法 |
| 原有参考 | 只读原 S5 要求投影及其授权 Expected 原文；没有编译新答案或修改 Expected、Oracle、selection、source-map |

原 Final 由[历史转换绑定][historical]及既有 phase13 输入绑定定位，不选择旧分数较好的输出。八组 Native、Final、stage evidence、原执行与输入绑定的 SHA 已逐份核对；八份原 Storage `result.md` 实际存在，与各自 `final.md` 字节一致。研究涉及的主体工件没有缺失，不需要重新转换来制造替代样本。主链实现的接手 HEAD 源码指纹与原转换绑定吻合，单位识别的本轮改动另列身份。

本轮证据集中在 `benchmark/runs/lite/diagnostics/native-final-value-s5-20261118/`：

- [输入与原版本绑定][inputs]：8 组真实路径、SHA、原页、配置与转换身份，以及接手 HEAD 源码核对。
- [正向案例与阶段链][cases]：每组的六个主指标值、物业/厂房/设备两列、Native locator、Contract 项、Semantic 引用、Final 字符跨度和行号。
- [全体字段来源记录][lineage]：实际 Semantic 日期列值与自己的源格、单位、期间、附注列、Final 跨度；只用于归因，不作为另一个评分器。
- [负面原始对象及阶段证据][negative]：缺位金额、无标签小计、不完整单位、单格合写、错误日期与复合角格。
- [共同评分索引][scores]及[读取限制实例][limits]：实际 Native/Final 同版结果、原责任、扣分判据及未采纳为财务验收的原因；存储引用用 `trace_storage.read_score` 展开。
- [修复前证据][before]、[修复影响][repair]、[隔离执行记录][execution]：保留旧对象、两份实际新 Final、来源引用及数值/日期不变证据。
- [研究摘要][summary]：来源实例计数及八组交付状态。没有激活 `scores/current` 或恢复历史 quality800 成绩。

Native 评分仍只读取 Native 独立建树的候选；Final 评分只读取相应 `final.md`，不用 IR、Semantic 或其他配置补答。中间阶段仅在独立比较之后用于追踪来源和变化。P01/P02 三页均为 Docling，P03/P04 均为各自 Paddle，P05 均为 GLM，P06/P07 均为 MinerU，P08 均为 Visual Blocks；本选段没有将 GLM 回退页归为其他后端的情况。

## 3. 实际处理链：在哪一步建立了关系

| 实际环节 | 实现及保存证据 | S5 的实际行为与边界 |
| --- | --- | --- |
| Native 原始对象 | 各自 `native.json`；HTML 格或 Docling `data/table_cells/n` | 保留文字、行列、span、标签和来源；原生错误不由后续答案替换 |
| Adapter 与 NativeContentContract | `adapt_saved_document → bind_native_content`；`evidence.json#/contract`、各阶段 `source_audit/native_handoff` | 基于收到的原始 JSON 字节建立 inventory，绑定 artifact SHA、原页、格位置和原文；不从 observation 的答案补内容 |
| NativeContentEvidence 验证 | `native_content_evidence.py` 的 `validate_native_content`、`verify_table_source`、`validate_ir_handoff`；`source_verification/native_content`、`ir_handoff` | 这是绑定及校验函数，不是一个另行持久化的同名阶段；证明已暴露的对象和源格交接，不能证明业务正确 |
| SavedContentService | `SavedContentService.finalize` 调用真实 Export、IR、TableSemantics、FinalContent | 来源补充、原件和媒体读取禁用；`source_pages/native_pages` 回调明确不适用，不能算实际执行了 PDF 处理 |
| Export | `ExportService.apply_document`；`stages` 中 `exported`、`table_views` | 组装原生表格与正文、规范展示空白，保留源表边界；尚未把金额展开成业务字段 |
| IR | `DocumentIRService.build`；`stages/ir/source_audit/parse_result/tables` | 逐格保留文字、行列及 span；原 Native locator 由并行 Contract/fragment 证据侧追溯。例示 IR 格的 `provenance.sources` 为空，不将其伪称为已经补出了 PDF 来源 |
| TableContext | `TableSemanticsService._apply_owned` 内先调用 `prepare_native_table_scopes` | 没有独立的 TableContext 快照；其结果首次出现在 `semantic` 快照的 `table_fragments/native_evidence`。从原生可读格及明确计量文字建立 `header_rows=[0]`、日期列和业务行范围 |
| TableSemantics | `native_scopes → bind_table_view → _qualify_relation → render_nested_record` | 建立 `CellRef` 行轴、列轴、单位、期间及记录；首个实际字段组织与单位引用出现在此阶段。不能仅据矩形、列数或金额相同判关系成立 |
| FinalContent | `FinalContentService.apply`；`stages/final`、`final_text_evidence`、observation 中 `final_markdown_span` | 保留 Semantic 生成的字段和实际来源跨度，执行可重放的最终正文编辑；不猜补错误日期或缺位值 |
| Storage | `StorageService.write_result`；实际 `persistence/jobs/{selection}/output/result.md` | 写入 Markdown、资产索引及 warnings；8 份旧、2 份新正文均已核对。落盘一致不证明完整财务语义，也不证明线上 API、ZIP 或媒体交付验收 |

阶段名及数组位置来自各工件，通常依次为 adapted、source_pages、native_pages、exported、ir、assets、semantic、final。`adapted` 是真实适配页面的诊断拼接；从 Export 开始才是实际文档渲染。IR 前后的源格可以相同，直到 `semantic` 才新增 header scope、行组、单位/期间引用和列表正文。这把“原文保留”和“明确关系建立”分开，不从 Final 倒推某个不存在的阶段。

## 4. 案例 A：收入、销售成本、销售毛利

Expected L1792–1796 给出人民币百万元、2024/2023 两年及六个值：收入 `862,072 / 704,174`，销售成本 `(479,501) / (378,810)`，销售毛利 `382,571 / 325,364`；收入附注为 8。每个案例均先按自己的表、行名、列轴定位，再核对值，没有用正确金额选择同名字段。

### P03 的完整来源与交付实例

| 关系或阶段 | 实际对象与原文 |
| --- | --- |
| Native 原始表 | `#/pages/0/raw/res/parsing_res_list/1/block_content`；第一行是 `（人民币百万元） / 附注 / 2024年 / 2023年`，以下三行分别是收入、销售成本、销售毛利；全部是 `td` |
| 收入值与行轴 | `::html/cell[6]`、`[7]` 为 `862,072`、`704,174`；`[4]` 为收入，`[5]` 为附注 8 |
| 成本及毛利 | 成本值 `[10] / [11]`，行名 `[8]`；毛利值 `[14] / [15]`，行名 `[12]` |
| 单位与年度 | `[0]` 为 `（人民币百万元）`；`[2] / [3]` 为 `2024年 / 2023年`，不是由 Expected 补入的列轴 |
| Contract | `#/contract/inventory/8` 对应收入 2024 格，实际 inventory 项以 locator 回指 `::html/cell[6]`、原页 68 和原始 `td` 声明；完整项及精确 pointer 在案例文件中 |
| Adapter → Export → IR | `paddle_p1_t1` 的 row=1、column=2 仍为 `862,072`；IR 同一表同一位置保留此格。原来的 `is_column_header=false` 未被改写为解析器已经声明了表头 |
| TableContext | 原始格可读、年份表头及标量记录共同建立 `native_literal_measurement_headers`，header row 0、业务行范围及 row-header column 0；不是单看对齐坐标判定数据表 |
| Semantic | `records[0]` 的金额值引用 `CellRef(paddle_p1_t1,1,2)`，行头 `(1,0)`、列头/期间 `(0,2)`、单位 `(0,0)`；2023 使用另一个源值格和另一个列头 |
| Final 与 Storage | `final.md` L5–10 打印收入、附注 8、两年值及各自单位；2024 金额的实际字符跨度 `[53,60)` 为 `862,072`，Storage 原字节相同 |

Contract 的引用以案例工件中实际 `contract_pointer` 为准；表内 `CellRef` 是公共链的来源引用，不是 Native 原本就有的业务答案。P03 原格中列头角色没有显式声明，但字面年份、计量单位、完整行格与业务标签共同支持这里的有限字段绑定。PDF、其他 pipeline 和 Expected 都没有进入该处理链。

附注的表达需要精确区分：数码 8 作为同一收入记录的“附注”列值，其行头仍是收入；金额的 `ValueRelation.note_refs` 并没有指向附注全文。这证明了行级附注编号的保留与交付，不证明读懂或交付了选段之外的附注解释。附注数码没有被当成人民币金额继承单位。

P01/P02 的原生 locator 为 `#/documents/0/document/tables/0/data/table_cells/n`，对应上述相同的格序号。P01 有明确列头及行头声明，公共链补充可追溯的单位/期间引用并交付字段；P02 第一角格只有 `（人民币百万`，公共链没有合法完整单位可以引用。P05 的入口在 `#/pages/0/raw/json_result/0/1/content`；P06/P07 由自己的 DocVortex middle 表格进入 Contract；P08 从自己的 ContentBlock 表格进入。各自精确 locator、原页和金额来源均在[案例文件][cases]，不以相同字符串推定跨视图同一性。

### 已证明的收益与尚未证明的部分

| 观察 | 结论 |
| --- | --- |
| 八组的六个金额都在自己的源格中，Final 金额跨度与原值一致 | A：48 个实例的内容保留成立；没有恢复新的识别数值 |
| P01/P03–P08 在这些实例中有完整行、年度、单位引用，并实际打印到 Final | B/C：42 个实例的结构组织及单位/期间显式绑定有来源和交付证据；包含原本全 `td` 的表达 |
| P02 同样打印六个金额，但单位缺元，标签前还带有 `（人民币百万：` | 原始值保留，完整单位关系未证；不能按金额正确就把这一组财务字段全部验收 |
| Docling 日期格折行变成空格、表格变成列表、共享单位重复打印 | D：这些展示变化本身不增加业务信息；应与真正建立的来源引用分开 |

这些实例支持公共处理有价值，不支持整张利润表已经全部正确。原生行组、空标签、合写金额和原生损坏值仍有单独责任。

## 5. 案例 B：资产负债表、两列日期及错误传播

Expected L1831 起声明人民币百万元；物业、厂房及设备在 L1835 的两列日期为 `2024年12月31日`、`2023年12月31日`，金额为 `176,565 / 156,495`，附注 14。字段要同时检查项目、日期、单位和附注，金额相同不提供其他轴的证明。

P01 的原生表头在 `#/documents/0/document/tables/1/data/table_cells/2`、`/3`，原字为 `2024年\r\n12月31日`、`2023年\r\n12月31日`。源格和 IR 保留折行，Semantic 使用同一格作为 period ref，Final L207 起打印 `2024年 12月31日：176,565`。这是同一日期的展示空白变化；不能据空白差异称日期丢失，也不能称恢复了一个原本不存在的期间。

P02 同位置的 Native 原字却是 `2024年\r\n2月31日`、`2023年\r\n2月31日`。沿 [负面证据][negative] 的 `native-invalid-date-column`：

| 环节 | 实际结果 |
| --- | --- |
| Native → Contract | 两个错误日期来自原页 69 的原表头；不是评测对应出来的日期 |
| Adapter、Export、IR | 表头文字逐格保留，月份没有改变 |
| TableContext / Semantic | 将自己的年度表头绑定到值；没有验证并修复日历日期，不从 Expected 得到缺少的 `1` |
| 冻结 Final | L147 的 `2024年 2月31日：176,565`，下一年度同样打印 `2月31日` |
| 修复 Final | 新增单位引用后仍打印 `2024年 2月31日`、`2023年 2月31日`；原日期列不变 |
| Storage | 原 Final 与原 Storage、新 Final 与新 Storage 各自一致，错误期间分别被持久化 |

最早可见错误为 Native。公共链做了来源有据的列绑定，却绑定了上游错误日期；这不是业务正确性改善。P02 本表实际生成 70 个非空日期列值槽，修复后 65 个增加单位引用，也不使这些错误日期变成正确。这个 70 是实际输出槽位数，不替代 Expected 的字段要求或上一轮 68 项期间检查失败的口径。

P02 的物业、厂房及设备行名还在原生 `table_cells/8` 中截成“物业、厂房及设”，Final 保留这个损坏名称；金额来源存在并不证明完整项目身份已经正确。

P03/P04/P05/P07/P08 的这个表头保留完整 `12月31日`，原生单位、行名、两列日期及附注可回读到自己的 Semantic 引用。P06 同样保留完整日期，但另有复合角格的单位及字段角色问题，不能据日期完整就宣布全部字段可用。

没有将月份猜改、补零或利用其他配置修正 P02；这类错误应当进入局部重解析或人工复核。

## 6. 案例 C：缺失、未绑定、合写与公共处理退化

### C1. 完整单位文字被展示括号妨碍：本轮最小修复

P01 现金流表角格 `#/documents/0/document/tables/2/data/table_cells/0` 为 `（人民币百万元`；P02 资产负债表角格 `#/documents/0/document/tables/1/data/table_cells/0` 也含同样完整单位载荷，仅没有右括号。Adapter、IR 没有丢掉“人民币百万元”。错误首次表现于 TableContext/TableSemantics：`unit_header()` 未识别这个完整载荷，角格反而进入 `subject_headers`，单位引用为空。

P01 原 Final L470 起实际打印 `- （人民币百万元：销售商品及提供服务收到的现金`，随后两年金额没有单位子项；P02 也将单位文字当作项目名前缀。这是有原文依据的单位未被正确组织，归入公共处理缺陷，不是需要补识金额的场景。

修复位于 [table_context_service.py](../../../app/services/table_context_service.py) 的 `unit_header()`：仅允许一侧展示括号缺失时对整个剩余字符串执行原有有限单位识别；不写回源文字，不补单位字符，不改变数值。独立正反例使用 USD millions、人民币百万元、缺失“元”、嵌套括号及夹带其他词的标签，验证完整载荷可用、不完整或扩展载荷不被补全，原源格不变。相关语义、上下文及保存结果回归通过；它们不作为研究完成标准。

两条必要重跑复用原 `saved_content_closure` 和原 metadata/observation，在只读代码/原 Native、屏蔽原件与 Expected、独立挂载及网络命名空间、GPU 不可见、8 CPU、8 GiB、串行资源下执行。只有本轮输出目录可写，两个执行均无边界违规。没有重跑其他六份冻结 Final，也没有重跑 72 组。

| 对象 | 修复前实际交付 | 修复后实际交付 | 有限影响 |
| --- | --- | --- | --- |
| P01 现金流表 | 单位载荷成为行标签前缀，20 个非空日期列值没有单位引用 | 项目名独立，20 个值各自增加原角格的 unit ref，Final 打印 `单位：（人民币百万元` | 值、年度、括号原文均未补改；只是已识别完整单位的角色与归属恢复 |
| P02 资产负债表 | 70 个非空日期列值无单位引用 | 65 个值增加原角格 unit ref；另外 5 个含逗号、折行等破损值仍未获得单位绑定 | 日期错误和原金额文字均未改变，不把剩余 5 个强制判定为完整金额 |

例示新 P01 Final 现在实际交付：

```text
- 销售商品及提供服务收到的现金
  - 附注：
  - 2024年：931,642
    - 单位：（人民币百万元
  - 2023年：770,927
    - 单位：（人民币百万元
```

右括号仍缺失，保持原字；单位载荷的币种与数量级完整，不因此猜补原生信息。新 P02 仍有 `2024年 2月31日`。两份新结果及对应 Storage 在[修复影响][repair]中分别绑定，旧版本未被覆盖。修复后原 conversion/delivery 的 partial 状态也没有被改成质量通过。

### C2. 原生确实缺字符：公共处理保留错误，不能恢复

P01 的 `#/documents/0/document/tables/0/data/table_cells/31` 在营业利润 2023 列只剩 `04,401`，Expected L1800 为 `104,401`。从 Contract、Adapter、IR 到 Semantic、Final L51 及 Storage 都是原来的 `04,401`，没有证据把首位 `1` 归为公共链丢失，也不能据行内其他金额猜补它。

P02 利润表 2023 研发费用的原生格只剩 `64,721)`，Expected 为 `(164,721)`，首位与负数开括号都不足。实际 Final 继续打印 `64,721)`；该值不是经过公共链的合法负数恢复。需要局部重解析或人工复核，Normalization 不生成金额和符号。

P02 利润表单位角格是 `（人民币百万`，与上述完整载荷缺括号不同。当前有限单位合同没有完整支持此格，原生本表也没有独立已证的完整单位来源；其他表或其他配置中的单位不能借来补它。本轮的负例明确保留其单位绑定未知，没有为了提高分数补“元”。

### C3. 有值但没有足够行轴：保留原格优于制造字段

P01 利润表 row 16 的行名为空，2024/2023 值是 `(597) / 1,483`，对应值 locator 为 `#/documents/0/document/tables/0/data/table_cells/66`、`/67`。另一个空行名的 subtotal 在 row 20。虽然 Expected 明确写“小计”，该名称没有来自这两个 Native 行的独立来源。

公共链记录 `unresolved_row_subject`，保留这两行的物理表；Final L110–111 中实际保留表头及 `|  |  | (597) | 1,483 |`，原值有实际 Final 跨度。它没有给空行编造“小计”。这是有信息、绑定不足、合理保留未决的案例，不是漏掉这两个金额，也不是完整字段转换已经完成。

P02 还在一个原生格内合写了多项金额。例如利润表 row 9 的标签包含“财务收入及财务费用 / 应占联合营公司业绩”，金额格包含 `(8,255)` 和 `(237)` 等多段原文。公共链将相关行保留为物理表，Final 仍有这几个字面值，没有拆成可以唯一确认的独立财务字段；首个能力边界在 TableContext/TableSemantics 的 `native_nonrecord_region_retained`。Source/IR 不缺这段原文，关系不足来自原生合写及当前组织能力，两者不能强行二选一。

S5 保存的全部八组格子 span 均为 1×1，没有已声明的几何合并格可供独立验证。上述是实际单格合写内容，不冒称原 PDF 的 rowspan/colspan 合并；原页没有查看。“真正合并格的完整关系恢复”这一子问题因此保留证据缺口，不增加样本、不重新解析或制造合并格来补齐研究。

### C4. P06 的复合角格：文字有来源，生成的字段关系仍可能不成立

P06 原页 69 的角格为 `（人民币百万元）资产`，精确 Contract locator 是 `#/documents/0/pages/1/blocks/2/content/0/content::html/cell[0]`。其文档视图与原页 envelope 的关系由该 Native 自己的文档/页绑定给出，不能靠字符串相同推定是镜像。该格把单位文字和资产组名放在了一起；完整值仍存在，问题不是金额未识别。

IR 保留这个原格。TableContext 没把格内单位与组名分开，Semantic 的 `subject_headers` 反而把整个格作用于本表所有记录，74 个非空日期列值的 unit ref 都为空。冻结 Final L299 打印 `- （人民币百万元）资产：权益 / 本公司所有者应占权益`，L314 打印 `- （人民币百万元）资产：负债 / 借款`。Expected 的资产、权益、负债是各自范围，不能把它们全变成“资产”轴下的业务字段。

这一新增前缀的文字确有原始来源，但从该文字到整张表所有行的强关系缺少支持，属于 E 类关系退化/未证绑定；不能因为每个输出词都能找到源字，就认为完整字段正确。最早变化位于 TableContext 与 Semantic 的 header/subject 绑定之间，IR 前仍只是未解释的复合源格。它也说明 P06 的 `conversion=completed` 不等于单位和业务关系完成。

修复它需要处理同格内单位片段与组名片段的独立作用范围及来源引用，超出本轮单个完整单位载荷的最小修复；本轮保留真实对象和问题，不扩大成新的拆格框架。

### 无来源内容的检查边界

在六个主指标、两列日期和本轮两项修复的来源对照中，没有发现公共链新增无来源金额，亦没有发现同一金额源格被无条件重复用来提供互相冲突的字段。本轮字段记录中的金额格身份不重复，原共同单位格只在自己的明确表头范围内复用。这个结论限于所检查的来源实例；没有据此证明所有 Final 关系都正确。C4 就是“文字有来源但关系缺少支持”的反例。

## 7. 八种配置的适用性与公共处理增益矩阵

下表的“非空槽/单位引用”来自实际 Semantic 日期列值和 Final 来源跨度，包含可能已经损坏的原值，描述组织产物，不是 Expected 正确率。不同 Native 本来就有不同的合写、空行和记录粒度，不能用记录数排序。利润、财务状况、现金流三表顺序固定；同一空的标题金额槽未计入非空数。

| 配置 | 冻结 Final 的三表非空槽 / 有单位引用 | Native 已有能力与公共组织结果 | 主要限制与实际交付 |
| --- | --- | --- | --- |
| P01 | `50/50；74/74；20/0` | 显式表头及主指标值可用；公共链组织行、年度、附注与单位，保留无标签 subtotal | 原生缺位金额继续存在；冻结现金流单位错作标签，修复后 `20/20`；正文落盘，conversion/delivery 仍 partial |
| P02 | `44/0；70/0；18/17` | 主指标原值及附注 8 存在；能生成部分嵌套记录及保留复杂原格 | 原生日期、金额、符号、单位及合写损坏较多；修复后财务状况单位 `70/65`，错误日期不变；仍 partial |
| P03 | `54/54；74/74；20/20` | 全 `td` 中的年度、单位及主指标经公共规则形成明确引用并交付 | 这些计数不证明各项行组与业务值全部正确；Native 顺序/阶段限制仍使 conversion/delivery partial |
| P04 | `54/54；74/74；20/20` | 与 P03 的固定正向案例有相近组织证据 | 没有建立版本总体优劣；仍有原生顺序等 partial 限制 |
| P05 | `54/54；74/74；20/20` | GLM 自己的 HTML 原格支持主指标和日期字段的公共组织 | S5 结果不消除其他选段已知缺文风险；本组交付仍 partial |
| P06 | `54/54；74/0；20/20` | 主指标和现金流的单位/年度绑定可回读；日期完整 | 财务状况复合角格造成单位缺失及“资产：负债”前缀；conversion 标为 completed 也不构成财务验收；媒体交付 partial |
| P07 | `54/54；74/74；20/20` | 主指标、日期和单位引用可追溯；原生表前标签在 Final 中额外打印“范围” | 原生标题层级未由此变成已证完整树；conversion completed、媒体交付 partial |
| P08 | `54/54；74/74；20/20` | 与 P07 相同的主指标交付字节有各自独立 Native 来源证据 | 不因输出字节相同推定同一次执行；原生阅读顺序未知，conversion/delivery partial，不涉及图像语义 |

| 配置 | A 信息保留 | B 结构改善 | C 业务关系改善 | D 仅表达变化 | E 退化或风险 | 未决 |
| --- | --- | --- | --- | --- | --- | --- |
| P01 | 六个主指标及原生错误均保留 | 原格展开为项目记录 | 主指标行/年/单位/附注；另修复现金流 20 个单位引用 | 日期折行改空格 | 冻结现金流单位错作前缀已修复 | 无标签 subtotal、完整业务层级 |
| P02 | 六个主指标、错误日期和破损值保留 | 部分行展开，复杂行保留原表 | 记录级年份/附注；另修复 65 个单位引用，日期仍错误 | 日期折行改空格 | 不完整单位成为标签前缀、合写行无法可靠拆分 | 正确金额/日期/完整单位及行轴仍需核实 |
| P03 | 六个主指标实际原值保留 | 全 `td` 生成记录 | 正向六例单位/年/附注来源闭合 | 格式及单位重复打印 | 本轮关键正向例未确认新增退化 | 完整行组、全表质量及原生顺序 |
| P04 | 同上，各自来源 | 同上 | 同上 | 同上 | 同上 | 同上，版本优劣未证 |
| P05 | 同上，GLM 来源 | 同上 | 同上 | 同上 | S5 关键正向例未确认新增退化 | 全表质量；不外推其他选段 |
| P06 | 原值及完整日期保留 | 主指标、现金流记录化 | 主指标的六例成立 | 列表化与重复单位 | 复合角格产生全表强前缀，财务状况单位未绑定 | 同格单位/组名的正确范围 |
| P07 | 原值及日期保留 | 全 `td` 记录化 | 正向六例成立 | 增加来源表前标签的“范围”文字 | 不能以范围文字证明完整标题树 | 标题层级、媒体交付、全表质量 |
| P08 | 原值及日期保留 | 同上，各自来源 | 正向六例成立 | 同上 | 顺序未证 | 顺序、标题层级及全表质量 |

A–E 不是互斥的样本评分，也不相加成总收益。一个原值可以得到 A 的保留、B/C 的显式组织，同时保留上游业务错误；同一值的换行规范化属于 D，不重复计成业务事实增长。这里不选择总体获胜解析器，而是明确哪些 Native 表达适合当前公共处理，哪些必须保留限制。

## 8. 同版 T/L/B 的实际结果与研究限制

原连续方法已经在真实调用链执行，没有为了使 Native 和 Final 同分而改 AST。下表保留程序原计算值，仅用于解释当前比较器；**这些数字不采纳为 S5 财务质量成绩，不计算公共处理质量总增益**。

| 配置 | Native T / L / B | 冻结 Final T / L / B |
| --- | --- | --- |
| P01 | 55.927 / 17.302 / 8.513 | 28.390 / 7.546 / 未决 2 项 |
| P02 | 43.176 / 15.755 / 4.192 | 0 / L 未决 22 项 / B 未决 28 项 |
| P03 | 21.041 / 3.980 / 3.601 | 37.095 / 7.380 / 0.617 |
| P04 | 21.019 / 3.980 / 3.601 | 36.045 / 6.938 / 0.617 |
| P05 | 21.391 / 3.980 / 3.601 | 40.157 / 7.822 / 0.617 |
| P06 | 20.976 / 4.146 / 4.218 | 34.164 / 8.015 / 1.929 |
| P07 | 20.888 / 3.897 / 2.984 | 14.983 / 4.726 / 0 |
| P08 | 20.888 / 3.897 / 2.984 | 14.983 / 4.726 / 0 |

三个真实限制解释了为什么不能直接从这张表判断公共处理质量：

1. P03 Final L14–17 明确分别打印两年的销售成本及其单位，但候选读取只给 2023 字段承接单位，2024 字段只有 note/period，`B:2` 因而失败于数量维度及完整轴。`B:3` 又有单位内币种未独立传入限定比较的问题。真实正文及公共来源引用均存在，不能把零分当作 Final 没有单位。
2. Expected 的收入标签含“附注8”，Final 将附注 8 放在同一收入记录的独立附注列。`B:0/1` 没有建立可靠字段对应；P07/P08 的来源“范围”文字也没有自动成为评测 heading scope。两种表达需要忠实读取各自关系，而不是把内部 Semantic 直接塞给评分候选补分。
3. T 沿用出现容量及插入政策。Final 重复单位、范围、附注和列表包装，Expected 则展开另一种记录形式；可见文字的表示与对应敏感性仍存在。P02 冻结 Final 的 `S=293,D=2186,I=2469` 超过 4,572 字分母而截断为 0，不表示整篇没有保存文字。

这些限制有 [原 trace 与真实 Final 对照][limits]，没有把其余责任按前缀豁免，也没有手工改原分数。研究中的字段来源闭合用于说明实际信息流，不替换程序的正式评分或制造新的正确率。修复后 P01 的原计算为 `36.242 / 8.983 / 1.852`，P02 仍为 `0 / 未决22 / 未决28`；单位绑定的实际恢复由 85 个 source ref 和新 Final 证明，不以这些分数的高低判修复成功。

## 9. 处理建议、成本与停止位置

当前可以直接用于阅读或受控下游输入的是来源已闭合的局部字段，例如七组完整单位的收入/成本/毛利六例，以及保持自己正确日期和单位的具体财务状况字段。不能据此直接采用整份 S5 Final 作为可计算、完整正确的财报答案。保留物理表和 partial 是处理能力不足时的有效交付形式，不等于已经恢复其全部业务关系。

后续处理应按问题分流：

- 可以由公共处理改善：完整单位载荷的角色、已有明确年份与行名的记录组织、自己的附注列、已有条件下的共享单位范围。本轮括号单位修复属于这一类。
- 应局部重解析或人工复核：P02 的错误日期、缺位金额及符号，P01 的 `04,401`，以及 Native 本表缺少完整来源的单位。公共处理不猜补答案。
- 应保留未决：空标签 subtotal、单格合写多个金额、复合单位/组名、原生未声明的几何合并关系、完整业务层级和原生顺序。P06 的复合角格是优先的公共处理边界案例。
- 评分读取限制单列：嵌套单位、币种、附注及“范围”的忠实读取仍不足；它们不与模型能力、实际交付改善混成同一个收益数字。

最值得继续研究的问题是：公共链能否在保持已证字段正常交付的同时，对“同格单位加行组”“破损金额”“无标签小计”保留明确边界，避免把原始文字强行升级成整表业务关系。优先使用 S5/P06 复合角格与 P02 合写行等现有对象验证，不预设扩展到 S1–S9 或重建评分体系。若之后需要量化财务质量收益，应先独立验证 Final 表达的读取能力，再用相同规则配对比较；本轮不继续扩展这项工作。

原解析、模型初始化、公共处理、评测和 Storage 的成本保持分开。历史 `development_conversion_seconds` 是保存 Native 到公共链返回的研究用墙钟，包含阶段快照和来源校验，发生于 Storage 写入之前；不是解析器推理时间，也不是无审计的生产延迟。没有独立 Export、IR、Semantic、Storage 分段耗时可供相加，未测项保留未知。此次两条 CPU 重跑是验证，18 次 CPU 比较是评测；没有重新开展性能实验，不包装成 GPU 独占成本。

本轮仅修改公共单位角色识别及其受控正反例，新增本报告和本地研究证据。原 Native、Expected、Oracle、selection、source-map、历史 Final、原始成本与输入均未改；原输入和冻结 Final 的 SHA 保持。没有 PDF/图片查看、PDF 文字层、OCR/VLM、模型运行、在线服务/GPU/TTS 操作、正式 current 激活、部署、提交或推送。本轮到此停止扩展，保留研究与修复前后证据，供用户审阅。

## 10. 复合表头多角色与独立作用范围的实际修复

本轮从实际 HEAD `b39d00f63c0910a0979f102032ad4585f2357081`、干净工作区接续，直接修改现有 TableContext、TableSemantics 和来源去向记录。最终版本已在 S5 八配置各自的保存 Native 上运行；P06 原页 69 的 74 个非空日期列值逐项获得有源格、有范围及实际正文位置的单位引用，错误的“资产：负债 / 借款”前缀消失。没有重做 Native 质量研究、运行评分或转换完整 72 组 Final。

### 10.1 版本、范围与证据保存

证据根为 `benchmark/runs/lite/diagnostics/s5-cell-role-scopes-20261118/`。[输入绑定][role-inputs]保存原 Native、observation、旧 Final、旧 Semantic/evidence 及旧 Storage 的路径和 SHA；`before/`独立保存八份旧正文、Semantic/evidence、Storage 和当前接手代码快照。P01/P02 使用上一轮完整单位括号修复后的实际交付作为回归基线，其余六组使用原冻结交付，没有为 P01–P06 制造历史处理基线。接手软件 ID 为 `565bbf2dffc3055bb42f6872835808ce2f53805ed22643538a3862348ee37be2`；六组冻结交付的原软件身份仍保留为第 2 节所列值。

最终修复软件 ID 为 `22f5a0a17c9a12b314fd1ec6b7dc8d0931111176d6b04b9b34aa28c3d2c154c4`，代码在 `attempt-02/after/software/`独立保存。八条最终重放全部使用这一身份，各自实际 Export、IR、Semantic、Final 和 Storage 保存在 `attempt-02/after/{pipeline}/huawei-statements-p068-070/`。最初实现及其八份工件保留在 `attempt-01/`；随后补齐“分组已证、单位未证”的局部保留及来源拒绝校验后，才生成最终版本，未覆盖前次证据。

两次都是必要的 S5 确定性重放，复用原 CLI 及原 source metadata：只读代码/Native、独立 mount/network namespace、原件与 Expected 等目录屏蔽、GPU 不可见、8 CPU affinity、8 GiB address-space limit、串行，仅本轮输出目录可写。最终八次执行均成功，工件内的边界违规为空，Native 未改，Actual Final 与 Storage UTF-8 字节一致；原解析成本未改。这些执行是内容组织验证，不是新的吞吐或生产延迟测量。详见[执行记录][role-execution]和各条 `evidence.json`。

### 10.2 进入实际处理链的通用能力

原 Native 的 HTML 角格依次通过 Adapter、Export、IR 保留完整文字；IR 没有被拆格或写入新的答案。`prepare_native_table_scopes()`调用现有 `native_scopes()`，在已确认的计量表头范围内建立格内角色声明。`_compound_header_roles()`按实际边缘括号与文字跨度读取单位，另用连续标量记录和精确具名总计证明起始分组的范围；后者不借用单位的范围。生产代码没有公司、配置、页码、金额或具体角格特判。

角色复用 `TextRef`，通过 `source_cell`回指同一 `CellRef`；`native_evidence.cell_roles`只保存一份完整原格和原生 locator，每个角色各有实际片段、半开字符跨度、识别依据和行列范围。`bind_table_view()`不再把已分解角格整体放进所有记录的 `subject_headers`；分组片段进入适用记录的 `row_groups`和 `ValueRelation.row_headers`，单位片段由 `_qualify_relation()`独立限定到适用值。既有具名总计规则同时支持中文总计，结束旧组后不把它传播到后续跨组汇总。

`render_nested_record()`仍按这些已有引用生成正文，FinalContent 继续使用自己的实际编辑账本，Storage 保存实际 Final。输出 observation 和反向 Native 去向增加角色的源格及片段跨度、Semantic token 和真实 Final 字符位置；整格去向标为 `located_in_final_roles`时，必须由实际片段覆盖其非空白原文，不能拿某个片段冒充完整角格。来源校验拒绝重叠跨度、改绑 locator、外表 occurrence、超出范围的分组和脱离已证分组的值。来源定义更新在[表格来源约定](../../../docs/specs/table-source.md#表头与限定语作用域)。

两个方向的局部不确定性均保留：已证单位、未证组名时仍可建立单位引用，组名原文留在局部原表；已证组名、括号内资格文字未证时可保留分组而不给值补单位。部分文字被引用不算整格已消费，残余原文通过现有 retained row 路径交付，不让一格的歧义阻断其他记录。这些反例来自受控文字结构，不将它们计为额外真实财报样本。

### 10.3 P06 原页 69 的实际范围与 Final

原生 locator 保持为 `#/documents/0/pages/1/blocks/2/content/0/content::html/cell[0]`，完整原文仍为 `（人民币百万元）资产`。下列坐标均为此物理表的原始零基行列，不是新插入的显示行，也不出现在交付正文中。

| 角色 | 实际文字来源 | 证据及适用范围 | 实际金额列实例 |
| --- | --- | --- | --- |
| 单位 | 原格 `(0,0)` 的 `[0,8)`：`（人民币百万元）` | 当前完整日期表头的 body rows 1–39，columns 2、3；附注列不继承金额单位 | 74 个非空日期列值各有一个独立引用及其后的真实单位正文 |
| 起始业务分组 | 同格 `[8,10)`：`资产` | 连续记录 rows 1–18，至源格 `(18,0)` 的“资产总计”结束；不跨权益标题 | 18 条记录、36 个日期列值 |
| 权益分组 | 独立标题源格 `(19,0)`：`权益` | rows 20–22，至“权益总计”结束 | 3 条记录、6 个日期列值 |
| 负债分组 | 独立标题源格 `(23,0)`：`负债` | rows 24–38，至“负债总计”结束 | 15 条记录、30 个日期列值 |
| 跨组总计 | 行名源格 `(39,0)`：`权益及负债总计` | 不继承资产、权益或负债的业务分组；仍在本表单位范围内 | 1 条记录、2 个日期列值 |

这里的 74 是实际逐项检查结果，并非预设让每个值都继承同一单位：表头只声明一个完整单位，两个日期列均在其范围内，74 个原值均符合既有标量及计量适用条件；附注编号没有获得单位。74 条对照分别保存值格、原文、行名、附注列、日期及期间引用、单位/分组片段、作用范围、实际 Final value 和 qualifier 跨度，见[逐值记录][role-values]。原角格在反向去向中有 74 个单位位置和 18 个分组位置，均回指同一原生格的不同片段，不制造第二个源格。

| 比较对象 | 修复前实际结果 | 最终修复后实际结果 |
| --- | --- | --- |
| 原始角格 | `（人民币百万元）资产` | 完整原文、Native locator、源格与 IR 文字不变 |
| 角色识别 | 整格成为所有记录的业务列头 | 单位 `[0,8)` 与资产组 `[8,10)` 独立引用 |
| 单位引用 | 74 个非空日期列值均无引用 | 74 个逐项建立引用，范围为本表两个日期列；附注列仍无单位 |
| 业务分组 | 权益、负债记录仍带资产前缀，负债还覆盖最后的跨组总计 | 资产、权益、负债独立；跨组总计无继承组名 |
| Final | `（人民币百万元）资产：负债 / 借款` | `负债 / 借款`，其两年金额下分别打印单位 |
| 原始值与限定内容 | 原金额、日期、行名及附注 | 原源格逐格一致，金额和附注列实际交付文字没有猜改 |

最终 [P06 Actual Final][role-final] 中的真实节选为：

```text
- 资产 / 物业、厂房及设备
  - 附注：14
  - 2024年12月31日：176,565
    - 单位：（人民币百万元）
  - 2023年12月31日：156,495
    - 单位：（人民币百万元）

- 负债 / 借款
  - 附注：24
  - 2024年12月31日：237,508
    - 单位：（人民币百万元）
  - 2023年12月31日：291,688
    - 单位：（人民币百万元）
```

### 10.4 八配置真实回归与剩余边界

下表每格依次为“非空日期列值数：修复前有单位引用 → 修复后有单位引用”。它是实际来源组织对照，不是业务正确率或 T/L/B 分母。P01/P02 的“前”已包括上一轮括号缺一侧的修复。

| 配置 | 利润表 | 资产负债表 | 现金流表 |
| --- | --- | --- | --- |
| P01 | `50：50 → 50` | `74：74 → 74` | `20：20 → 20` |
| P02 | `44：0 → 0` | `70：65 → 65` | `18：17 → 17` |
| P03 | `54：54 → 54` | `74：74 → 74` | `20：20 → 20` |
| P04 | `54：54 → 54` | `74：74 → 74` | `20：20 → 20` |
| P05 | `54：54 → 54` | `74：74 → 74` | `20：20 → 20` |
| P06 | `54：54 → 54` | `74：0 → 74` | `20：20 → 20` |
| P07 | `54：54 → 54` | `74：74 → 74` | `20：20 → 20` |
| P08 | `54：54 → 54` | `74：74 → 74` | `20：20 → 20` |

八组 Native cells 和 IR 交接使用的源格原文均未改，Semantic 值格集合及列头、期间、附注引用不变；全部 1,770 个已组织值槽（含附注与空文字槽）的实际 Final 文字逐项与各自修复前一致。P01 的 8 个、P02 的 44 个保留源格及其实际 Final 出现也逐项不变，无标签小计及破损合写没有被补名或拆成猜测值。固定收入、销售成本、销售毛利的 48 个年度金额仍全部交付，其中 42 个有完整单位来源；P02 六例仍因原生单位缺字而未被补全。详见[总对照][role-comparison]、[主指标逐值来源][role-principal]、[附注及局部保留对照][role-retention]和[IR 保全记录][role-ir]。

普通单位角格、没有显式 `<th>` 的计量头以及 P01/P02 完整载荷缺括号的单位绑定均未退回业务前缀。除 P06 外，实际分组变化只有两类：P01/P03/P04/P05/P07/P08 各一条“权益及负债总计”在“负债总计”后退出负债组；P02 三条权益记录在“资产总计”后退出资产组。逐条检查了这些变化自己的原生行带与实际 Final，没有发现新引入的分组或单位回归。P02 合写的权益行名、`2月31日`、缺位金额等原生错误继续保留，不宣称恢复了正确业务答案；完整差异见[分组对照][role-groups]。

既有多层表头、共享单位、多分组、分组切换、无标签小计、空白角格、续表与相邻表边界回归，加上本次少量必要的同格正反例，共 11 个相关测试模块在禁用父 conftest、plugin autoload 并拒绝原件、参考、媒体和网络 I/O 的局部审计下通过 727 项，边界违规为空，实际代码身份未变。合写片段的两种先后顺序、两种局部未知方向、普通网格正文、相邻表不继承、原文重叠、locator 改绑、外表 occurrence、错误行范围及已证分组脱离均有独立反例；测试明细与实际参数见[回归记录][role-regression]。这些是软件验证，不计为额外真实样本或完整财务验收。

当前能力限定在有原生表头、实际文字边界和各自范围证据的片段；没有扩大到任意正文拆角色、缺失金额恢复、未知合并格关系或全部财务层级。八组转换与媒体交付状态保持：P06/P07 的 conversion 为 completed，其余六组 partial，八组 delivery 均为 partial；本轮不据此给出完整质量等级。原 Native、Expected、正式分母、计分合同、原始成本及旧工件均保留，未解析 PDF、未调用 OCR/VLM、未运行任何新评分或服务/GPU/TTS 操作。所有改动留在工作区，未提交、未推送，等待用户审阅。

[historical]: ../../runs/lite/service/development/cross-document-normalization-phase12/final-binding.json
[inputs]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/inputs.json
[cases]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/casebook.json
[lineage]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/field-lineage.json
[negative]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/negative-evidence.json
[scores]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/scores-index.json
[limits]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/readback-limits.json
[before]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/before-unit-context-fix.json
[repair]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/repair-impact.json
[execution]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/repair-execution.json
[summary]: ../../runs/lite/diagnostics/native-final-value-s5-20261118/research-summary.json
[role-inputs]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/inputs.json
[role-execution]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/execution.json
[role-comparison]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/comparison.json
[role-values]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/p06-74-values.json
[role-principal]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/principal-values.json
[role-retention]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/retention-and-notes.json
[role-groups]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/group-differences.json
[role-regression]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/regression.json
[role-final]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/after/P06/huawei-statements-p068-070/final.md
[role-ir]: ../../runs/lite/diagnostics/s5-cell-role-scopes-20261118/attempt-02/ir-preservation.json

## 11. 表头分段、具名小计与实际下载（2026-11-19）

本轮对照起点为第 10 节的 `attempt-02`，软件 ID 为 `22f5a0a17c9a12b314fd1ec6b7dc8d0931111176d6b04b9b34aa28c3d2c154c4`。新版八份实际 Final、Semantic、Storage 和软件快照独立保存在 `validated-02/after/`，软件 ID 为 `926db2c1e78cf1c46d5e7eff9cd20b8e6c051e7c7a14a6188b2e777f0e0dc0b9`。P01 至 P08 逐个串行重放，每次仅挂载本配置的保存 Native 和执行元数据，使用 8 CPU、8 GiB、禁用网络及 GPU 的隔离环境。开发重放与此次交付分目录留存。[基线文件及校验值][scope-baseline]、[新版逐配置执行记录][scope-execution]、[下载八份实际 Markdown][scope-finals]。

| 比较对象 | 基线中的实况 | 新版交付及来源 |
| --- | --- | --- |
| P06 角格与 74 个金额 | 最初整格传播为业务上级，缺 74 个单位；到本轮基线已拆出单位和资产，74 个单位已建立 | 原生完整文字仍为 `（人民币百万元）资产`。单位取字符区间 `[0,8)`，两日期金额列共用。资产取 `[8,10)`，覆盖本表第 1–18 数据行。74 个值分别比对原 HTML 的金额、日期、行名、附注、分组源格以及 Final 位置 |
| P06 七对同名行 | 大组内同名项目共 28 个日期金额，仅靠名称和附注无法区分两个借款记录 | 以原生标题、同级具名小计及各自连续区间确定子组。七对逐笔保留自己的源格，负债与权益各自独立，跨组总计仍有自己的两笔日期金额、单位 |
| P02 利润表残缺角格 | `（人民币百万` 成为 22 条记录的共同业务上级 | 角格完整残片原地保留一次，22 条错误前缀全部消失。六个收入、销售成本、销售毛利年度金额继续没有单位来源 |
| 现有金额与实际字节 | 1,770 个值槽，含附注和空格位；八份正文各自持久化 | 相同 Native 和 IR 源格，逐槽核对原文和 Final 位置。633 槽的关系发生改变，567 槽在七份财务状况表增加具名子组，P02 的 66 槽撤除残片上级。其余 1,137 槽的这些关系相同。八份 Storage 正文各自与对应 Final 字节一致 |
| 已有可证单位 | P01 现金流表 20 个，P02 财务状况表 65 个；八组固定三项主指标 48 个金额中 42 个有单位 | 所有 85 个旧绑定逐个保留来源和实际正文位置。48 个金额全部交付，42 个有完整单位，六个源格残缺的金额继续局部交付 |

[含来源和正文行号的 74 行 CSV][scope-csv]、[原 HTML 独立逐格核对][scope-raw]、[P06 每笔前后关系][scope-p06]、[七对同名行的 28 个金额][scope-pairs]、[P02 残片和正文位置][scope-p02]、[85 个既有单位][scope-protected]、[48 个主指标][scope-indicators]、[1,770 槽逐项去向][scope-slots]、[633 槽关系变动明细][scope-changes]。

P06 两笔借款的附注均为 `24`，日期列从左至右均为 `2024年12月31日`、`2023年12月31日`。下表行号为原生物理表的零基行号，表头在第 0 行。各行覆盖关系在读到金额之前即可从标题及具名小计确立。[P06 实际 Final][scope-final-p06]。

| 原生记录 | 日期金额原文（2024 / 2023） | 实际打印路径与原生依据 |
| --- | --- | --- |
| 第 24 行，借款 | 237,508 / 291,688 | 负债 / 非流动负债 / 借款。负债标题在第 23 行，第 28 行“非流动负债合计”界定第 24–27 行 |
| 第 29 行，借款 | 27,363 / 16,726 | 负债 / 流动负债 / 借款。第 28 行结束上一组，第 37 行“流动负债合计”界定第 29–36 行 |
| 第 39 行，权益及负债总计 | 1,290,149 / 1,263,597 | 独立记录。两笔金额保留日期及同一角格中的单位，组路径为空 |

24 份真实物理表中，一份触发同格单位与业务分组拆分，七份有证据确立具名小计子组。S5 中多段换头和明确跨页继承的观察数均为零。受控数据中的后段借款 `7` 确实打印 `2023年` 和 `USD millions`；局部新表头只建立已证列，明确续表保留上页角色源格，普通年份数据、无标签小计和相邻表均有反例。年份挪用、已结束分组、错表、缺必需单位和错误片段有独立拒绝测试。普通含单位的列头保留完整列路径，年份与单位分别指向已打印片段。[真实表结构清单][scope-physical]、[受控 Native、Semantic 和实际 Markdown][scope-controls]、[多层列头与反例][scope-multilevel]、[相关软件回归][scope-regression]。

对 P03 的实际 Final 通过正式 Markdown 读回入口进行局部诊断。收入、销售成本和销售毛利的两年金额均能读到各自打印的单位和日期，两条收入还能关联本记录的独立附注 8。此项可见改善来自读回器，P03 原文此前已交付这些字段。[六个字段的读回依据][scope-p03]。

八份正文各有可独立解压的交付包，含 `result.md`、`manifest.json` 及实际交付的资产。八份 S5 样包的已交付图片数均为零。P06、P07 有媒体声明但图像交付未证，两者公共转换完成、交付状态均为 `partial`。其余六组保留各自局部转换状态。沿现有同步、异步入口，以保存的 P06 正文作为识别结果经过队列、任务库和存储，分别核对响应、下载、持久化和 ZIP 中的字节。重复图片、缺失或损坏资产、旧缓存和重复下载由含已知图片字节的受控请求验证。使用的是进程内 API，正式服务和新增原件运行另行验收。[八个样包及校验值][scope-bundles]、[两种 HTTP 入口的实际读回][scope-api]、[S5 前后及状态汇总][scope-comparison]。

S5 的 P02（表内关系未决）、P03（阅读顺序未证）、P06（图片交付未证）也分别经过同步和异步任务，六次下载均保留对应警告、部分完成状态及持久化字节。另提供一个受控图片样包，其中两处引用共用同一份可离线读取的 PNG。P06 三个独立页码已从正文去除，公司名称和年度报告文字仍出现于页眉页脚位置；整份文档的装饰文字清理尚未通过验收。另核对了已保存的四份历史输出以补充 S5 没有的内容结构，腾讯 27 处列表项和华为编辑页三处图题有实际正文落点，华为目录三个布局容器保留在审计，平安三处未决网格局部保留。这四份沿用各自旧软件身份。[内容最终去向][scope-content]、[P02 任务读回][scope-api-p02]、[P03 任务读回][scope-api-p03]、[受控含图离线样包][scope-image-sample]。

本次针对表格与读回的 735 项回归通过。重新审查统一 source-only 清单的变更与依赖后，完整入口在冻结测试源码下通过 4,528 项，禁止 I/O 的触发次数为零。首次统一执行暴露旧的手写样本目录计数仍固定为 23，最终断言分别保护历史样本及新增选段。此前的执行和中断记录保留，最终绑定记录同时核验 64 份早期工件、八份新版正文和存储、受控 HTTP 结果及独立来源检查。[统一回归与 I/O 记录][scope-alltests]、[测试源码及依赖审查][scope-review]、[最终版本与工件校验][scope-bind]。

[scope-baseline]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/baseline.json
[scope-execution]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/execution.json
[scope-finals]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/s5-finals.zip
[scope-final-p06]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/after/P06/huawei-statements-p068-070/final.md
[scope-raw]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/p06-native-html-audit.json
[scope-p06]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/p06-74-values.json
[scope-pairs]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/p06-seven-pairs.json
[scope-p02]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/p02-local-header.json
[scope-protected]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/protected-unit-bindings.json
[scope-indicators]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/principal-values.json
[scope-slots]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/value-slots.json
[scope-changes]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/relationship-changes.json
[scope-physical]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/physical-table-coverage.json
[scope-comparison]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/comparison.json
[scope-regression]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/regression.json
[scope-p03]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/p03-six-markdown-fields.json
[scope-bundles]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/bundles.json
[scope-api]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/api-saved-final.json

[scope-content]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/content-destinations.json
[scope-api-p02]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/api-saved-final-P02.json
[scope-api-p03]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/api-saved-final-P03.json
[scope-image-sample]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/controlled-image-sample.zip
[scope-csv]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/p06-74-review.csv
[scope-controls]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/controlled-tables/index.json
[scope-multilevel]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/controlled-tables/multi-level-and-negative-controls.json
[scope-alltests]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/validated-02/regression-approved.json
[scope-review]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/source-only-review-bound.json
[scope-bind]: ../../runs/lite/diagnostics/s5-table-scopes-and-delivery-20261119/final-binding.json

## 12. 同一份已交付正文的评分器读回

本轮直接读取第 11 节交付的八份持久化 Markdown。旧程序和新程序读到相同的正文文件，各文件的 SHA 随逐值记录保存。先从正文建立金额、日期、单位及附注，再按上轮已核对的来源和打印位置验证。两次读取均未运行解析后端或转换 Final。[旧版逐值读回](../../runs/lite/diagnostics/scorer-issue-repair-20261119/public-baseline.json) [新版逐值读回](../../runs/lite/diagnostics/scorer-issue-repair-20261119/public-delivered.json)

| 同一批实际正文 | 旧评分器 | 新评分器 |
| --- | --- | --- |
| P06 资产负债表的 74 个非空日期金额 | 0 条读出完整绑定，完整日期字段未被识别 | 74 条逐项通过金额、期间、单位、币种、单位打印位置、业务路径和附注检查 |
| P01 现金流表的 20 个单位引用 | 20 个金额和期间可读，0 个读到单位 | 20 个金额及其单位、单位文字位置和期间全部对应 |
| P02 资产负债表的 65 个单位引用 | 无效日期旁的 65 个金额都未读到 | 65 个原值及其单位全部对应。65 个“2月31日”都保留自己的原文和位置，有效日期绑定为 0 |
| 八组收入、销售成本和销售毛利的 48 个年度金额 | 已有交付对照保留全部 48 个实际值 | 八组正文均读回对应金额和日期。42 个有完整单位来源，另 6 个仍保留无单位来源的状态 |

对同名字段的受控试验只交换整组顺序、替换归属、调换金额或替换附注所指文件。修复后，四笔正确金额在两个组换序后仍逐笔判对。两笔同值记录被挪入另一个组时，只有原组的两笔判对。把附注所指的财务报表换成年度报告，该条附注的业务得分由 76.19% 降至 0，邻近的两笔正确金额均保留满分。[旧结果](../../runs/lite/diagnostics/scorer-issue-repair-20261119/controls-before.json) [修复后结果](../../runs/lite/diagnostics/scorer-issue-repair-20261119/controls-delivered.json)

复核中发现第一版修复给八个现金余额重复展开了同一处“人民币百万元”，多出 48 个文字字符和 16 项单位、币种关系。最终实现把限定语绑定到已经计分的字段，每个金额仍须通过自己的单位、币种和业务归属检查。S5 的三层分母前后均为 4,572、603、162。现金分组标题的文字和来源保持，语义角色从普通文字改为定位分组。每项原职责及因分析关系增加而顺移的编号均可核对。[计分对象对照](../../runs/lite/diagnostics/scorer-issue-repair-20261119/denominators.json)

列表归属和同名字段的评分器修改完成后，用同一版程序再次读回上述八份既有正文。P06 的 74 个金额及七个逐值核对项全部通过。P01 的 20 个、P02 的 65 个单位引用仍能定位到正文。P02 的 65 处无效日期继续保留原文。48 个主指标金额逐项对应，42 个完整单位来源和 6 个缺口均与先前一致。本次读回使用原有持久化文件，其字节和此前采用的文件逐份相同。[逐值读回和正文文件标识](../../runs/lite/diagnostics/list-field-scope-20261119/verified/public.json)

### 12.1 从八份持久化 Markdown 独立建树

同一版评分器逐份读取第 11 节留存的实际 Final，仅用各份 Markdown 生成候选文档 AST。八份树共 3,855 个内容节点，其中 57 个对应空白单元格。其余 3,798 个节点的文字与原始位置、57 个空格各自的来源均已从本份正文读回核实。八个文件的 SHA 与第 12 节的输入逐一相同。[八份候选树及来源文件](../../runs/lite/diagnostics/dual-ast-20261119/after/final-trees/index.json)

P06 的 74 个金额逐项核对金额、期间、业务路径、附注、单位、币种和打印位置，74 项均有原先的绑定。P01 的 20 处和 P02 的 65 处单位来源逐项可追；P02 这 65 处的残缺日期继续保留原文字段。八配置的六个主指标合计 48 笔都有原值和期间，42 笔能追到完整单位。此次验证的是评分器如何读已交付的正文，没有产生新的 Final 或 Lite 分数。[实际正文逐值读回](../../runs/lite/diagnostics/dual-ast-20261119/after/s5-markdown.json)

Expected 列表的两个“借款（附注24）”现在也保留为可展开的记录。每个记录分别带有自己的完整业务路径、附注 24 的原文跨度、两条日期和每个日期的金额。共享单位“人民币百万元”回指原单位说明，币种还可定位到其中的“人民币”。每笔金额仍由原年度字段计分。两笔同名记录的字段和原文位置可以并列检查。[两笔借款的 Expected 子树](../../runs/lite/diagnostics/dual-ast-records-20261119/accepted/expected-records.json)
