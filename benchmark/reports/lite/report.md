# MO-Parse Lite：暂定容量边界与固定18份独立验收

容量对应边界已完成验证；固定18份已完成独立审查，其中18份通过、0份退回、0份受外部条件阻塞。18份中13份新通过，5份发现并修复实现缺陷后通过；已在更新版本通过再复验0份，未审查0份。原华为、顺丰、中石化三个基线在最终源码及唯一current下重新通过。这里的通过是document_ast/1独立来源验收，完整质量成绩继续暂停。

## 固定范围与逐项结论

接手HEAD为 `3cc3a5c8b22f64cd428faf7b8cd7d74cbfce6f6e`，工作区干净，两个工程入口均指向/opt/moparse。实际索引中21份比较责任完整，原独立来源验收有效集合为3份，差集准确恢复为18份；旧Oracle、受测源码及测试身份与接手文件相符，没有过期验收或重复成员。旧验证记录的git_head早于接手提交不单独使其失效；本轮最终记录使用实际脏源码和断言身份。固定集合在实施前保存，未修改manifest、selection或正式样本集合。

[固定集合及完整身份](../../runs/lite/requirements/validation/actual-source-diagnosis.json)位于fixed_sample_acceptance：保留接手原始来源、选段、要求及能力摘要，逐份final_acceptance绑定当前源码、生成视图、覆盖摘要、实际case、义务、分析限制及同版能力证据。[手写断言](../../../tests/validation/lite_fixed_source_assertions.py)先依据完整授权文字建立，随后调用生产编译器；[独立入口](../../../tests/validation/lite_source_oracle.py)实际检查483个授权来源及500个case，其中17个case单独验证选段内的空白分隔义务。全部已解释正文也参与审查，未使用真实expected作candidate自比较。

| sample_id | 完整审查来源数 | 当前合同B/L要求数 | 本轮结论 |
| --- | ---: | ---: | --- |
| catl-impairment-investment-debt-risks-p064-066 | 16 | 11/25 | 新通过 |
| catl-industry-market-overseas-risks-p053-057 | 42 | 32/75 | 新通过 |
| catl-ip-newbusiness-finance-risks-p058-063 | 42 | 30/71 | 新通过 |
| catl-listing-ownership-diagrams-p178-180 | 20 | 13/28 | 新通过 |
| catl-nev-battery-markets-p127-132 | 80 | 66/138 | 修复后通过 |
| catl-power-market-materials-drivers-p133-136 | 42 | 34/66 | 修复后通过 |
| catl-recycling-emerging-entry-barriers-p144-147 | 28 | 22/42 | 新通过 |
| catl-storage-renewables-markets-p137-143 | 65 | 51/111 | 修复后通过 |
| hkex-board-portraits-p030 | 14 | 0/14 | 新通过 |
| hkex-organisation-photo-p028-029 | 3 | 0/2 | 新通过 |
| hkex-overview-photo-p005-006 | 3 | 0/2 | 新通过 |
| huawei-front-p002-003 | 28 | 20/45 | 新通过 |
| huawei-open-ecosystem-p058-061 | 45 | 36/79 | 修复后通过 |
| huaweitech-network-divider-p020 | 1 | 0/0 | 新通过 |
| nhu-related-party-audit-p002-003 | 20 | 14/30 | 新通过 |
| pboc-cover-p001 | 4 | 3/8 | 修复后通过 |
| sf-brand-award-callouts-p034 | 15 | 11/22 | 新通过 |
| sf-supply-chain-operating-efficiency-p025-026 | 15 | 10/22 | 新通过 |

每份的可复查执行证据见[oracle-validation.json](../../runs/lite/requirements/validation/oracle-validation.json)的results[sample_id].cases，case身份使用source::sample_id::L原始行。requirements、obligations及analysis limitations在实质来源断言通过后按物理来源关联；派生B/L编号不是语义预期。标题、图题及分隔页的B不适用具有明确来源角色依据，表中0不表示取得业务或图像理解分数。图片只检查授权文字、图题及已有范围，不进行图像语义解释。

## 容量对应的最终行为

问题已在完整read_expected、要求图、来源审计、候选独立读取、grade_layers及validate_evidence链路复现。两项“董事會秘書接受專業培訓”“董事會秘書參加專業教育”竞争唯一弱候选“董事會秘書進行職業訓練”时，旧结果为先项unresolved、后项missing；交换处理顺序使错误随之交换。最终两项均为unresolved，B分母保持2，相关层不发布成绩，证据复核拒绝不完整发布。[复现记录](../../runs/lite/requirements/validation/document-reproduction.txt)同时保留修复前及最终受测身份。

compare_document_ast分别记录已确认、暂定及未确定的对应。唯一弱检索不排他消费跨度，多个未确认要求的竞争保留原始跨度和竞争身份；只有独立确认的对应及整个可检查范围的完整排他覆盖，才能证明其他要求缺失。已确认身份的内容即使conflict或unresolved仍保留位置，正确值不参与消歧。grade_document_content同步使暂定位置的L归属及顺序保持未决；实际阅读顺序始终来自候选块序及块内位置。

受控反例检查固定原文顺序、仅改变求解器内部遍历后的每个稳定requirement_id，连同最终outcomes、blockers、分母和完整证据重放；另覆盖精确身份与弱候选竞争、身份确定但语义未决、独立双候选、可证明的真实缺失、重复身份不同数值、空范围及普通错值。原1:1、1:N、N:1、有界N:M、同块反序、结构屏障和混合类型责任继续通过。合同定义见[评测任务](../../evaluation-tasks.md#文档-ast-与内容比较)，合同版本未改变。

## 独立审查发现的实现缺陷

| 授权来源 | 发现及修复 |
| --- | --- |
| PBOC封面L3、L5、L7 | 三个独立名称被拼成虚假的report命题；保留三段完整内容及其正确标题范围，移除虚构报告关系。 |
| 华为开放生态L1533、L1534、L1541、L1542 | 未解释的冒号叙述被当成标量答案；以原始标签、全文及来源责任保留陈述。 |
| 宁德时代新能源市场L1749 | 多分句定义附注被当成标量；完整保留两个渗透率定义及原始范围。 |
| 宁德时代动力市场L1938 | 新应用场景叙述被当成单个标量；完整内容承担技术条件、应用场景及需求描述。 |
| 宁德时代储能市场L2045 | “表後儲能”的末字能被识别为能力模态，主体截断为表後儲；保留完整主体、主要限定及两项包括成员，不添加能力模态。 |

共享修复还将连接分析的绝对跨度投影回各原始片段，完整内容不借用首片段身份承接其他来源。财务列声明、封闭标量记录及年度序列的尾随原因继续由已有读取器负责。全量投影核对暴露的浦发L127、L130、L131年度序列拆分回归已修复，两个实际年度位置、变化值及原因保留；这些数值均来自原文，没有反算。句末上标脚注的连续读取边界另有独立正反例，原字及脚注仍进入T。

## 固定投影、基线与集合外影响

固定18份中下列五份的B/L要求投影变化已随完整来源Oracle重新验证；其他13份比较要求数保持。PBOC移除一项跨三来源的虚构命题，改由三份完整内容负责；华为及宁德时代两个标量正文修复补回所属文档范围责任；储能样本移除两项虚构能力关系。分析视图节点数不等于T字符分母，也不等于当前合同比较分母。

| 固定成员 | 接手B/L | 当前B/L |
| --- | ---: | ---: |
| catl-nev-battery-markets-p127-132 | 66/137 | 66/138 |
| catl-power-market-materials-drivers-p133-136 | 34/65 | 34/66 |
| catl-storage-renewables-markets-p137-143 | 51/113 | 51/111 |
| huawei-open-ecosystem-p058-061 | 36/75 | 36/79 |
| pboc-cover-p001 | 1/3 | 3/8 |

| 原成功基线 | 分析T/L/B | 当前合同B/L | 最终独立验收 |
| --- | ---: | ---: | --- |
| huawei-operating-results-p062-063 | 407/575/122 | 122/575 | 通过 |
| sf-cashflow-assets-liabilities-p040-041 | 585/708/133 | 133/708 | 通过 |
| sinopec-finance-governance-p025-036 | 910/1284/272 | 324/1352 | 通过 |

原三份Oracle的实质断言未改写。A/B/C保持顺丰三项声明及221项计量、华为L1586三项业务要求、平安L298首句一项命题和4条关系的原有payload。中石化仍为semantic_complete=False，不宣称通用中文语法解析完成。[baseline-preservation.json](../../runs/lite/requirements/validation/baseline-preservation.json)绑定当前执行证据。

173份的原始授权来源数组、selection及原始传输选段逐份保持，五个输入范围保持原身份；128份派生来源数组未变，122份分析投影身份未变，128份规范业务payload及关系未变。全部283处分析B减少的来源均复核了被替代标量跨度的完整内容归属，PBOC的跨三原始来源单独关联其实际来源case；既有完整类型化财务要求丢失0。完整逐来源前后内容、范围和变化保存在actual-source-diagnosis.json的fixed_sample_acceptance.final_rebuild_comparison。这些集合外回归检查不提供新增样本独立验收。

公共修复使集合外11份比较责任完整，清单仍独立保存在上述诊断，未补入固定集合，也未标为独立验收通过。集合外四份中另撤回5项此前暂定的完整内容责任：BIS财政生产率L838、L948，BIS政策框L674，IEA基础设施L588及IEA训练能耗L730；连接分析的未决来源尚未得到完整局部归属证明。四份临时B/L要求数分别为46/152到44/148、46/128到45/126、15/42到14/40、10/25到9/23。原文、选段、目标及具体阻塞义务全部保留；这些较小的临时目标集没有取得计分分母批准。它们继续由软件覆盖门禁阻断，本轮未展开其完整选段修复。

## 全局门禁与同版证据

以下维度可以重叠，不相加计算质量或覆盖率。

| 维度 | 当前数量 |
| --- | ---: |
| 编译来源或文档结构不完整 | 0 |
| 比较义务或未决责任仍有未覆盖 | 141 |
| 已声明能力缺少同版受控证据 | 0 |
| 比较责任完整但缺少独立样本验收 | 11 |
| 已按合同独立来源验收 | 21 |
| 仅保留语言分析限制 | 27 |
| 含既定输入范围问题的视图 | 5 |
| 既定输入范围目标 | 5 |

全局仍有141份比较责任缺口及11份完整要求待独立验收；真实格式读取、全范围保存输出诊断与实际回放均未验收。40种受控能力证据及P01–P08标签参数化不等于八种原生交付链通过。三个全局门禁继续not_passed，未生成实际worker回执，完整质量成绩继续暂停。五个输入范围没有与软件覆盖问题合并；Alibaba L2353的两种附着及未经批准的多解释合同保持原状态。

[完整受控回归](../../runs/lite/requirements/validation/software-validation.json)为 `4393 passed in 229.46s (0:03:49)`，180个测试文件，源码与183份测试及支撑文件的身份在执行期间均保持。tests_sha256为 `007259b67a59db877e278b76d5e71e71e209f4536d5c25819c1d93e87ce77a57`，software_id为 `61575a912d5d17e2151ffd1949c1541a0f3a2705c4539942d3a75a386433e29d`。当前HEAD仍为接手提交，没有提交或推送；新手写断言及测试已纳入Git跟踪。

[173份JSON/XML](../../runs/lite/requirements/current/index.json)在同一源码下以16个分析进程重建，耗时140.69秒，来源完整性失败0；索引SHA-256为 `b928b680627dbe1872819da6772414c6a2b36cb2da333a594906a589e6f80b67`，状态structure_blocked，编译退出码2对应集合外未完成责任。最终[独立来源运行记录](../../runs/lite/requirements/validation/oracle-validation.json)SHA-256为 `779f26a62271388ca98e30e931d585a2ca7f65e391bfe10ca1369b06cf848733`；21份全部重新编译并核对已安装current，视图、覆盖、选择、义务和能力用例绑定通过。旧生成视图已删除。

最终绑定命令为 `PYTHONPATH=/opt/moparse .venv/bin/python tests/validation/lite_source_oracle.py --output benchmark/runs/lite/requirements/validation/oracle-validation.json --diagnosis-output benchmark/runs/lite/requirements/validation/actual-source-diagnosis.json`。完整测试命令与逐文件身份见software-validation.json；regression.xml、comparison-validation.json、mutations-validation.json保留实际执行及重放入口。续做入口为[expected output optimization](../../../docs/engineering/prompts/expected-output-optimization.md)。

Ruff与非语料Markdown政策检查通过。一次未设路径排除的git diff空白检查误包含已跟踪报告，随后按规定排除语料、数据包、参考裁定、运行与报告目录重新执行；没有语料输入参与通用检查，来源验收结论不依赖该空白检查。

本轮只进行source-only软件工作及独立合成候选比较。canonical expected、映射、selection、页包、语料、有效native、历史交付和原始成本保持只读；未读取原始PDF、图片或字层，未运行OCR、VLM、模型服务或裁判、实际候选比较、真实回放、正式保存输出评分、推理、GPU/TTS/在线服务操作、部署、公开API修改、提交或推送。原生横向比较与P07/P08真实历史baseline/current交付配对继续分开。

## 原始处理成本

以下为原始执行观测，单位为秒；不含本轮source-only软件耗时，没有重新运行解析或后处理。数值未改写或补零。原生边界为worker开始处理到原生产物及忠实导出就绪，初始化/预热单列。quality800为800输入页的一次执行，perf80为相同80输入页的三次执行；各轮值为原case处理时长之和，不是整批作业首尾墙钟时长，重复轮次不增加独立文档样本。每组native的173次quality执行及84次perf执行均记录completed，原始时长没有缺测；这是执行状态，不是内容正确率。逐轮值、初始化/预热、资源范围及缺测政策见[原始成本数据](data/processing-cost-summary.json)。

| 原生组 | quality800 | perf80中位数（最小–最大） |
| --- | ---: | ---: |
| P01 | 1565.35 | 199.90（199.42–201.00） |
| P02 | 1478.30 | 186.33（186.27–187.19） |
| P03 | 11576.99 | 937.51（893.87–1001.96） |
| P04 | 11826.90 | 778.31（778.19–967.77） |
| P05 | 2908.12 | 276.46（275.32–278.23） |
| P06 | 1619.34 | 202.44（202.14–202.87） |
| P07 | 2411.70 | 276.90（274.57–279.99） |
| P08 | 3327.53 | 311.49（310.53–316.18） |

服务表保留既存实际正文的独立CPU后处理成本；本次八组新回放尚未执行，不继承这些时长为新实现测量。后处理成本不与native相加或解释为新的端到端时长。右列为quality800实际执行状态，partial和警告均保留，不转为质量分数或采用依据。

| 服务后处理组 | quality800 | perf80中位数（最小–最大） | completed / warnings / partial / failed |
| --- | ---: | ---: | --- |
| P07 baseline | 216.09 | 28.02（27.74–28.40） | 126 / 16 / 31 / 0 |
| P07 current | 216.84 | 28.04（27.91–28.22） | 126 / 16 / 31 / 0 |
| P08 baseline | 194.05 | 28.91（28.82–29.27） | 127 / 14 / 32 / 0 |
| P08 current | 181.99 | 27.37（27.18–27.39） | 128 / 14 / 31 / 0 |

原生配置的CPU预处理分配为8核及8GiB内存、推理进程分配为4核及20GiB内存，自有评测GPU显存预算16GiB；原服务后处理为8核及8GiB内存、无GPU、并发1。原始执行存在TTS共驻和未受控制的活动：起止持久任务计数71至76，观测到5个新增任务；短调用可能没有被这些观测捕捉。不得据此宣称GPU独占或TTS空闲。数据分别保存分配与实测使用、RSS/cgroup峰值及观测覆盖；未记录的GPU指标保持未知，单页allocator峰值不等于整个设备占用。本轮16个CPU分析进程仅用于source-only要求图重建，不改变原执行资源与时长。
