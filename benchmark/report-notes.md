**已部署并选定 V7：Advanced＋TXT＋vLLM 双并发处理原生页，Docling 2.139／TableFormer V1／matching=False／PyPdfium 独立核验表头与来源，GLM-OCR＋SDK 方向预处理处理扫描／混合页。完整550页真实HTTP已测完，新生产159页的传输、GFM、原问题功能及来源保全验收通过。**

正式API于03:39:49 UTC切换至受测同一V7镜像，保留旧V6容器、37条旧记录和250份旧输出／资产SHA，模型worker／provider未重启。新生产159页于03:40:23–04:01:23 UTC完成实际HTTP捕获，04:03:12 UTC最终只读收据通过；此前03:40:07仅为控制器身份／设置准备阶段。
[最终实际部署／完整159页收据](evidence/table-v7-production159-final-release-20261018.json)。
项目实体目录为 `/opt/moparse`，旧目录为兼容符号链接；上游仓库保持原历史改名。

| 同一 10 份完整 PDF、502 页 | 核心原值／完整期间 | 原值及唯一行·严格原字 | 完整列义·严格原字 | 固定正文／结构 | 上传→保存 MD |
| --- | ---: | ---: | ---: | ---: | ---: |
| 旧线上 Docling 2.139／V1／False／PyPdfium＋GLM，同部署历史 HTTP | 各 209/209 | 372/402 | 326/402 | 16/40 | 22.50 分钟 |
| 本轮 Advanced＋TXT＋GLM | 各 209/209 | 351/402 | 297/402 | 40/40 | 61.94 分钟 |
| 本轮选定 Advanced＋TXT＋原件核验 V7 | 各 209/209 | 351/402 | 297/402 | 40/40 | 75.56 分钟 |

![完整 HTTP 的质量与 502 页实际耗时](assets/full-http-comparison.svg)

V7 的 502 页上传→保存 MD 为 **4533.361 秒**，排除 Office 与附件下载；完整 504 页含 Office／附件为 4549.147 秒。
Office 衍生两页三组均 6/6，单列于图；质量分母有交叉，不能相加或称整份文档准确率。
旧 502 页是历史 180W，本轮为 220W，预热／共享负载不同；展示实际成本，不推算受控加速倍数。
[本轮完整504页](evidence/table-v7-regression504-20261018.json)、[逐项402三方差异](evidence/table-v7-402-source-differences-20261018.json)、[图表来源和时间边界](assets/full-http-comparison.sources.json)。

**为何选择及代价。** 选择依据是正文完整性、源表头／合并格和来源关联优先：PDF 固定正文／结构由旧线上 16/40 提高至 40/40，含 Office 的固定条件 46/46、额外条件 4/4。
代价是耗时明显增加，金融严格原字分数低于旧线上；标签／表头全半角标点也会失分，保持原判，不用印刷等价诊断改分。
另有两处真实金额分隔符错误：134 页原件第 54 页 `1,465,510,368.44` 被读为 `1,465.510,368.44`，第 56 页 `1,342,788,515.86` 被读为 `1.342,788,515.86`。
两错从纯 TXT 延续至 V7，另两项恢复分开列，不能抵消错误；本轮配置并非全面更准或更快。

**原问题的正式服务新验收（31页）。** 新线上两份完整27／4页原件均使用auto、未设置unit_range，已独立核实实际正式URL、受测同一镜像与生产卷。浙江出版原件的两组完整期间表头分别保留，资产／收入／归母净利润／每股收益及元／股单位对应正确；筹资表完整44个位置、31个非空源格、7个合并跨度、万元和八行标题锚点保留。
正常续表完整头只出现一次，逻辑合并、真实重复头去除、来源页／来源行映射与跨度正确。HTTP、持久化GET和实际生产磁盘Markdown字节一致；独立31页源件证明与整体159页最终收据分别保留。
原字严格检查仍保留财务 3 格、筹资 4 格、正常续表 2 格宽度差异，功能检查与严格原字分开。
[V7 新生产31页独立源件与身份验收](evidence/table-v7-production31-original-issues-independent-review-20261018.json)、[候选31页源件验收](evidence/table-v7-original31-original-issues-independent-review-20261018.json)、[完整原件表面诊断](evidence/table-v7-source-surface-20261018.json)。

**新生产159页。** 7份完整原件实际为6 completed＋1 NASA partial，传输均完成，quality_fully_resolved=false；约定功能验收通过不等于原字严格条件全部通过或所有源件准确。原始严格结论仍false，9格宽度差异保留。
固定46项中的实际覆盖16/16、另外30项未覆盖；Office6/6、末7页24/28与本次候选相同，未添加新独立测试结论。
整次上传至MD／事件／资产捕获为**1260.202秒／21.003分钟**，逐件上传→保存MD合计1259.247秒。新生产全部159页可见正文与候选相同，182张表格的跨度／头范围／来源均相同，仅一格全半角右括号不同；119页p14仍为GFM、16spans及正确来源映射，源16列／模型17列错误仍未修复。
[新生产7件逐表／正文比较](evidence/table-v7-production159-candidate-public-consistency-20261018.json)、[完整159页资源与逐件时钟](evidence/table-v7-production159-resource-stage-observation-20261018.json)。

**仍未解决的源件错误与 unknown。** Census 第 6 页七个年龄行在旧线上和本轮都被折成一行；V7 末三格 `22／23／3` 仍不代表原件的七行数值，不能把 V6 重复数字减少称为源件恢复。
原图确认 WHITE 到校为 `2／3／14／2／虚线／虚线／虚线`，OTHER 两列仅 7–13 岁行各 `3`；原 SDK 区域响应未保存，首次出错层未知。
Census 地名原件 `Tutuila` 在 V6／V7 均被误读；130 页章号原件 `35010510007235`，V7 为 `510101510007235`，仍错。
V7 签章区又多一份行内姓名，与源件两处姓名呈现不符；28 页原件的红色篆体章 OCR 两版也均错，未发现对应普通印刷正文新增遗漏。
[年龄表源件与历史输出](evidence/source-v6-Census-page6-source-and-baseline-review-20261018.json)、[V7 地名与 IRS 空白拓扑](evidence/table-v7-Census-place-and-IRS-blank-topology-source-review-20261018.json)、[V7 签章原件复核](evidence/table-v7-130-pages11-12-signature-seal-source-review-20261018.json)、[篆体章复核](evidence/table-v7-28-page4-scan-seal-source-review-20261018.json)。

119 页第 14 页的新真实 HTTP 已无 raw HTML：原保存模型 503 个锚格、16 个跨度和来源 14:1–33 均保留为 GFM；但**原件16列、模型17列的拓扑错误仍在**，完整表头列义明确 unknown。
IRS 空白表格拓扑在两次调用间变化，五个非空锚格文字／坐标相同，空格边界未经独立源标注，不据列数判精度升降。
NASA 时间轴不再公开无源生成表格，保留原图和 exact PDF 字层，API **partial／结构 unknown**；来源保全 B 为 11/11，原件物理结构 A 仍 8/19，不声称恢复甘特语义。
[V7 119页实际格式与剩余模型结构错误](evidence/table-v7-119-page14-real-HTTP-GFM-source-review-20261018.json)、[NASA 实际末7页与 A／B](evidence/table-v7-fresh7-20261018.json)。

**完整550页结果。** 17 份完整输入实际为 16 completed＋1 NASA partial，全部传输与三组 GFM 检查通过，quality_fully_resolved=false。
原39页为 31/36、393.952 秒，末7页为 24/28、100.407 秒；与旧基线逐断言相比，旧通过项变失败／未知均为 0，分别恢复7项／5项。
这些样本全部已暴露，只作为开发回归；未标注区域的上述实际错误仍单独保留，不能由固定分数掩盖。
[原39页](evidence/table-v7-holdout39-20261018.json)、[39页逐条件差异](evidence/table-v7-holdout39-baseline-diff-20261018.json)、[末7页逐条件差异](evidence/table-v7-fresh7-baseline-diff-20261018.json)。

V6→V7 全504页的原670张公开表格矩阵／跨度／来源均完全相同，新增一张由 raw HTML 修复为 GFM 的 p14 表；500页非表正文原字相同，其余为该格式分类变化及三页签章 OCR／重复变化。
原39页正文全同，23表中20表全同，其余为上述 IRS 空白拓扑与 Census 两表；末7页全部6公开表格和7页正文全同。
这是一致性诊断，不是未标注内容的源件准确率。
[全部504页公开输出比较](evidence/table-v7-whole-public-consistency-20261018.json)、[全部39页比较](evidence/table-v7-holdout39-whole-public-consistency-20261018.json)、[全部7页比较](evidence/table-v7-fresh7-whole-public-consistency-20261018.json)。

**时间与资源。** 504页组原生后端在10/11份有时钟，观察墙钟合计 **3303.033 秒**，包含CPU预布局／公式、GPU调用和组装；独立GPU前向总时长未采集。
CPU表头核验有9/11份记录，合计 **801.105 秒／13.35分钟**，164源页、111对候选、4对接受；缺失时钟保留未知，不计零。
504页组来源保全阶段无记录，NASA来源保全为 **1.115 秒**，末7页组1/3份记录。

| 本轮550页窗口的容器／角色 | Docker RAM working-set 采样峰值 | CPU峰值（单核=100%） |
| --- | ---: | ---: |
| API／Docling独立核验 | 2.208 GiB | 807.64% |
| 原生CPU worker | 4.183 GiB | 422.70% |
| 原生vLLM provider | 7.161 GiB | 145.50% |
| GLM-OCR provider | 6.758 GiB | 334.59% |
| GLM SDK | 6.991 GiB | 3537.75% |

原生provider归属PID显存采样峰值 **3528 MiB**、进程SM观测均值 **24.81%**；GLM显存单列为11612 MiB。
504页组GPU1整卡能耗 **127.67 Wh** 包含GLM／TTS，GPU0还有其他训练负载，均不归因单个模型。
8GiB只是原生CPU worker限额，其自V4持续运行的 cgroup 生命周期峰值为 **5,348,884,480 bytes／约4.98GiB**，不是V7独占峰值；本轮五容器无重启／OOM／交换，双卡实际均220W。
原生provider同counter创建时刻、同model/engine标签的服务窗口增量为 **1108请求、RUNNING累计5649.425秒**；请求可重叠且可能有其他调用，不能当CUDA／GPU前向或整文墙钟。
[最终实际身份／逐角色资源／阶段覆盖](evidence/table-v7-final550-identity-resource-observation-20261018.json)、[RUNNING窗口原始哈希和限定](evidence/table-v7-provider-RUNNING-window-observation-20261018.json)。

新生产159页另有原生后端6/7份时钟、已观察910.268秒，验头4/7份167.598秒，来源保全1/7份1.021秒；缺失保留未知。对应provider窗口308请求、RUNNING累计1361.691秒，仍不能称GPU前向时间。
175份冻结文件（含测试／验收器）与工作树及Git index一致；容器实际运行源码／静态资源另行读回匹配，正式服务与受测候选的API／worker／provider三镜像相同，模型和共享服务身份保留。
V7配方指纹：`e760367d7fb88f11a7bc0bb5388db12ebe7f4fc54983b1ac8559d266736c11c7`。
完整550页的5391份原件／请求／日志／结果／资产及CPU证据已私有归档，稳定manifest SHA为 `2c3be73fde93e658da04c457d78ab0a2a61151a0e114eb3a30eb21055a156d95`；原始私有内容不提交。
[Eventrail归档索引与完整性收据](evidence/table-v7-full550-private-evidence-archive-index-20261018.json)。
新生产159页原件／请求／日志／结果／资产另有85文件私有归档，manifest SHA为 `252b6640ed3b04c454ea3de13ce07daf37b8506c6cc8d236be3729ce4510a4b8`。
[新生产Eventrail索引](evidence/table-v7-production159-private-evidence-archive-index-20261018.json)。

<details>
<summary>展开独立来源边界、首次失败、资源修复与历史证据</summary>

现有 10 份 PDF、502 页及 Office 两页都曾用于开发，属于暴露回归。固定 209、402、46 和额外 4 条条件有交叉覆盖，始终分别计数。
原 39 页在 2026-10-17 18:05 UTC 源件标注封存、19:14 UTC 首测后已暴露，V4 将其作为开发复测；不重写首次结果。
新 7 页由不同家族的 NASA 两页说明书、GSA 两页表单、NARA 三页扫描组成，28 条条件由只看源件的标注员封存。
模型权重、每页输入／原文提取、VLM 采样和验头谓词早于基线新 7 页输出冻结；CPU MFR 微批、处理窗口与堆回收在基线之后依据 NIST OOM 修复，
因此整套识别／调用配方并非早于任何新 7 页输出冻结。候选此前未执行新 7 页，源金标和读出器未改，不追加新金标。
[主数据集](datasets/moparse-v1/dataset.json)、[新 7 页附录](datasets/moparse-addon-20261018/dataset.json)。
主清单顶层暴露说明是最初 504 页的遗留文字，保持冻结 SHA；暴露范围以文件级记录及上述实际时间为准。

| 原 39 页、固定 36 条来源条件 | 服务成功页 | 通过／失败／未知 | 整次请求耗时 |
| --- | ---: | ---: | ---: |
| 旧线上 Docling＋GLM，本轮请求 | 39/39 | 24／12／0 | 212.90 秒 |
| 纯 Advanced＋TXT＋GLM，首次尝试 | 37/39 | 14／4／18 | 418.34 秒，包含失败 |
| Advanced＋TXT＋验头 V3，暴露复测 | 14/39 | 24／4／8 | 315.66 秒，包含失败 |
| Advanced＋TXT＋验头 V4，暴露复测 | 39/39 | 31／5／0 | 347.11 秒 |

固定 36 条逐项比较中，旧基线通过项没有变为失败／未知，7 项 IRS 条件恢复。
仍失败的 5 项为 IRS 签名字段顺序、NIST 排放表格式，以及 Census 的两个脚注和 copra 数字；均为原基线已有。
[39 页正式结果](evidence/header-v4-holdout39-20261018.json)。

旧线上另外独立完成 Office 两页（6/6，1.90 秒），不与历史 502 页伪装成一次新鲜 543 页运行。
新 7 页旧线上首次结果为 19 通过、6 失败、3 未知，完整请求 17.30 秒；3 项未知是 NASA 表格／跨度公开选表未匹配，服务本身成功。
V4 新 7 页完整请求 107.26 秒，固定 28 条为 24 通过、4 失败、0 未知；旧基线通过项没有变为失败／未知。
NASA 成本表原件 10×4 含合并标题行，候选为 9×4，标题另作段落，金额与其余 9 行／脚注原字完整，因此完整网格及标题 colspan 两项仍失败。
另外两项为基线已有的 NARA 封面标题和电报抬头顺序问题。它们与首页列出的未标注时间轴严重幻觉分开，不能以固定分数掩盖新增源件失败。
[新 7 页正式结果](evidence/header-v4-fresh7-20261018.json)。

另做只读 CPU 字符预算诊断：对应完整原 PDF 的整页字层，每种显示字符均需相应 occurrence 支持，仅去空白和折叠全角 ASCII，保留负号、小数点、金额分隔符。
全部 700 表（回归 670、原 39 页 23、新 7 页 7）初版有 107 个预算冲突复核候选、40 个未知；两个上标标注表另作保守未知观察，原预算与原标记均保留。
收窄为“源字层已存在的 Unicode 字母／数字仍超次数”后为 9 表：NASA 时间轴 1 表和 Census 历史 OCR 扫描 8 表；回归 670 表和 IRS 四表均为 0。
NASA 的字符 `5` 为模型 397 次／整页来源 16 次，但模型总字符 2547 仍少于整页 2620，因此总长度阈值无法发现此错误。
该方法只适合触发独立复核：Census 字层完整性未验证，IRS 方框、NASA 度数符号及普通破折号会造成原预算冲突，不能自动拒收或改写；
两处已知财务分隔符错误仍落在整页预算内，也说明“预算内”不代表数值／列义正确。原件、完整计数、所有 MD 哈希和符号冲突均保留。
[来源 occurrence 预算与逐表复核范围](evidence/header-v4-source-character-budget-observation-20261018.json)。

调用审计还确认：官方全局 `no_repeat_ngram_size=100` 不豁免 OTSL 结构 token，正常重复月度行的逐格编码也可能与它冲突；
本次模型在触发该约束前已出错，因此不能把关闭约束当作已验证修复。响应未截断，未发现参数未传递或 SDK／vLLM 版本不兼容证据。
[实际调用、原始响应及 CPU 反事实](evidence/header-v4-nasa-gpu-raw-repetition-audit-20261018.json)。

随后仅对同一张已暴露裁图完成两臂调用消融，未加入 550 页或固定金标分母：

| 官方原调用，仅改变全局 no_repeat_ngram_size | 单次 provider 时长 | 原始响应／官方 HTML | 原件符合性 |
| --- | ---: | --- | --- |
| 100，对照 | 43.99 秒 | 2595 tokens，stop；3×313，仍重复 Launch／Masseset | 失败 |
| 0，处理 | 42.96 秒 | 2661 tokens，stop；1×2652，仅 FY23／FY24 和巨大空跨度 | 失败，后续年份、月份、阶段和里程碑丢失 |

两臂顺序运行于同一预热 provider，时长不是整份 PDF 延迟或受控速度比较；第二臂字符预算无超额仍严重漏失，不能把“没有重复”当作正确。
原服务配置保持 100，不将单个参数调整当成已修复方案。
[100 对照](evidence/ngram-component-100-20261018.json)、[0 处理](evidence/ngram-component-0-20261018.json)。

V5 在应用层加入通用来源冲突复核：仅原生路由的源见证字母／数字超次数触发独立 Docling 区域类型核对；证据冲突时保留原图和 PDF 原字层、结构明确 unknown，
不发布无源生成表格，也不声称恢复甘特语义。原件四表的既有标题／结构差异继续作为失败保留。
其首次完整 NASA 两页请求虽解析成功，但 `/result` 回读将原文 CRLF 转为 LF，被真实 HTTP 捕获器拒绝；原失败、请求和 25 处换行差异保留，不能称端到端通过。
V6 仅将持久化回读改为 UTF8 原字节解码，另行冻结、重新测试；V6 的完整 550 页旧成绩已封存；其后生产 159 页仍失败，本段保留早期修订的失败边界。
[真实 V5 回读失败](evidence/source-v5-NASA-preflight-readback-failure-20261018.json)、[独立事后源件条件与版本索引](regressions/nasa-maax-20261018/current-reference.json)。

V6 的正式 API 切换于 01:31:50–01:32:23 UTC 完成，保留原数据库 30 条与 182 份旧输出／资产 SHA；32.63 秒是 API 受保护切换区间，不是实体目录迁移耗时。
其后 159 页实际捕获用时 1277.283 秒／21.288 分钟、6 completed＋1 partial，原31页源件功能检查通过，但119页第14页仍泄漏6676-byte raw HTML，缺来源和结构注释，原生产收据明确失败。
V7 仅修正显式 td／th 闭合的通用语法：唯一打开单元格可被显式结束，角色来自开始标签；不补隐式结束、不放宽嵌套／重叠／跨度预算，不能无损解码时保留源页并显式失败。
单表 CPU 重放、前后文原字保全与其后独立完整 HTTP 是不同证据，旧 V6 的 550 页不改标 V7。
[实际 V6 生产格式失败](evidence/source-v6-production159-GFM-contract-failure-20261018.json)、[V6 生产31页源验收](evidence/source-v6-production31-original-issues-independent-review-20261018.json)、[V6 生产资源](evidence/source-v6-production159-resource-stage-observation-20261018.json)、
[V6 原源码归档](evidence/source-v6-frozen-source-archive-before-V7-20261018.json)、[单表离线保全](evidence/table-v7-HTML-syntax-component-conservation-20261018.json)、[表外期间／单位保全](evidence/table-v7-HTML-syntax-surrounding-source-conservation-20261018.json)。
事后 19 条源件网格／跨度条件与原 28 条分开；来源复核纠正了首表底部三项共处一个物理单元格的转录及 Launch 的区域／整页计数范围，原版本和分数仍保留。
当前源件版本为 v2，预检 8/19；既有标题、物理网格与跨度差异仍失败，来源保全 11/11 不等于表格结构全部正确。
[原 39 页基线](evidence/baseline-holdout39-20261018.json)、[新 7 页基线](evidence/baseline-fresh7-20261018.json)、[Office 基线](evidence/baseline-office2-20261018.json)。

纯 TXT 首次 IRS 两页返回 HTTP 502，原因是合法 13×202 HTML 表格触发旧 100 列硬上限；修复通用跨度解码预算后表格原字、顺序、跨度保留。
首次 39 页其余 4 项失败为 NIST 的 `CO₂`→`CO2`、Census `1,735,734`→`1,735,784` 及两条页下脚注遗漏；分别记录格式、真实数字和正文遗漏。
共同成功的 NIST、Census 18 条条件两组逐项相同，但 NIST 有原生 MinerU 表格，不能把相同结果都归因共用 GLM。
[首次封存失败](evidence/primary-holdout39-first-attempt-20261018.json)。

V2 在四份完整原件／51 页后发现单表来源注释区块顺序与已有读出器不兼容，停止捕获并保留服务已接受的 36 页任务 GET-only 恢复结果；恢复耗时不是原请求延迟。
V3 仅修正通用注释顺序，完整 504 页成功，但其后的 NIST 请求在公式识别阶段被 8 GiB worker cgroup OOM 终止，Docker 退出 137 并重启。
21:14 UTC 的低压力／零重启观察早于 21:17 UTC OOM，不能推导整轮无故障；重启后清零的计数及 `OOMKilled=false` 不能否定历史故障。
V3 不发布，原失败和首次曝光边界保留。
[V2 失败](evidence/header-v2-source-boundary-failure-20261018.json)、[V2 恢复 36 页](evidence/header-v2-recovered36-20261018.json)、
[V3 OOM 内核归属与 Docker 事件](evidence/header-v3-native-worker-OOM-failure-20261018.json)、[V3 失败 39 页](evidence/header-v3-holdout39-20261018.json)。

V4 保持 8 GiB 上限，采用 CPU MFR 微批 1（原默认 8）、官方处理窗口 8（原默认 64）、官方堆回收开启，不关闭／截断公式，不改模型和每项预处理。
完整 NIST 25 页预检为 138.52 秒，公共明确界定的数学片段 27→27，原字及顺序完全一致；8 条源件条件为 7/8。
日志内 26 个 MFR 区域与公共数学片段不能一一对应，不据此宣称原件公式全部准确。
预检 cgroup 峰值 3,475,578,880 bytes，max／OOM／交换／重启为 0；这只属于预检窗口。
预检后只重置原生 GPU provider，CPU worker 不重启，持续验证后续完整 550 页。
[NIST 预检](evidence/header-v4-nist25-resource-regression-20261018.json)、[源件与资源审阅](evidence/header-v4-nist25-source-resource-preflight-20261018.json)。

正常续表两格严格原字差异是基金名称中的全角横杠与机构名称括号；独立诊断只折叠全角 ASCII，不使用 NFKC，不删除数值符号／分隔符，
没有把未合并、缺头或缺来源判为通过。402 中另有 21 项标签标点宽度和 10 项表头冒号宽度导致的严格失分，保留原分，不当作数值丢失。
私有逐格诊断曾误将源件断行负号作为 Markdown 列表符，已另加纯源文本纠正观察；原始金标、402 判分、读出器及输出均未改变。
[诊断派生字段纠正](evidence/plain-source-diagnostic-compaction-correction-20261018.json)。

历史组件 Markdown 与当前下游公共 GFM 分组比较，180W 与 220W 计时分开；双并发是共享资源预算，并非声称它在所有指标最快。
历史同条件四并发更快，两档原生显存峰值相同。旧线上 502 页的 API 镜像、53 份源文件、GLM／SDK 容器和模型配置已有实际部署闭环。
[旧线上 502 页](evidence/historical-20261017-docling-full-http.json)、[旧公共正文 40 条](evidence/historical-docling502-content40-20261018.json)、
[部署身份闭环](evidence/baseline-deployed-source-20261018.json)、[冻结历史报告](../benchmark-results/clean-model-comparison-20261015/report.md)。

</details>
