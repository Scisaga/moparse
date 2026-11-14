# MO-Parse 跨文档 Normalization 审查：第十一阶段

审查日期：2026-11-14。现有证据盘点、固定集合、原生覆盖和责任缺口分类已经完成；完整跨文档验证未完成。首个实际阻塞是：固定集合的72个选段与配置组合中，64个没有当前公共版本的完整阶段产物。本轮只分析已有产物，没有运行adapter、转换器、候选比较器或评分器来补齐它们。不能将缺少阶段证据写成管线失败，也不能将现有八份开发转换推广为跨文档验收。

固定集合为8份文档、9个既有授权选段，包含72份实际native及配对observation；按document_id合并后是64个文档与配置组合。调查了10类结构，9类有文字或原生结构依据；扫描来源类别仍unknown，只有既有scan-like和特殊视觉版面声明。已有当前版本的完整链限于两份文档的8个开发结果。唯一质量报告仍是[report.md](report.md)；本文是信息保全审查，不发布质量分数、排名或新的解析性能成绩。

## 一、当前研究状态与历史执行

### 身份快照

| 对象 | 本轮读取到的身份或状态 |
| --- | --- |
| 工作目录与HEAD | `/opt/mosaic-parse`解析至`/opt/moparse`；`7733d86e5c9a78a7e2917192a473ec9841f1b533`；接手dirty为空 |
| 当前software_id | `7f15e69534194831f4935a3b6c0cc45b3fe95833224160844fe41455414c18aa`；按`cli.code_identity`算法仅读源码及安装元数据计算，没有导入评测执行入口 |
| execution-lock | `20261026-repaired-v3`；冻结时间`2026-10-26T02:30:15.546168+08:00`；SHA256 `341a6ac17351c0a0d65c3734947793e15bd8b623faf7c8fb79417af94f850d62` |
| Native执行 | `20261026-lite-v3`；原HEAD `e42ffe0db115af942a346a1428135c63d24150b8`；software_id `c6e7f5c0cdcbb8801d17595c515fcbe7794111c396bfe58a6d0ab71a199db28e`；run状态completed |
| 共同开发结果 | 第十阶段`visual-content-closure/final-binding.json`绑定8份结果，software_id与当前源码相同；它不是正式current索引 |
| requirements/current | SHA256 `09918d7c652aee0d306dc603cbf7c827c6ca01996b8a436d72fb8d4f803b6884`；173份；`document_ast/1`；`structure_blocked`；software_id `279041a7896ce2dca90646e088978fa754128be253fe179e52ea46ad95a25af4` |
| 正式service/current/index.json | 不存在；旧`current/p07`、`current/p08`和development目录均不能代替八组正式原子索引 |
| 正式成绩 | `scores/`为空，`scores/current/index.json`不存在；旧成绩及其结论继续撤回 |
| 成本身份 | 原生成本沿用上述Native执行；旧P07/P08 baseline软件`f5e9063bfd2ac64be79796389d4cdaf3ad3770a8820a0628a1b245fff05a8a03`，旧current软件`bcb3b2d3ac3a2546c0108f75a178a065c27d81aef8a8756afcbeabb51704a9f7`；不是当前公共链的测量 |

完整源码身份、执行配置、输入声明、工件路径及哈希见[state.json](data/cross-document-normalization/state.json)。这些哈希标识本轮读到的工件，没有重签历史执行、参考或成本。manifest只读取已有selection、document_id、source_pages及原件身份声明，没有打开、哈希或认证PDF与参考语料。

### 八组确实发生的执行

逐个读取了run声明的2,080份observation，并核对原始worker job中的sample_id、suite、phase、repetition和页数；不是只看执行锁或目录数量。每组3份warmup、173份quality和84份perf均有native、observation及faithful.md；所有observation记录completed，errors为空，计时字段无缺测，组内没有重复sample_id。quality/perf的sample_id集合分别与既有Lite/perf声明相同。八组`execution-config.json`逐项等于execution-lock；固定集合72份native中已保存的模型、revision、版本、资源及导出身份字段与各自执行配置没有冲突。未重新核验实际模型权重或镜像运行状态。

| 配置与实际保存的格式身份 | quality800 | perf80 | warmup | 原生产物与原始计时 |
| --- | --- | --- | --- | --- |
| P01：Docling 2.139.0、core 2.101.1、TableFormer V1 + GLM 0.1.5 | 173例/800页，1轮 | 28例/80页，各3轮 | 3例/8页 | 均存在 |
| P02：同版Docling、TableFormer V2 + GLM | 同上 | 同上 | 同上 | 均存在 |
| P03：PaddleOCR-VL 1.5；paddleocr 3.7.0、paddlex 3.7.2 | 同上 | 同上 | 同上 | 均存在 |
| P04：PaddleOCR-VL 1.6；与P03独立模型revision | 同上 | 同上 | 同上 | 均存在 |
| P05：全页GLM-OCR SDK 0.1.5 | 同上 | 同上 | 同上 | 均存在 |
| P06：MinerU 4.0.12 Standard/TXT、DocVortex Middle + GLM | 同上 | 同上 | 同上 | 均存在 |
| P07：MinerU 4.0.12 Advanced/TXT、DocVortex Middle + GLM | 同上 | 同上 | 同上 | 均存在 |
| P08：全页Visual ContentBlock[]；mineru-vl-utils 2.0.7 | 同上 | 同上 | 同上 | 均存在 |

模型路径、完整revision和镜像ID没有用简称替代，逐组保存在state的`pipelines.*.configuration`与flow的`native_configuration_identity`。原始job仅绑定同一输入路径、sample_id与页数；所查native/observation/job没有逐case的PDF字节SHA。因此本轮确认的是同一声明输入与保存工件身份，不新声称已独立证明八组实际读入字节一致。原PDF物理页声明与native页包、分支局部页号分别记录。

### A至F分离与冲突裁定

| 状态 | 有证据的结论 | 不成立的推广 |
| --- | --- | --- |
| A 原生解析执行 | 八组原始quality/perf及warmup确实执行并落盘 | 不等于原生质量通过 |
| B Native质量评分 | 历史日志证明旧读取和评分程序实际运行过；其错误指标产品已删除 | 没有当前合同下有效的正式T/L/B成绩 |
| C 保存结果读回 | 历史评分日志、旧service运行和8份共同开发证据证明不同范围的实际读取 | 本轮72份JSON结构调查不等于72份完整格式读回验收 |
| D Normalization验收 | 当前相同software_id下有8份有界开发链及既有独立验收；本轮复查其843个清单对象和阶段字符串 | 没有固定集合全部72个组合的同版验收 |
| E Product正文 | P07/P08旧baseline/current均有各260个case的实际正文、outcome及计时；另有8份共同开发正文 | 旧正文不能充当当前公共链的Product比较，正文存在不等于质量比较完成 |
| F 正式成绩及排名 | 当前撤回，无有效发布工件 | 不恢复旧成绩，不由执行完成推导排名 |

`docs/pipelines/README.md`的quality/perf完成声明有实际工件支持；“本轮按完整身份重新计算”没有当前成绩支持，本轮改为明确撤回与门禁待满足。report中“未启动”原指第十阶段没有启动新的正式比较和八组公共回放，不表示历史从未执行Native解析或P07/P08转换。本轮在唯一报告中明确阶段语境。

另有三处保留的过时记录：[work-status.json](../../runs/lite/work-status.json)仍写旧任务complete及零损失，[evaluation.log](../../runs/lite/evaluation.log)结束于如今不存在的评分索引，[report-reproduction.json](../../runs/lite/report-reproduction.json)记录旧34工件复现。它们证明历史行为或当时的声明，不证明当前T/L/B正确、零损失或报告与源码一致。旧复现记录中的report哈希也与接手报告不同。原记录原样保留，失效范围和身份列于[history-and-costs.json](data/cross-document-normalization/history-and-costs.json)。2026-10-25撤回的执行与成绩不恢复，当前有效Native工件属于之后的v3执行。

## 二、固定文档集合与真实覆盖

先按既有selection标签、原生结构和独立验收记录选定以下集合，再开展信息流分析；没有读取成绩择样，没有改manifest、selection、Expected或五个输入范围。以下S1至S9只是本文索引，sample_id保持原样。D5的两个选段属于同一份文档，绝不计为两份独立文档。

| 索引/document_id | 固定sample_id及已授权物理页 | 选择的结构依据与已知限制 |
| --- | --- | --- |
| S1/D1 `10726562` | `vanke-interest-p001-002`；1–2 | 既有single-column、cross-page-prose声明；native含连续正文及分项标题；没有当前公共链完整快照 |
| S2/D2 `1201917092` | `vanke-repurchase-share-changes-p001-003`；1–3 | 真实多层表头、空单元格、期间及列表；已有七条共同链；P08同选段只有native与旧Product，未用S3替代 |
| S3/D3 `1200694910` | `zhenye-coupon-seals-p001-003`；1–3 | mixed-visual-appearance、seal、handwriting既有声明；P08含文字与两处媒体出现；只对P08有当前完整链 |
| S4/D4 `complex-tencent-2025-bond-programme` | `tencent-conditions-entity-payment-definitions-p108-114`；108–114 | nested-lists、legal-definitions、cross-page-definition声明及真实嵌套/平面对象差异；已有独立source-only整样本验收 |
| S5/D5 `complex-huawei-2024-annual` | `huawei-statements-p068-070`；68–70 | 财务表、层次行组、括号负数、混合期间与附注；没有当前共同链快照 |
| S6/D5 同上 | `huawei-management-toc-p014`；14 | section-toc、photo-background、layout-prose声明；实际native有目录或目录布局；Paddle标题锚点字面匹配未唯一定位 |
| S7/D6 `complex-huaweitech-2024-096` | `huaweitech-editorial-spread-p002`；2 | landscape-spread、multi-column、双语正文、图像及签名声明；同一5G-A字面有多个对象，不能强配一对一 |
| S8/D7 `1200454112` | `spdb-cover-declaration-p001-002`；1–2 | scan-like-cover、seal、layout-grid声明及原生图片/正文；扫描来源保持unknown |
| S9/D8 `1200694562` | `pingan-financials-p001-004`；1–4 | cross-page-table、multi-level-header、checkbox、mixed-units声明与实际多表；旧P07/P08均partial，困难组合固定保留 |

每个选段的原生路径统一为`benchmark/runs/lite/artifacts/PXX/measured-quality800-r1/<sample_id>/native.json`，配对observation在同目录。完整72项路径、工件SHA、分支、页数、结构字段和已有共同/历史结果位置见[flow.json](data/cross-document-normalization/flow.json)的`fixed_matrix`。页码来自已有授权声明；未用文件名推断文档结构、来源类别或页对应。S3的既有P08 contract中original_pages为空；manifest中的1–3页声明不能追溯改写它。

| 调查类别 | 可用的固定证据 | 本轮边界 |
| --- | --- | --- |
| 1 普通连续正文 | S1、S3，多个真实文字区域 | 原生文本保全可调查，跨页正文合并尚无同版横向验收 |
| 2 多层标题及嵌套列表 | S2的原生list父链，S4的法律定义与嵌套列表声明 | 显示标题级别不能代替原生标题树 |
| 3 复杂数据表 | S2、S5、S9真实源格/HTML | 原生表不是已确认业务关系，S5/S9未完成当前公共链验证 |
| 4 多层表头、单位及期间 | S2、S5、S9 | 无损源格与推导关系分开，当前强证据集中在S2 |
| 5 多栏及复杂版面 | S6、S7、S8已有声明与区域结构 | 不按bbox重排或用布局外形判断正确阅读顺序 |
| 6 图文混排 | S2、S3、S7、S8 | 媒体出现与交付分开，图片内容未读取 |
| 7 目录及页面导航 | S6 | 目录页码属于字面导航证据，不与一般数值计量等同 |
| 8 法律/财务条件及关系 | S4、S5、S9 | 已有Expected责任与实际候选关系尚未正式比较 |
| 9 扫描或视觉主导 | S3/S8只有外观与特殊版面声明，P08是纯视觉处理配置 | 真实扫描来源类别缺独立证据，保持unknown；纯视觉执行不证明原PDF是扫描件 |
| 10 跨页及连续表 | S1/S4既有跨页声明，S9既有cross-page-table声明 | 当前同版续接、完整表头继承及跨页附注验证缺失 |

下表只表示当前公共版本可支持的最强有界证据。`normalization_verified`限于既有固定开发输入的来源、转换及持久化工程验收，允许状态partial，不代表Native/Product质量通过；`native_available`表示真实原生JSON和observation已读取、结构可调查，未冒充完整格式验收。没有用合成fixture填格，也没有把未知或缺少阶段判为失败。

| 文档及选段 | P01 | P02 | P03 | P04 | P05 | P06 | P07 | P08 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1/S1 连续正文 | native_available | native_available | native_available | native_available | native_available | native_available | native_available | native_available |
| D2/S2 多层表头与列表 | normalization_verified | normalization_verified | normalization_verified | normalization_verified | normalization_verified | normalization_verified | normalization_verified | native_available |
| D3/S3 图文与特殊视觉版面 | native_available | native_available | native_available | native_available | native_available | native_available | native_available | normalization_verified |
| D4/S4 嵌套法律定义 | native_available | native_available | native_available | native_available | native_available | native_available | native_available | native_available |
| D5/S5+S6 财务表与目录 | native_available | native_available | native_available | native_available | native_available | native_available | native_available | native_available |
| D6/S7 多栏跨版 | native_available | native_available | native_available | native_available | native_available | native_available | native_available | native_available |
| D7/S8 scan-like与网格 | native_available | native_available | native_available | native_available | native_available | native_available | native_available | native_available |
| D8/S9 跨页表 | native_available | native_available | native_available | native_available | native_available | native_available | native_available | native_available |

P07/P08在S1至S9都另有旧软件的实际Product、exported/final快照及Semantic记录，因此历史`normalization_available`证据存在；主矩阵保守显示当前版本状态，未将旧软件证据升级为当前`normalization_verified`。缺少的是64个当前公共版本的完整链，原生JSON没有缺失；其中16个组合只有旧Product链，另48个组合也没有本固定集合下的历史P01–P06 Product。不可比较的组合包括不同选段、不同源码版本、P07允许原件补充与P08纯视觉历史输出，以及任意只有native而没有当前阶段的组合。

## 三、跨阶段信息流

实际当前开发入口为`saved_content_closure.close_saved_document → replay_native → adapt_saved_document → NativeContentContract/NativeContentEvidence → SavedContentService.finalize → Export → DocumentIRService → TableContext/TableSemantics → FinalContent → Storage`。这是对已有产物及代码调用的审查，本轮没有执行该链。Independent NativeInventory先消费原始JSON，未从final.md反推输入对象。下述843项复用已保存的输入清单，再独立解析其raw JSON locator和560个非null文字值；不是重新建立Expected Oracle。

| 阶段 | 现有8份共同开发产物的证据 | 其他64个组合 |
| --- | --- | --- |
| Native | 实际native SHA、主视图、原生locator、原文、父链、顺序及坐标字段 | 真实native及observation；有界主对象枚举，不代表完整SDK读回验收 |
| Adapted | 实际adapted快照中的native_blocks及table_fragments；工件绑定与原文分别保留 | 同版快照缺失，记unknown；不能从旧final重造 |
| IR | 实际ir快照与native_ir_handoff，使用真实block_id、region/table及源格消费对象 | 当前实际消费对象unknown；旧final.json不替代本阶段 |
| Semantic | 七个真实表视图、35个记录、175项值关系；来源为各自单元格和上下文 | 旧P07/P08可读自身保存关系，不能作为当前公共链关系 |
| Final | 实际final快照、final.md、原生对象及单元格的最终span、FinalContent编辑证据 | 16个组合有旧软件final，其余48个没有相应历史final；当前版本均unknown |
| Delivery | 真实Storage result.md与final字节一致，资产声明及四层状态分开 | 旧Product只作历史交付观察；当前版本交付状态unknown |

八份记录各自捕获adapted、source_pages、native_pages、exported、ir、assets、semantic、final。source_pages/native_pages明确`not_applicable`，原因是当时禁止来源补充；保留既有快照但不将未适用阶段算新增能力。56条相邻阶段记录的已有编辑均可重构下一个已保存字符串，所有删除区间原文吻合；这只证明编辑账本一致，不证明其语义正确，也不是八组真实回放。本轮另读取8份Storage纯文本，均与各自final.md一致。

对象账本在flow的`existing_development[].object_ledger`，逐项保留原生身份、locator、raw_text、结构、Adapted/IR身份、Semantic视图、Final span、Delivery及最早变化阶段。没有当前产物的4,107个有界主对象保存在`independent_primary_objects`，各自指向缺少阶段的trace；`unresolved_transition_summary`明确首个不可观察阶段为Adapted，实际最早变化阶段unknown，不能据此标为lost。这里的主对象数量没有与843项包含媒体、inline及metadata的完整开发清单相加。

## 四、同文档跨格式差异与归因

首先按同一声明sample_id、输入页及原生字面上下文记录对象对应，之后才描述差异。flow的`native_occurrence_correspondences`保留72格锚点的全部命中、locator、原生角色及父链/空间字段；没有按公司名选语义答案，没有用模糊匹配补字，也没有将唯一命中当正确答案。S1、S2、S3、S4、S8的锚点可在八组各定位到一个原生出现；S5的P07有两个命中，S6的P03/P04没有该精确字面命中，S7各组有多个命中，S9的P06/P07有两个命中，均保留unknown对应。这些只是局部出现对应，不是全文、顺序或业务等价证明；未定位不能写成原生漏识别。

S2的表值进一步使用各组自己的完整行头、列头、期间路径及单元格locator对应。不能只按“第2行第1列”或相同数字对齐。以下是一条具体链的证据：P01的`#/documents/0/document/tables/0/data/table_cells/10`原字为`15,386,999 `，进入`docling_p2_t1.r2c1`，绑定“股份类别/一、有限售条件股份”及“本次回购前/2015年8月31日/股份数量”，最终区间`[982,992)`显示`15,386,999`；P02自己的`table_cells/11`原字为`15,386,99`，最终`[981,990)`仍为`15,386,99`。差异首次已在Native，公共链没有借P01补P02。本文没有用Expected为这两个值评分。

| 选段/证据 | 原生层实际差异 | 当前可归因的变化或能力边界 |
| --- | --- | --- |
| S2 Docling V1/V2 | 分别45/46格，原字、空白和括号不同；均有自己的阅读树与prov | 共同转换各自37个非空格；8/9个空文字不补值；不能把多格或少格直接判成损失 |
| S2 Paddle 1.5/1.6 | 各44个HTML格、31个polygon；block_order部分为空，group语义未知；P04表头有字面反斜杠+n | HTML格是语法投影，不是独立OCR格；公共Markdown转义保留原字面；相同5记录/25值关系不表示相同识别质量 |
| S2 GLM | P05三页均为json_result；P01/P02/P06/P07只有各自第三页GLM | 原始raw_json_result与markdown_result只审计，不给主结果补文；P05无待交付媒体出现，不能当作媒体保全能力优于其他组 |
| S2 MinerU Standard/Advanced | P06四个独立备查text；P07为同一list的四个子项 | 父链差异来自真实content嵌套，未按bbox制造；table_body及footnote分别保留，表下注没有推成每个记录的附注关系 |
| S2 MinerU官方schema | P06整文档接受；P07嵌套list显式continues_prev=null使第2页及整文档被官方PageInfo拒绝 | 最早是保存序列化与schema回读兼容性问题；逐块接受和共同JSON读取不消除整文档拒绝。官方核验身份仍引用既有记录，本轮未运行Typed工具 |
| S3 Visual | 22个区域、20个文字字段、2个媒体出现；无字符跨度、标题父树、polygon或明确读序 | bbox/angle/页变换保留；数组显示不等于读序证明；page_number区域及其文字组件显式排除，其余标题/正文留存；partial仍有独立依据 |
| S1 普通正文 | 八组都有文字/标题对象，对应锚点可定位 | 旧P07含native_text_reconstruction，旧P08没有该来源步骤；当前版本没有阶段，不能声称已统一正文续接 |
| S4 法律嵌套 | 明确原生树、list容器或平面文字的表达不同 | 原生嵌套与打印编号分别留证；当前跨格式父子关系、条件/否定/例外保全仍待真实阶段观察 |
| S5 财务表、S6目录 | 表/单元格与目录布局可见；同document_id的两个选段不能混配 | 旧Product有自身表关系或目录正文；当前期间、单位、附注、字面导航及图像出现的对应没有完整链 |
| S7 多栏、S8封面 | 图像与正文区域、bbox和数组分块不同 | 不以空间邻近拼段；当前阅读顺序或媒体交付缺证，扫描类型不推断 |
| S9 跨页表 | 多个物理表、续接/表头表达不同；历史两组均partial | 不用列数相等代替续接证明，当前公共版本缺阶段，不能把历史完成状态升级为连续表转换完成 |

原生识别缺陷需要相同冻结Expected下的有效比较才能成立，本轮不作该判定。原生保存/schema缺陷、适配映射缺陷、公共转换缺陷和交付缺陷按首次证据区分；没有阶段时保持未知，不用最终Markdown的外观或相同字符替代结构判定。

## 五、Normalization信息变化诊断

以下数量属于8份已存在开发链的输入清单诊断，不是正式质量分母。每条native行先从输入清单取得身份，再核对实际raw locator和各阶段去向；原生container只拥有子对象，不重复拼成一份文字。843个locator均能解析，560个非null原文投影与已有清单一致。媒体仅确认声明字段和定位，未读取、解码或检验图像内容。

| 配置/选段 | 输入清单 | retained | normalized | transformed | unresolved | excluded | 现有转换/交付 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| P01/S2 | 81 | 28 | 11 | 38 | 4 | 0 | completed/partial |
| P02/S2 | 82 | 29 | 11 | 38 | 4 | 0 | completed/partial |
| P03/S2 | 142 | 90 | 8 | 38 | 6 | 0 | partial/partial |
| P04/S2 | 142 | 90 | 8 | 38 | 6 | 0 | partial/partial |
| P05/S2 | 77 | 39 | 0 | 38 | 0 | 0 | completed/completed |
| P06/S2 | 137 | 88 | 8 | 38 | 3 | 0 | completed/partial |
| P07/S2 | 132 | 79 | 12 | 38 | 3 | 0 | completed/partial |
| P08/S3 | 50 | 40 | 4 | 0 | 4 | 2 | partial/partial |
| 合计 | 843 | 483 | 62 | 266 | 30 | 2 | 不汇总为通过率 |

retained包含留在immutable audit中的结构/元数据；它不意味着全部对象必须打印进正文。normalized是标题标记等有来源的显示规范化；transformed为7个表及259个非空单元格的关系化显示，来源、完整标签和实际final span同时保留。相同表头在多条值关系中显示是明确的关系展开，不能按同字面出现次数判成duplicated。

另列175项`inferred_relation_ledger`：它们是MO-Parse在Semantic阶段从各自源格及上下文生成的值关系，不是175个新增原生对象，也不是原生解析器直接给出的业务语义。本轮逐项记录value、行头、列头、期间、单位和附注源格，全部有本组工件locator；没有缺来源的关系，完整关系签名没有重复。它们的存在和可追溯性不替代独立的关系正确性验收。此前既有断言的范围仍限于这七份固定表格。

30条unresolved由26个媒体相关对象去向和4个原生空footer节点组成。媒体相关对象包括14个媒体声明及12个关联picture区域，不是26张不同图片。4个空footer各自保留原生无字状态，没有因此新增partial。2条excluded是P08同一个page_number区域及其文字组件，不是删除两个正文段。P03/P04各31条读序未知影响转换；group语义未知保留，但当前未被输出责任依赖的group字段不单独阻断。P08的22条读序未知和2处媒体未交付分别保留；原PDF页映射未知也没有被改成完成。

lost、duplicated、unsupported和无来源新增在上述已定位清单中没有新确立的实例；缺少阶段的64个组合在这些维度均为unknown，不能填0。完整格式读取、跨页连续表、复杂条件、媒体字节交付和其他未覆盖结构仍未验收。当前没有依据为了提高样本通过率而修代码或替换样本。

## 六、Native、Normalization、Product与公共链一致性

| 对象 | 输入及现有能力 | 实际阻断与可隔离范围 | 本轮就绪判断 |
| --- | --- | --- | --- |
| Native | 自己的原生JSON、主视图、原生关系、状态与原生成本；无需等待Product链 | 原生读回完整性、Expected责任及独立比较器/当前执行门禁分别满足；P07整文档schema兼容性不能被逐块通过覆盖 | 可继续只读格式与局部来源研究；当前不能启动正式Native评分 |
| Normalization | Native→Adapted→IR→Semantic的信息保全与有据变换 | 不直接依赖107份Expected责任缺口；当前首要阻断是固定集合64个同版阶段缺失、部分读序不确定及真实结构覆盖不足 | 两文档8条开发链可局部有效；完整跨文档验收未完成，无总分 |
| Product | 固定公共软件实际Final、资产、状态和Storage；质量比较只读真实正文 | 107份对应层的Expected比较缺口、3份独立验收、5范围、同版正文/阶段与媒体验收各自保留 | 旧正文和8份开发正文可读；当前正式Product比较与发布未就绪 |

对指定11个公共/适配文件及实际调用链的静态核对，未发现按P01–P08编号、公司名或文件名选择业务答案的公共语义分支。`native_config`按编号限制producer和许可branch；Docling、GLM、Paddle、MinerU、Visual各自读原生语法后进入同一SavedContentService。`NativeContentEvidence._execution`只白名单接纳observation身份与状态，不读取其派生文字/关系补主结果；GLM固定json_result，MinerU固定documents主结构，raw/派生导出不重复计入答案。SavedContentService在进入Export之前及Final之后核验共同契约，IR与表关系另有核验，没有在当前八份开发入口中发现绕过来源守卫的路径。

仍存在必须记录的证据分支：`table_context_service.native_scopes`允许受契约核验的saved源格，并保留旧MinerU来源入口；`_prepare_native_continuations`有仅接纳MinerU来源的续表守卫；`FinalContentService.apply`禁止跨GLM单页调用范围无证拼接。这些是格式/来源能力或既有处理边界，不能写成“所有相同证据已经跨格式等价验证”。S9及S4没有同版阶段，所以尚不能确认续表/跨页限制是否在等价证据下造成不必要差异；本轮未删除守卫，也未发现对固定当前八条链有明确影响的新公共缺陷。

人工开发暴露没有抹去：S2已接受多轮Docling、GLM、Paddle及MinerU开发，S3为P08开发样本，部分其他选段已有历史诊断或Oracle暴露。各自开发目录、binding及旧run身份保留；该集合是开发验证集合，不能当独立测试集或据此排序方法。原生没有的父链、charspan、caption、polygon或读序不会由另一个视图或另一条管线补造；unknown是否影响partial取决于实际消费责任，不能按warning名称或管线固定升降状态。

## 七、107份责任缺口的真实阻断分类

只读取现有index、各自comparison_coverage及stage5诊断，未重编译Expected、修改Oracle、责任或分母。当前仍是107份责任缺口、66份责任完整；66份中63份已有原有独立source/contract验收，3份待独立整样本验收；60份属于责任完整但仍有语言分析限制。后者与107份不同，不能把语言pending统一等同于没有内容责任。

| 分类 | 现有证据与数量 | Native影响 | Normalization影响 | Product及发布影响 |
| --- | --- | --- | --- | --- |
| T文字保真比较 | 27份带T阻断标记；其中原有字面投影缺口23份/340个raw source，另4份为合同处置问题 | 阻断对应T义务，不能扩成所有Native层 | 不直接阻断native-owned信息保全 | 阻断对应T及完整成绩；须保持原标记并修确切来源 |
| L结构比较 | 103份有明确L阻断 | 影响相应标题、列表、条件或关系比较 | 不证明adapter丢结构；可继续原生父链/来源诊断 | 阻断对应L，不能借T相同自动通过 |
| B业务语义比较 | 同103份有B阻断 | 影响相应实体、指标或语义关系判定 | 不阻断纯信息去向记录；语义正确性验收仍须独立证据 | 阻断对应B及完整成绩 |
| 来源真实性 | 现有173份均记录source_structure_complete；107缺口未建立Native来源伪造实例 | 来源工件和native locator仍须单独核对 | 不能从Expected缺口推断Normalization来源已验证或已失败 | 不把来源完整标签当产品准确率 |
| Normalization专属 | 107份中没有直接指向共同链信息损失的证据 | 不构成Native专属阻断 | 实际独立阻断为64个同版阶段缺失、必要读序及覆盖边界 | 缺口应进入当前信息流账本，不转嫁为Expected问题 |
| Product专属 | 107份是共同Expected责任问题；媒体与Storage、正文阶段属于另一类证据 | 不要求等待Product交付 | 资产声明保全与交付分开 | 当前14处媒体声明未交付，以及64个当前正文/阶段缺失，不能用修Expected消除 |
| 仅局部层/关系 | 4份只有T；另80份为B/L，23份为T/B/L；关系级ID与source见下表和数据 | 不受影响的层/关系可在原合同下隔离研究 | 可保留限制继续研究，不改成N/A | 全样本/全局发布仍须覆盖全部非deferred义务 |
| 内容责任完整、语言未决 | 60份，与107缺口分开 | 在现有完整内容合同及独立验收范围内可局部有效 | 不是保全链共同阻塞 | 不扩大完整内容责任，不继承为当前软件正式门禁 |
| 输入/授权不足 | 原5个范围目标继续存在；本轮没有新输入授权 | 影响对应范围的完整比较 | 对已保存native内部保全通常可隔离 | 完整比较与发布须解决范围，不据文件名或相邻页猜补 |

分层使用原blocking obligation和blocking analysis limitation的layers并集，另保留原T字面诊断，不是新计分。27与23不是同一统计口径；额外四份是`huawei-digital-energy-p037-040`、`nvidia-business-manufacturing-people-p096-104`、`pboc-policy-columns-p019-026`、`tencent-title-transfer-status-p115-117`，均有既有T层`source_has_no_supported_semantic_disposition`阻断。没有把它们改名、删掉或重新判N/A。

四份仅T阻断为`hkex-audit-committee-p109-111`、`hkex-quarterly-results-p074`、`huawei-financial-summary-p007`、`tencent-title-transfer-status-p115-117`；它们不因此新增L/B责任缺口。三份责任完整待验收仍为`iea-adoption-ai-types-p025-031`、`pingan-business-highlights-p012-013`、`pingan-health-senior-care-p025-030`。原有63份独立记录和60份仅语言分析限制的完整sample_id列表均保存在[gap-classification.json](data/cross-document-normalization/gap-classification.json)，没有把软件测试数当成独立样本验收。

五个输入目标原样保留：Alibaba strategies L230；Midea strategy L417；PBOC banking L540；PBOC macro和policy分别引用L252的两个既有选段。它们的outside_selection及原文身份沿用stage5-preservation，未扩大允许页范围。Alibaba business-risks L2353双附着保持，不采用多解释合同提案。

全局阻断是正式执行授权、同版独立门禁及完整质量责任，不能因此停止所有Native格式或Normalization保全研究。Native专属问题是各自原生主视图完整读取与格式/schema边界；Normalization专属是实际阶段和变换来源；Product专属是实际交付与同版正文。107份主要阻断Native/Product对应层的内容比较，不能把它们当三组研究的共同停止条件。对完整成绩必须修复；对来源与去向研究可隔离，但本轮没有授权据此发布局部质量成绩。

### 107份sample_id、层与定位

下表逐项引用现有阻断，不生成新答案。`O/A`为现有blocking obligation/analysis limitation数量；仅用于找工程工作，不是质量分母。T的raw字面缺口与合同处置标记分别保留；完整obligation_id、issue_id、原始source行与span、requirement_id、阻断影响和隔离建议见同一data文件。以下所有107份的完整质量发布均受阻，Normalization保全研究均未被这些Expected缺口直接否决。

| sample_id | 阻断层 | O/A | 首个既有source定位 | 局部处理入口 |
| --- | --- | ---: | --- | --- |
| `alibaba-business-risks-p109-112` | B/L | 149/69 | L2355 [153,717) | L/B具体关系 |
| `alibaba-international-and-data-risks-p117-124` | B/L | 61/27 | L2547 [0,215) | L/B具体关系 |
| `alibaba-strategies-p009-010` | B/L | 77/39 | L204 [0,179) | L/B具体关系 |
| `alibaba-trade-sanction-risks-p113-116` | B/L | 110/50 | L2433 [0,213) | L/B具体关系 |
| `beijing-media-disposal-p001-008` | B/L | 26/6 | L53 [0,115) | L/B具体关系 |
| `bis-economic-review-p022-025` | B/L | 3/3 | L466 [22,25) | L/B具体关系 |
| `bis-financial-risk-boxes-p035-041` | B/L | 15/15 | L694 [0,30) | L/B具体关系 |
| `bis-fiscal-productivity-policy-p042-051` | B/L | 5/5 | L826 [66,69) | L/B具体关系 |
| `bis-policy-boxes-p026-034` | B/L | 19/20 | L526 [0,28) | L/B具体关系 |
| `byd-bilingual-front-p001-012` | B/L/T | 211/29 | L17 [0,469) | T字面/处置及L/B关系 |
| `byd-outlook-finance-p037-044` | B/L | 22/22 | L687 [0,165) | L/B具体关系 |
| `byd-product-cards-p025-036` | B/L | 7/8 | L679 [0,53) | L/B具体关系 |
| `fiyta-terms-financials-p001-010` | B/L/T | 117/114 | L17 [0,7) | T字面/处置及L/B关系 |
| `hkex-audit-committee-p109-111` | T | 4/4 | L3426 [0,40) | T字面/处置 |
| `hkex-ceo-review-p021-027` | B/L | 3/4 | L414 [0,32) | L/B具体关系 |
| `hkex-financial-cards-p010` | B/L | 11/1 | L158 [0,221) | L/B具体关系 |
| `hkex-investment-and-resources-p075-080` | B/L/T | 55/109 | L2299 [0,31) | T字面/处置及L/B关系 |
| `hkex-key-tables-p011` | B/L/T | 117/155 | L183 [0,67) | T字面/处置及L/B关系 |
| `hkex-quarterly-results-p074` | T | 30/30 | L2247 [0,121) | T字面/处置 |
| `hkex-risk-committee-p112-117` | B/L | 0/59 | L3500 | L/B具体关系 |
| `huawei-address-p004-005` | B/L | 6/7 | L72 [0,30) | L/B具体关系 |
| `huawei-automotive-p047` | B/L | 1/8 | L1228 [0,125) | L/B具体关系 |
| `huawei-business-review-p017` | B/L | 2/15 | L449 [0,10) | L/B具体关系 |
| `huawei-carrier-business-p018-022` | B/L | 17/17 | L596 [0,53) | L/B具体关系 |
| `huawei-cash-and-risk-p064-065` | B/L | 11/3 | L1668 [0,122) | L/B具体关系 |
| `huawei-chairman-p008-010` | B/L | 6/9 | L278 [0,132) | L/B具体关系 |
| `huawei-cloud-business-p033-036` | B/L | 4/9 | L963 [0,119) | L/B具体关系 |
| `huawei-cybersecurity-p054-057` | B/L | 70/51 | L1458 [0,11) | L/B具体关系 |
| `huawei-digital-energy-p037-040` | B/L/T | 21/28 | L1019 [0,159) | T字面/处置及L/B关系 |
| `huawei-enterprise-business-p023-027` | B/L | 13/11 | L667 [0,82) | L/B具体关系 |
| `huawei-financial-summary-p007` | T | 4/4 | L175 [0,14) | T字面/处置 |
| `huawei-industry-trends-p011-013` | B/L | 5/9 | L366 [0,74) | L/B具体关系 |
| `huawei-progress-p006` | B/L | 7/20 | L141 [0,125) | L/B具体关系 |
| `huawei-research-quality-p048-050` | B/L | 8/4 | L1270 [0,171) | L/B具体关系 |
| `huawei-services-connection-computing-p028-032` | B/L | 32/33 | L805 [0,315) | L/B具体关系 |
| `huawei-statements-p068-070` | B/L | 0/7 | L1792 | L/B具体关系 |
| `huawei-terminal-business-p041-046` | B/L | 6/10 | L1130 [0,46) | L/B具体关系 |
| `huawei-vision-p015-016` | B/L | 3/4 | L419 [0,23) | L/B具体关系 |
| `huaweitech-5ga-p007-009` | B/L | 1/2 | L273 [5,7) | L/B具体关系 |
| `huaweitech-apn6-p027-030` | B/L | 7/4 | L823 [0,57) | L/B具体关系 |
| `huaweitech-editorial-spread-p002` | B/L | 3/4 | L35 [0,14) | L/B具体关系 |
| `huaweitech-future-optical-p024-026` | B/L | 24/24 | L742 [0,190) | L/B具体关系 |
| `huaweitech-intelligence-address-p004-006` | B/L | 65/52 | L197 [0,30) | L/B具体关系 |
| `huaweitech-metro-p016-019` | B/L | 0/6 | L542 | L/B具体关系 |
| `huaweitech-odn-p010-015` | B/L | 9/13 | L417 [0,11) | L/B具体关系 |
| `iea-infrastructure-capabilities-p032-036` | B/L | 104/7 | L597 [0,307) | L/B具体关系 |
| `iea-outlook-computing-rating-table-p062-070` | B/L | 0/48 | L1133 | L/B具体关系 |
| `midea-business-p013-024` | B/L | 137/154 | L223 [0,891) | L/B具体关系 |
| `midea-front-p001-012` | B/L/T | 149/216 | L32 [0,7) | T字面/处置及L/B关系 |
| `midea-fx-derivatives-p001-004` | B/L | 14/13 | L5 [0,141) | L/B具体关系 |
| `midea-strategy-p025-036` | B/L | 172/159 | L353 [0,67) | L/B具体关系 |
| `moutai-governance-environment-p030-039` | B/L/T | 198/358 | L1146 [0,25) | T字面/处置及L/B关系 |
| `moutai-governance-p018-029` | B/L/T | 164/121 | L739 [0,8) | T字面/处置及L/B关系 |
| `moutai-introduction-p001-008` | B/L/T | 366/58 | L137 [0,105) | T字面/处置及L/B关系 |
| `moutai-transactions-p040-049` | B/L/T | 493/592 | L1456 [0,13) | T字面/处置及L/B关系 |
| `nhu-subsidiary-guarantees-p001-003` | B/L | 9/1 | L29 [0,79) | L/B具体关系 |
| `nvidia-business-manufacturing-people-p096-104` | B/L/T | 10/4 | L3118 [0,73) | T字面/处置及L/B关系 |
| `nvidia-business-overview-p018-019` | B/L | 0/8 | L522 | L/B具体关系 |
| `nvidia-ceo-letter-p010-014` | B/L | 225/145 | L67 [11,14) | L/B具体关系 |
| `nvidia-global-regulatory-risks-p111-120` | B/L | 277/115 | L3466 [43,45) | L/B具体关系 |
| `nvidia-illustrated-review-p002-009` | B/L | 7/7 | L19 [0,41) | L/B具体关系 |
| `nvidia-management-estimates-ratio-table-p128-132` | B/L | 172/42 | L3744 [133,195) | L/B具体关系 |
| `nvidia-meeting-notice-toc-p015-016` | B/L | 7/3 | L372 [0,136) | L/B具体关系 |
| `nvidia-officers-risk-supply-p105-110` | B/L | 170/92 | L3358 [193,402) | L/B具体关系 |
| `nvidia-proxy-summary-p020-024` | B/L | 265/27 | L617 [0,344) | L/B具体关系 |
| `nvidia-regulatory-governance-equity-p121-127` | B/L | 150/90 | L3613 [0,192) | L/B具体关系 |
| `pboc-banking-columns-p029-040` | B/L | 29/42 | L406 [0,14) | L/B具体关系 |
| `pboc-committees-p002-003` | B/L | 0/27 | L23 | L/B具体关系 |
| `pboc-contents-p007-008` | B/L | 1/37 | L100 [8,10) | L/B具体关系 |
| `pboc-macro-columns-p011-018` | B/L | 25/30 | L114 [0,45) | L/B具体关系 |
| `pboc-overview-p004-006` | B/L | 42/36 | L56 [0,151) | L/B具体关系 |
| `pboc-policy-columns-p019-026` | B/L/T | 41/31 | L252 [0,43) | T字面/处置及L/B关系 |
| `pboc-statistical-tables-p101-108` | B/L/T | 41/58 | L1332 [22,37) | T字面/处置及L/B关系 |
| `peoples-network-fundraising-p001-003` | B/L/T | 21/15 | L21 [0,40) | T字面/处置及L/B关系 |
| `pingan-financials-p001-004` | B/L/T | 159/190 | L21 [0,41) | T字面/处置及L/B关系 |
| `pingan-fundraising-assurance-p003-007` | B/L | 9/6 | L20 [0,184) | L/B具体关系 |
| `pingan-summary-and-profile-p004-005` | B/L/T | 390/41 | L145 [0,210) | T字面/处置及L/B关系 |
| `sf-auditor-grid-prose-responsibilities-p087-088` | B/L | 3/1 | L2203 [0,25) | L/B具体关系 |
| `sf-industry-business-review-p017-024` | B/L | 5/4 | L492 [0,95) | L/B具体关系 |
| `sf-margin-profit-ebitda-p037-039` | B/L/T | 40/42 | L803 [0,60) | T字面/处置及L/B关系 |
| `sf-network-infographics-p027-031` | B/L | 1/13 | L596 [0,2) | L/B具体关系 |
| `sf-revenue-operating-cost-tables-p035-036` | B/L | 8/1 | L779 [0,78) | L/B具体关系 |
| `sinopec-front-p001-012` | B/L/T | 300/339 | L64 [0,48) | T字面/处置及L/B关系 |
| `sinopec-operations-p013-024` | B/L/T | 363/427 | L301 [0,30) | T字面/处置及L/B关系 |
| `spdb-acquisition-approval-p001-002` | B/L | 3/1 | L13 [0,141) | L/B具体关系 |
| `spdb-cover-declaration-p001-002` | B/L | 3/2 | L11 [0,42) | L/B具体关系 |
| `spdb-credit-overview-p001-004` | B/L/T | 287/64 | L7 [0,17) | T字面/处置及L/B关系 |
| `spdb-prospectus-financials-seal-p021-023` | B/L/T | 128/160 | L221 [0,93) | T字面/处置及L/B关系 |
| `spdb-prospectus-issuer-terms-p006-012` | B/L | 11/14 | L74 [0,66) | L/B具体关系 |
| `spdb-prospectus-risk-tax-p013-020` | B/L | 12/18 | L177 [0,125) | L/B具体关系 |
| `spdb-summary-financials-p001-004` | B/L | 48/107 | L21 [0,9) | L/B具体关系 |
| `tangshan-accounting-policy-p001-005` | B/L | 38/29 | L66 [0,239) | L/B具体关系 |
| `tangshan-li-nomination-p009-011` | B/L | 3/1 | L277 [0,57) | L/B具体关系 |
| `tangshan-rong-nomination-p001-002` | B/L | 3/1 | L5 [0,57) | L/B具体关系 |
| `tencent-conditions-definitions-formulas-p102-107` | B/L | 0/3 | L1469 | L/B具体关系 |
| `tencent-issuer-summary-p024-026` | B/L | 1/1 | L420 [20,23) | L/B具体关系 |
| `tencent-programme-summary-p027-033` | B/L | 80/9 | L449 [0,59) | L/B具体关系 |
| `tencent-sofr-formulas-benchmark-replacement-p124-134` | B/L | 39/7 | L1769 [0,57) | L/B具体关系 |
| `tencent-title-transfer-status-p115-117` | T | 0/1 | L1628 [20,75) | T字面/处置 |
| `tgood-acquisition-terms-p009-019` | B/L/T | 23/22 | L816 [0,197) | T字面/处置及L/B关系 |
| `tgood-compensation-subscription-p022-028` | B/L/T | 28/19 | L782 [0,110) | T字面/处置及L/B关系 |
| `tgood-meeting-p001-006` | B/L | 19/14 | L9 [0,30) | L/B具体关系 |
| `vanke-acquisition-guarantee-p001-002` | B/L | 15/7 | L13 [0,214) | L/B具体关系 |
| `vanke-interest-p001-002` | B/L | 5/1 | L9 [0,77) | L/B具体关系 |
| `vanke-repurchase-share-changes-p001-003` | B/L | 5/3 | L9 [0,186) | L/B具体关系 |
| `vanke-sales-projects-p001` | B/L | 13/14 | L11 [0,142) | L/B具体关系 |
| `wuliangye-litigation-ruling-p001-002` | B/L | 5/1 | L19 [0,98) | L/B具体关系 |

## 八、成本数据可比较性

本轮重新读取原observation及旧service case/outcome核对计时记录，没有重测、重签或更改历史成本。八组原生处理边界与原字段保持；下表只表达字段能否用于原执行条件下的描述，不据此给方法排名。唯一质量报告的“原始处理成本”段及[processing-cost-summary.json](data/processing-cost-summary.json)保持原字节。

| 配置/阶段 | 可比较的已有观察 | 缺少或不可混用的观察 |
| --- | --- | --- |
| P01–P08 Native处理 | 各173个quality与3×28个perf的worker.processing_seconds完整；suite/sample和资源声明一致 | 不能把case时长之和叫整批墙钟；重复轮次不增加独立文档；未重新证明逐case源PDF字节SHA |
| 初始化 | 8个持久worker各有独立initialization_seconds；独立inference-ownership另有initialization_to_readiness_host_seconds及清理记录 | 两个字段的边界不同，不能重复累加到每个case；服务生命周期和worker时长可能重叠 |
| 预热 | 每组同一3样本/8页、独立warmup记录完整 | 不与measured混合；不从预热推完整文档性能 |
| 单页处理 | 总输入页数、page_processing元数据可读 | 没有可覆盖八组的独立逐页elapsed分解，保持unknown；不能用总时长除页数冒充原测量 |
| 旧P07/P08 Adapter/IR/Semantic/Final | 四个历史run各260个case，native_bridge_seconds、ir_seconds、semantics_seconds、final_content_seconds及导出等字段齐全，case与outcome计时相等 | software和来源权限不同于当前source-free链；P07含实际来源补充，P08不含，不能当当前公共链公平性能比较 |
| Storage | 旧run有pure_persistence_and_observation_seconds，原边界明确排除总postprocessing；开发结果可核对Storage文本 | 它混合持久化及observation，不是纯Storage成本；当前8个开发结果无正式分阶段性能测量 |
| 外部API/请求 | 保存部分请求参数、usage、终止原因及原始retry观测 | 非所有格式均有同样请求遥测；没有统一API wall-time，不能把缺记录当0调用、0重试或0成本 |
| CPU和内存 | 各case的worker_cpu_seconds、进程RSS采样和cgroup生存期峰值存在；配额与affinity分别保存 | CPU配额8不等于独占8物理核；采样峰值、生存期峰值和单case峰值不能互相替代，P03/P04同进程隔离含义须保持原记录 |
| GPU与TTS | 八组独立inference/resources均有整卡、自有进程及TTS显存采样，采样内未记录超过16 GiB自有预算；起止持久任务71→76，记录5个新增任务 | CPU worker-resources的GPU采样数为0，不等于管线没有采样；独立inference采样也均标partial，不能证明全时真实峰值、无短时超预算或TTS空闲；整卡功率/利用率不是自有进程独占成本 |
| 本轮审查和开发历史 | 旧development_conversion_seconds及source-only回归时长各自仍保留 | 不属于正式Native解析或Product性能；本轮读取JSON和报告生成耗时也不写入这些字段 |

独立inference资源与CPU worker资源的观察范围分别保存。下表直接引用inference/resources原字段，单位MiB；是历史窗口内的采样峰值，不是本轮新测量或全时真实峰值。完整原资源摘要、ownership及其哈希在state的`pipelines.*.inference_resources`，没有用worker的null覆盖实际GPU观测。

| 配置 | 自有进程采样峰值 | TTS采样峰值 | 自有可归属采样/全部采样 | 覆盖状态 |
| --- | ---: | ---: | ---: | --- |
| P01 | 4464 | 5118 | 1220/1222 | partial |
| P02 | 4464 | 5316 | 1160/1162 | partial |
| P03 | 3254 | 5316 | 7314/7316 | partial |
| P04 | 3254 | 5316 | 7289/7291 | partial |
| P05 | 5604 | 5316 | 1966/1970 | partial |
| P06 | 8224 | 5316 | 624/628 | partial |
| P07 | 8372 | 5316 | 880/883 | partial |
| P08 | 3914 | 5316 | 2206/2209 | partial |

原生quality/perf处理时长没有缺测；GPU也有上述独立采样，只是不能据部分观测作全时峰值或资源合规认证。旧service的postprocessing包含来源、资产及诊断捕获等真实阶段；其子阶段没有被重新相加为新的端到端时长。Native加旧后处理也不是一条新测量。待授权的新成本研究需要固定同版完整边界、分开初始化和预热、至少三次代表性处理测量、独立Storage计时，以及足够覆盖的自有GPU归属采样；本轮没有启动这些工作。

## 九、下一阶段工程决策

公共NativeContentContract、原生独立清单、分格式读取、共同Export/IR/TableContext/TableSemantics/FinalContent/Storage、依赖驱动的状态及现有阶段编辑证据已经足以承接下一个固定跨文档开发验证，不需要再建一套架构或按管线编号继续重复纵向接入。当前证据支持“同版公共链在两个固定文档切面上可用”，不支持“不同文档结构已统一验收”。

停止继续优化S2/S3的通过数量、软件测试数量或同一三页样本的显示形式；停止将原生字面差异归一到别组答案。P07整文档schema拒绝继续单列；未经授权不改其原始JSON。当前没有新确立、对固定已运行切面有明确影响的公共缺陷，因此没有为了制造代码变更而修改生产实现。

Native正式评分可独立于Product准备，但现在不能开始：当前requirements仍structure_blocked且绑定旧软件，没有同版独立有效门禁，完整原生读取与真实格式/比较器证据也不能由本轮结构枚举代替，且本轮明确禁止正式评分。Product正式比较同样不能开始：还缺固定公共版本下的完整选段产物/阶段、对应T/L/B责任及独立验收，媒体交付和五范围问题必须按实际责任保留。Normalization可以继续保留这些限制研究，但生成缺失的64份新阶段工件超出本轮只审查既存产物的授权。

## 十、具体下一轮任务与本轮边界

以下是可执行的后续工作界面，不是本轮追加执行许可。优先补齐固定集合的同版信息流证据，再根据最早实际差异决定最小修复；固定成员不更换。

| 顺序/文件与函数 | 固定输入或反例 | 验收条件与所需授权 |
| --- | --- | --- |
| 1 `moparse_eval/saved_content_closure.py::close_saved_document`、`service_stages.py::capture_stage`及现有阶段入口 | flow.fixed_matrix中64项current_common_stage_evidence为空的准确native/observation组合 | 需另行授权有界source-free开发转换；8 CPU/8 GiB、串行、断网、禁GPU，保持各页许可；自己native→实际Adapted/IR/Semantic/Final/Storage和反向去向完整，不造历史before、不激活正式current |
| 2 `app/services/table_context_service.py::native_scopes/_prepare_native_continuations` | S9全部八组、S5三页各自表格；先观察同版产物，再构造相同证据的独立跨格式反例 | 不以列数、相同首行或source_kind名称替代完整表头/期间/单位/续接；同一证据应得到同一公共决策，缺证保留物理表与unknown；只修有真实影响的公共缺陷 |
| 3 `app/services/final_content_service.py::FinalContentService.apply`、`native_content_status.py::native_status_impacts` | S1跨页正文、S4嵌套法律定义、S7多栏；配套独立否定/例外/条件和未知读序反例 | 原文、限定、父子与出现次数逐对象留证；不得借bbox拼接；无关unknown不降级，必要读序和失败不升级completed；需上述开发运行授权 |
| 4 `app/services/native_content_evidence.py::validate_ir_handoff/validate_table_relations`、`saved_content_coverage.py::native_destinations` | 固定9个选段；重点S6目录、S9跨页表及S2的空源格与原字差异 | 每项原生出现有原始locator、实际IR/关系去向及final范围；推导和原生分开；阶段缺失仍unknown，不能以数量相等接受 |
| 5 `moparse_eval/three_layer.py::_finish`、`text_projection.py`及既有责任实现 | 仅T阻断的HKEX audit/quarterly、Huawei summary，以及Tencent title-transfer L1628；然后查表中其余来源 | 另行source-only软件修复授权后，修确切字面或合同处置，不改T/L/B合同、分母或Oracle；独立来源断言覆盖完整选段，旧原字与typed payload保持；不为本轮重编译全173份 |
| 6 `moparse_eval/mineru_typed_validation.py`与`moparse_eval/executors.py::_native_snapshot`保存链 | S2/P07四个显式continues_prev=null嵌套成员，及对应独立官方序列化反例 | 先核对生产保存函数的真实调用边界；新受控序列化若获授权可修，旧native字节和rejected证据不改；全Middle与逐块结果分别验收，不恢复旧成绩 |
| 7 `app/services/storage_service.py::StorageService.write_result`及既有资产声明入口 | 固定S2/S3媒体出现和S7/S8特殊版面 | 若另行授权媒体字节读取/交付，核对每次出现、文件、manifest及持久化；当前只保留声明和partial；不增加图像语义任务 |
| 8 `moparse_eval/requirement_gate.py::validate_expected_structure_gate`及原有成本字段生产位置 | 不变的107份、3份待验收与5范围；固定同软件的后续比较范围 | 只有获得对应执行授权、同版独立证据及完整责任后才能进入Native或Product正式比较；成本新测量另定，历史字段、成绩与门禁不重签 |

本轮没有修改生产代码、T/L/B合同、Expected、manifest、selection、source-map、五个输入范围、Oracle、分母、原native、原observation、历史正文、requirements/current或任何执行门禁。没有运行全量pytest或source-only回归，没有模型、quality800/perf80重跑、八组真实回放、正式candidate比较、正式Native/Product评分、PDF/图片读取或渲染、字层、OCR/VLM、网络、GPU/TTS、在线服务、部署、提交或推送。JSON媒体字段只作为声明读取，没有解码。历史执行边界偏差及旧失效记录保留原样。

本轮交付仅为此审查、四份证据数据和必要的状态文档同步；审查数据不建立新Gold或第二份累计质量报告。文档检查只针对允许的非语料文档；不运行会遍历真实候选、PDF或图片的测试。保护对象及最终文档检查结果另见[review-verification.json](data/cross-document-normalization/review-verification.json)。完整验证的11项完成条件中，历史执行、固定集合、原生矩阵、已有链归因、缺口分类、评价边界、成本审查与下一步已处理；固定集合的全范围同版Native→Final追溯仍未满足，不能宣布本轮横向验证完成。
