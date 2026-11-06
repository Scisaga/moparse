# MO-Parse 解析预期

**最高优先级永久规则：对于语料，永远绝不允许机械复核。** 制作、修订、复查和验收只能基于实际打开原件后的逐页视觉阅读与对照；禁止新增、恢复或临时编写机械复查代码，也不得把通用格式、链接、哈希或映射检查用于语料验收。完整执行约束与可复用任务提示见[制作规则](AGENTS.md#最高优先级永久规则语料永远禁止机械复核)。

此规则防止低精度机械检测产生误报、将正确内容改错，并造成反复修改。问题清单中的“调整为”也必须回看原件核实；本轮同时检查历史误改，正确稿保留、错误建议撤销，不能为了符合清单而改写原件。

本语料用于让PDF解析结果直接服务后续知识抽取。当前目录记录500份完整原件、11,419个物理页保留在上级 `pdf/`，本目录不复制原件。2026-10-21按用户要求，旧113份、7,070页的正文与处理说明已全部删除，不归档、不迁移、不复用；随后重新制作了相同113份参考，并留下全量逐页视觉复核及问题修订记录。2026-10-24本轮按用户要求重新视觉复查问题清单，实际范围、误报撤销和历史误改恢复以[解析预期调整清单](review-findings.md)为准，不能把历史完成声明直接当作本轮全文验收。其余387份原件不计入当前参考范围。

[MO-Parse输出规范](moparse-output-spec.md)约束本轮内容：真实数据表语义化，网格排版按实际读序组织；业务图片保全、原位引用并保留图题及原说明，不进行图片语义化。自然段与编号连续，清除独立排版页码和重复页眉页脚。完成状态只能依据实际逐页视觉制作和复查记录。

## 制作方式：逐页视觉阅读，直接撰写

2026-10-21用户明确：**每页由智能体认真视觉阅读原PDF，理解内容、版式和对应关系后直接撰写结果。** 后续执行必须先读本目录的 [AGENTS.md](AGENTS.md)。

1. 打开完整原件，逐页阅读；多栏、宽表、图示和不清晰区域旋转或放大查看，不以抽看少数页面代替全文阅读。
2. 判断原件的真实结构和归属，再直接撰写 `expected.md`。段落、数据表记录及共享范围由视觉阅读确认；业务图片直接保全，不解释图中节点、关系或趋势。
3. 对照原页复核正文，直接修正遗漏与错配；将物理页对应、表图范围、实际复核范围及未解决内容写入`manifest.json`。
4. 逐项记录实际打开的物理页、当前稿内容、原件视觉证据与结论；未看过或无法确认的内容保持待复查或未知，不运行机械复核。

不得用PyMuPDF、pdfplumber、OCR、解析服务结果、PDF文字层、坐标、格线或结构缓存生成预期正文或待改底稿；也不得把答案、字段或图示描述写成代码，再由程序拼接发布。此前采用的自动重建与反复修补方式已经废弃，相关生成代码已删除，不从历史提交或数据盘恢复使用。

工具可用于打开、渲染、旋转、放大PDF，以及原样保存智能体已经直接写好的内容；独立的原件选样工具不属于内容制作或复查流程，不得用于复核语料。程序不得替代阅读、理解或自动改写正文。特殊排版先判断真实结构，不把所有水平排版都当作表格；表格本身也不能按数值基线切断多行字段或共享单元格。

## 文件组织

每份新稿保留正文和规范清单；有业务图片时附图片资产：

- `expected/<文档标识>/expected.md`：完整预期正文，真实数据表按语义表达，图片以相对路径引用。
- `expected/<文档标识>/manifest.json`：原件身份、正文与图片哈希、来源页映射、人工处理说明及未解决项。它是清单，不是第二份解析正文。
- `expected/<文档标识>/assets/`：在原页视觉核定的业务图片。裁图在处理说明记录来源页及渲染方式，不冒称原始嵌入字节。原件PDF不复制；不为本轮参考创建服务ZIP或JSON正文副本。

[code/](code/README.md)保留预览和独立的原件选样工具，不生成预期正文。2026-10-24按用户要求删除全部专用机械复查代码；内容复查只能对照原页视觉进行。本轮与新规范统一，以manifest替代独立`处理说明.md`，不保留双份。[index.html](index.html)直接读取正文和清单，不生成逐份HTML、逐页正文、JSON正文副本、截图集合或转交包。

清单中的`source`保存原PDF文件名、SHA256和总物理页数，`markdown`保存`expected.md`路径与最终字节哈希，`assets`列出每张业务图片的相对路径、SHA256、文件类型及已核定来源页。`source_map`明确完整或部分覆盖，绑定当前正文SHA256；每个`entries`条目使用`source_pages`和`markdown_lines`，页与行从1起算、包含首尾，允许共享和不连续来源范围。人工说明写入`processing_notes`，已知缺口写入`warnings`。视觉修改后的必要记账可计算哈希等字段，只保存该次编辑，不比较、不检查、不验收语料；正文、页映射及语义判断必须来自实际视觉阅读。

规范第1.2节要求正式服务输出包包含`result.md`和`manifest.json`，以及正文引用的全部图片；本参考目录沿用`expected.md`文件名。`source_map`在服务规范中可选，本轮参考为联动核对维护它；`processing_notes`是参考制作的补充说明字段，不是服务必须新增的正文或接口。

## 联动预览

[打开 PDF 与预期联动预览](index.html)。左侧按原件名称选择资料，右侧并排阅读 PDF 与渲染后的 `expected.md`。联动直接读取`manifest.json`的来源映射，按原件物理页定位，不依赖PDF印刷页号。“处理说明”页签展示同一清单的人工说明、来源范围和缺口，原文链接打开JSON，不再解析Markdown表格取得定位。

文件列表中的标签标识各份原件的解析重点，例如表格、跨页表格、结构图、流程图、多栏、公式和扫描件。标签按各份处理说明及原件的实际网格、字形、图像与人工回看依据核定，维护在既有 `pdf/catalog.json` 的 `parsing_tags` 中，CSV 同步使用顿号分隔；标签不代表该文件的解析参考或服务结果已验收，尚未核实的图关系、表头层级和逻辑续表不凭图形数量或相邻页推定。预览不会为了筛选读取全部 PDF 或全文。搜索框下方可多选标签，筛选同时包含所选重点的资料，并与名称搜索组合。筛选只改变左侧列表，右侧当前文档保持原位；搜索、标签、文档和页码随页面地址保留，刷新与返回后可以继续。

目录的 `reference_status` 分别记录 `ready` 与 `pending`：`ready`表示本轮完整新稿及清单已可预览，状态本身不能替代视觉复核证据；`pending`表示新稿尚未完成，可能尚未开始或正在连续撰写长文。待整理原件照常翻页，右栏原位显示“解析预期待整理”，不请求未完成正文、不套用上一份内容，联动暂不可用。切回完整参考恢复原联动选择。`ready`文件缺失仍应报错，不能自动降为待整理。资料范围与状态沿用既有目录，不增加空白预期或第二份全局清单。

跨页续文可以共同指向同一正文行，正文行范围也可能因跨页图表出现重叠或起点倒序；预览保留这种来源关系，不拆改正文。空白页和只有车辆照片的页按处理说明显示其真实状态，不制造对应正文。

从项目根目录启动只读预览服务：

```bash
python3 pdf_sample/parsing/code/preview_server.py --host 127.0.0.1 --port 4175
```

然后访问 [http://127.0.0.1:4175/pdf_sample/parsing/](http://127.0.0.1:4175/pdf_sample/parsing/)。使用 HTTP 地址打开，不能直接双击 HTML 通过 `file://` 读取。页面地址保留所选文档和物理页，刷新或分享该地址后继续对应位置。

PDF.js、Markdown 与公式渲染依赖从项目本地加载，不请求 CDN；依赖维护在 `static/package.json`。首次运行若缺少依赖，在项目根目录执行：

```bash
npm --prefix static ci --ignore-scripts
```

远程使用可以转发 SSH 的 4175 端口；也可将启动参数改为 `--host 0.0.0.0`，通过主机地址从同网浏览。此服务只提供语料预览，无需部署或改动正式 Eventrail API。

## 正文与表格

表格采用[本目录输出规范](moparse-output-spec.md)定义的语义条目表示。GFM 是 GitHub Flavored Markdown 的名称，不能用它代指本项目的表格语义化要求，也不能把竖线表格或 HTML 表格当作已经完成语义化。

一条原表行对应一条语义条目，字段名使用当前有效的完整表头路径。例如已有实际输入中的一行：

```text
item1；项目：募集资金总额；金额(人民币元)：854,700,000.00
```

多层表头中的期间、币种、合并/母公司等限定须进入对应字段或明确的共享语境；同一行各字段的关联不能丢失。不把表格归纳成摘要，不先替下游抽取器生成本体事实。

人工层级分隔采用半角 ` / `。日期、单位和完整字段先按来源语义组织，例如 `As of December 31, 2024（RMB’000）：1,358,296`；不把换行词语拼成层级，不让单位夹在日期与年份之间。原文中的单位、比率、名称和日期斜杠保留自身含义。表格中的空白、勾号、圆点、票数及百分比也须保持各自的真实列对应。

- 原文名称、条款、否定、条件、计划/已完成、日期、单位、比例、正负号、小数精度、括号和脚注均保留，不修改原件自身的矛盾。
- 正文不混入文件哈希、核验声明、人工页标题或修复指令。这些说明仅写入对应的处理说明。
- 物理行宽和换页不构成自然段；同段续文连接，序号与所属内容保持在同一条目，多栏按实际栏顺序阅读。独立排版页码、重复页眉页脚从正文移除，物理页到正文行的映射保留在处理说明；证券代码、年度、条款号、业务附注、签章日期、正文页码引用及目录指向按原义保留，不批量删除纯数字行。
- 表格保留原行的完整关联，多层表头按真实路径嵌入字段；表内换表头只对相应行段生效，跨页继承须核对同一表及实际字段，依据见处理说明。
- 字段使用来源实际语义，不生成 `C1`、`C2` 或“原列1”等伪字段。表头缺失时回看原件核定；仍无法确认时明确缺口，不套用邻表或编造列义。单元格内部的分项、条件及注释在所属字段内保留。
- 合并格按其真实覆盖范围表达共享语义，处理说明保留必要的原网格范围，R/C均从1开始。共享金额不复制成多项事实；覆盖格不能当成新的空值，真实空白、横线、不适用及零分别核对。
- 脚注与数值分开；`6,606.57^{1}`中的上标1是脚注，不能合入金额。平方米等单位中的上标同样保留。
- 单位、主体、期间、合并/母公司口径和注释按原文范围关联；左右并排的不同表区分开阅读，不把同一横排的项目配成同一事实。
- 看不清的局部以 `�` 表示缺口，具体原因写入处理说明，不从其它页、旧正文或知识库回填。

## 业务图片

按新规范，股权图、流程图、组织图、统计图及照片以完整来源图片交付，正文保留原位置引用、图题及已有说明。签名与印章同样保全。图片替代文字采用来源图题或中性名称；不生成图意，不恢复节点、连线、层级、比例归属或趋势，不把图片语义化列为本轮缺口。

图片区域必须逐页视觉核定。多对象或矢量图形可按完整图域渲染；处理说明记录来源物理页、区域及提取或渲染方式，不冒称原始嵌入图片。真实数据表依然逐行语义表达，不能用表格截图替代。

## 视觉复查与修订记录

审查结果与当前完成状态统一维护在[解析预期调整清单](review-findings.md)，分别记录历史审查与本轮逐项视觉复查。清单按原文档用“位置、当前内容、调整为、原因”四列保留原定位及复查结论，复杂项在表下补充完整定位与必要说明；已确认的原件限制另列一表，不计入内容缺陷。本轮没有再次重读全部7,070页，不重新认定历史全文验收结论；具体核定结果以清单开头的本轮记录为准，不能仅凭条目存在或旧修复声明认定正确。

发现问题时回看同一原件对应页，直接重写错误内容并复核相关前后页；不能修改生成规则后重新输出正文，也不能以某几个期望数值回填。修改后的正文与处理说明一起核对，保证单位、期间、主体、共享范围、脚注及图片位置真实成立。

此前“100份全文完成”“54项语义回归通过”等表述来自程序生成、机械检查及局部核对，不能证明逐页视觉制作与全文内容正确。旧113份参考已全部删除，不保留旧稿或缓存底稿，不沿用其完成声明。重新制作后的历史审查记录也须与本轮实际查看范围分开；本轮已经发现并恢复历史误改，不能因旧记录写过“通过”而跳过原件或延续错误建议。

正文生成器、表格及图示重建、段落拼接、模板发布和相应规则测试已删除；语料专用机械复查代码及缓存也已删除，只读预览继续保留。代码不得重新承担参考答案生成或机械复核；实际MO-Parse内容验收和模型金标另按对应任务开展。

2026-10-24起，内容复查仅基于原PDF页面的实际视觉阅读，逐项对照当前正文、图像及来源归属。专用机械复查代码已经删除，不再提供脚本检查命令；已有历史检查记录只按当时事实保留，不能作为本轮视觉复查结论。当前复查进度与实际发现维护在[解析预期调整清单](review-findings.md)。

## 新增复杂原生PDF

2026-10-19新增以下20份官方完整原件。原件选样阶段曾核对文件身份、页数、文字层并抽看下面列出的复杂页面；这类选样元数据不进入预期制作链。页码均为PDF物理页。对应当前参考均已纳入113份参考的全量逐页视觉复核，修订状态见[解析预期调整清单](review-findings.md)；尚未进行本轮MO-Parse实际内容回归。原件哈希和来源沿用已有 `pdf/catalog.json`/`catalog.csv`，不再生成新清单。

| 完整原件 | 页数 | 已查看的复杂页面与抽取难点 | 官方来源 |
| --- | --- | --- | --- |
| [招商银行2024年报](../pdf/complex-cmb-2024-annual.pdf) | 363 | 第41、244页：集团/公司口径；多币种债券、期限、利率及脚注组成的密集无框宽表 | [CNINFO](https://static.cninfo.com.cn/finalpage/2025-03-25/1222896773.PDF) |
| [比亚迪2024年报（中英双语）](../pdf/complex-byd-2024-annual.pdf) | 374 | 第6、373页：图文时间线；中英双语行名、五年对比、重列标记与括号负数 | [HKEX](https://www.hkexnews.hk/listedco/listconews/sehk/2025/0324/2025032401238.pdf) |
| [宁德时代2025年H股招股章程](../pdf/complex-catl-2025-prospectus.pdf) | 626 | 第179–180、415页：发售前后股权架构、节点比例与脚注；纵向物理页内旋转90度的多层宽表 | [HKEX](https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0512/2025051200006_c.pdf) |
| [小米2024年报（英文）](../pdf/complex-xiaomi-2024-annual.pdf) | 379 | 第9、317页：带期间及单位的信息图；固定资产分类、多层行组和滚动变动表 | [小米](https://ir.mi.com/system/files-encrypted/nasdaq_kms/assets/2025/04/24/5-27-15/%E8%8B%B1%E6%96%87.pdf) |
| [NVIDIA FY2025年度报告](../pdf/complex-nvidia-2025-annual.pdf) | 181 | 第11–14页多栏正文、矩阵勾号、跨年薪酬、三年财务数据、章程增删标记；业务图片与原有说明保全 | [NVIDIA](https://s201.q4cdn.com/141608511/files/doc_financials/2025/annual/NVIDIA-2025-Annual-Report.pdf) |
| [贵州茅台2024年报](../pdf/complex-moutai-2024-annual.pdf) | 143 | 第15、98页：同表产量/销量/收入多单位；固定资产增减与折旧分组、真实空白 | [CNINFO](https://static.cninfo.com.cn/finalpage/2025-04-03/1222993920.PDF) |
| [美的集团2024年报](../pdf/complex-midea-2024-annual.pdf) | 295 | 第49、160页分组及合并/公司口径，第92页多人共享股数，第97–118页跨页排放口，第287页共有估值与各输入值敏感性 | [CNINFO](https://static.cninfo.com.cn/finalpage/2025-03-29/1222951181.PDF) |
| [中国石化2024年报](../pdf/complex-sinopec-2024-annual.pdf) | 222 | 第16、204页：三栏正文；多家附属公司各自两年数据，三张密集表连续排布 | [HKEX](https://www1.hkexnews.hk/listedco/listconews/sehk/2025/0323/2025032300008_c.pdf) |
| [腾讯2025年全球中期票据计划发行通函（英文）](../pdf/complex-tencent-2025-bond-programme.pdf) | 705 | 第88、680页：多层债券条件；附录内嵌2023年报及股权激励表，发行年份、附录年份与页码须分开 | [腾讯](https://static.www.tencent.com/uploads/2025/09/16/5a0b274dacf222d262734936c3508821.pdf) |
| [阿里巴巴FY2025年报（英文）](../pdf/complex-alibaba-2025-annual.pdf) | 324 | 第48、318页：附属公司与VIE描述；US GAAP与IFRS调节、多列多年度独立表 | [HKEX](https://www.hkexnews.hk/listedco/listconews/sehk/2025/0626/2025062601064.pdf) |
| [顺丰控股2024年报](../pdf/complex-sf-2024-annual.pdf) | 190 | 第87、139页：审计事项/应对两栏并排；飞机等资产的成本、折旧与账面值矩阵 | [HKEX](https://www.hkexnews.hk/listedco/listconews/sehk/2025/0407/2025040701401_c.pdf) |
| [中国平安2024年度业绩公告（含完整年报，英文）](../pdf/complex-pingan-2024-annual.pdf) | 364 | 第193、334页：保险负债与金融负债；到期时段矩阵、未定期/即期分类、衍生工具现金流 | [中国平安](https://group.pingan.com/resource/pingan/IR-Docs/2025/pingan-ar24-report.pdf) |
| [华为2024年报](../pdf/complex-huawei-2024-annual.pdf) | 148 | 第38、90页：多图图注、双栏业务说明与脚注；资产成本/折旧/减值多区块宽表 | [华为](https://www.huawei.com/minisite/annual-report-download/annual_report_2024_cn.pdf) |
| [IEA Energy and AI 2025](../pdf/complex-iea-energy-ai-2025.pdf) | 304 | 第56、258页：分组柱图、图例、专栏；多情景/多年度表与2035年探索情景限定 | [IEA](https://iea.blob.core.windows.net/assets/de9dea13-b07d-42c5-a398-d1b3ae17d866/EnergyandAI.pdf) |
| [中国金融稳定报告2024](../pdf/complex-pboc-stability-2024.pdf) | 120 | 第18、117页：双栏正文、专栏与折线图；旋转年度/同比宽表及统计范围脚注 | [中国人民银行](https://www.pbc.gov.cn/jinrongwendingju/146766/146772/08b4b564775242619f8386232f9f4fae/2025010317243072518.pdf) |
| [中国移动2024年报（英文）](../pdf/complex-china-mobile-2024-annual.pdf) | 180 | 第12、179页：人物任职及任期；五年财务对比、多行表头与百万单位 | [中国移动](https://www.chinamobileltd.com/en/ir/reports/ar2024.pdf) |
| [国泰君安换股吸收合并海通证券报告书](../pdf/complex-guotai-haitong-2024-merger.pdf) | 428 | 第18、287页：跨页大合并格、换股价/换股比例；两公司与多期间财务资料须各守范围 | [上海证券交易所](https://static.sse.com.cn/stock/disclosure/announcement/c/202412/601211_20241223_EPHT.pdf) |
| [香港交易所2024年报（英文）](../pdf/complex-hkex-2024-annual.pdf) | 240 | 第37、124页：并排人物履历及别名；按人/授予批次分组、多个归属日期与脚注的奖励股份表 | [HKEX集团](https://www.hkexgroup.com/-/media/HKEX-Group-Site/ssd/Investor-Relations/Regulatory-Reports/documents/2025/250317ar_e_WCAG.pdf) |
| [华为技术总第096期](../pdf/complex-huaweitech-2024-096.pdf) | 58 | 第15、23页：一个物理页并排两张刊页，多栏阅读顺序、网络架构连线、图注与参考文献 | [华为](https://www-file.huawei.com/dam/asset/view/063aa82734f149a786a844c6d8f2bb0c.pdf?la=zh) |
| [BIS Annual Economic Report 2024](../pdf/complex-bis-economic-2024.pdf) | 150 | 第32、71页：专栏跨页、组合统计图、不同坐标轴、置信区间、图例与资料来源 | [BIS](https://www.bis.org/publications/aer-2024.pdf) |

新增覆盖的是供后续知识抽取使用的原生版式难点；带文字层不等于解析正确，短公告回归也不能代表长文件已通过。图像按新规范保全原图与已有说明，不解释图中数字、股权或网络关系。

## 当前113份参考目录

本目录保留此前制作记录列出的113份、7,070页参考；两份长文档的20页缺口合入情况保留在下文。2026-10-24本轮仅重新视觉复查清单的728项问题及4项原件限制，不重述为113份全文重新验收。美的物理210页金额叠印、利元亨证照及名单遮挡继续保留未知；已确认的历史误改按原件恢复。其余387份不在当前参考范围，详细状态以[解析预期调整清单](review-findings.md)为准。

2026-10-22按用户要求采用[协调与生成分工](AGENTS.md#任务提示面向知识抽取的解析参考)：协调者分配、检查、回收，生成者逐页记录、撰写和复核。该阶段新增复核517页，已把所有未拦截页段处理至两份原件末页并回收；遇输出流拦截则保留已有结果、记录当前尝试页，另派生成者跳过该页续作，不反复重试，不跨缺页推断补写。历史日志只能定位失败批次时，记录页段而不猜测具体触发页。该阶段未调用MO-Parse，不能将输出流错误判断为解析服务故障。

2026-10-23历史合入记录：独立补稿的20页合入两份原文档，其中12页由人工逐页视觉撰写并复核，8页按当时用户指定MO-Parse服务生成后逐页对照原图整理、复核。原记录同时记载正文、人工来源映射、哈希及业务图片同步，并设置清单`source_map.status=complete`、目录`reference_status=ready`。该历史来源不授权今后调用服务生成或机械复核语料；原独立补稿入口已不沿用，当前内容入口见下表。状态字段及合入记录不等于MO-Parse全文验收或金标完成。以下均为PDF物理页：

| 补齐原件 | 已回收页数 | 来源映射 | 正文与清单 |
| --- | --- | --- | --- |
| 阿里巴巴FY2025年报 | 324/324 | 全部物理页已覆盖 | [expected.md](expected/complex-alibaba-2025-annual/expected.md)、[manifest.json](expected/complex-alibaba-2025-annual/manifest.json) |
| 腾讯2025年全球中期票据计划发行通函 | 705/705 | 全部物理页已覆盖 | [expected.md](expected/complex-tencent-2025-bond-programme/expected.md)、[manifest.json](expected/complex-tencent-2025-bond-programme/manifest.json) |

以下列出当前113份完整参考，每份原件仅列一次：

| 原件 | 预期正文 | 清单与处理说明 |
| --- | --- | --- |
| [招商银行2024年度报告（A股）](../pdf/complex-cmb-2024-annual.pdf) | [expected.md](expected/complex-cmb-2024-annual/expected.md) | [manifest.json](expected/complex-cmb-2024-annual/manifest.json) |
| [小米集团2024年报（英文）](../pdf/complex-xiaomi-2024-annual.pdf) | [expected.md](expected/complex-xiaomi-2024-annual/expected.md) | [manifest.json](expected/complex-xiaomi-2024-annual/manifest.json) |
| [中国平安2024年度业绩公告（含完整年报，英文）](../pdf/complex-pingan-2024-annual.pdf) | [expected.md](expected/complex-pingan-2024-annual/expected.md) | [manifest.json](expected/complex-pingan-2024-annual/manifest.json) |
| [比亚迪2024年报（中英双语）](../pdf/complex-byd-2024-annual.pdf) | [expected.md](expected/complex-byd-2024-annual/expected.md) | [manifest.json](expected/complex-byd-2024-annual/manifest.json) |
| [宁德时代2025年H股招股章程](../pdf/complex-catl-2025-prospectus.pdf) | [expected.md](expected/complex-catl-2025-prospectus/expected.md) | [manifest.json](expected/complex-catl-2025-prospectus/manifest.json) |
| [国泰君安换股吸收合并海通证券报告书](../pdf/complex-guotai-haitong-2024-merger.pdf) | [expected.md](expected/complex-guotai-haitong-2024-merger/expected.md) | [manifest.json](expected/complex-guotai-haitong-2024-merger/manifest.json) |
| [10726562.pdf](../pdf/10726562.pdf) | [expected.md](expected/10726562/expected.md) | [manifest.json](expected/10726562/manifest.json) |
| [1200454112.pdf](../pdf/1200454112.pdf) | [expected.md](expected/1200454112/expected.md) | [manifest.json](expected/1200454112/manifest.json) |
| [1200467021.pdf](../pdf/1200467021.pdf) | [expected.md](expected/1200467021/expected.md) | [manifest.json](expected/1200467021/manifest.json) |
| [1200694562.pdf](../pdf/1200694562.pdf) | [expected.md](expected/1200694562/expected.md) | [manifest.json](expected/1200694562/manifest.json) |
| [1200694910.pdf](../pdf/1200694910.pdf) | [expected.md](expected/1200694910/expected.md) | [manifest.json](expected/1200694910/manifest.json) |
| [1200707112.pdf](../pdf/1200707112.pdf) | [expected.md](expected/1200707112/expected.md) | [manifest.json](expected/1200707112/manifest.json) |
| [1200716038.pdf](../pdf/1200716038.pdf) | [expected.md](expected/1200716038/expected.md) | [manifest.json](expected/1200716038/manifest.json) |
| [1200767518.pdf](../pdf/1200767518.pdf) | [expected.md](expected/1200767518/expected.md) | [manifest.json](expected/1200767518/manifest.json) |
| [1200767576.pdf](../pdf/1200767576.pdf) | [expected.md](expected/1200767576/expected.md) | [manifest.json](expected/1200767576/manifest.json) |
| [1200778318.pdf](../pdf/1200778318.pdf) | [expected.md](expected/1200778318/expected.md) | [manifest.json](expected/1200778318/manifest.json) |
| [1200799174.pdf](../pdf/1200799174.pdf) | [expected.md](expected/1200799174/expected.md) | [manifest.json](expected/1200799174/manifest.json) |
| [1200800787.pdf](../pdf/1200800787.pdf) | [expected.md](expected/1200800787/expected.md) | [manifest.json](expected/1200800787/manifest.json) |
| [1200838381.pdf](../pdf/1200838381.pdf) | [expected.md](expected/1200838381/expected.md) | [manifest.json](expected/1200838381/manifest.json) |
| [1200838391.pdf](../pdf/1200838391.pdf) | [expected.md](expected/1200838391/expected.md) | [manifest.json](expected/1200838391/manifest.json) |
| [1200838888.pdf](../pdf/1200838888.pdf) | [expected.md](expected/1200838888/expected.md) | [manifest.json](expected/1200838888/manifest.json) |
| [1200921575.pdf](../pdf/1200921575.pdf) | [expected.md](expected/1200921575/expected.md) | [manifest.json](expected/1200921575/manifest.json) |
| [1200921577.pdf](../pdf/1200921577.pdf) | [expected.md](expected/1200921577/expected.md) | [manifest.json](expected/1200921577/manifest.json) |
| [1200930858.pdf](../pdf/1200930858.pdf) | [expected.md](expected/1200930858/expected.md) | [manifest.json](expected/1200930858/manifest.json) |
| [1200933975.pdf](../pdf/1200933975.pdf) | [expected.md](expected/1200933975/expected.md) | [manifest.json](expected/1200933975/manifest.json) |
| [1200967992.pdf](../pdf/1200967992.pdf) | [expected.md](expected/1200967992/expected.md) | [manifest.json](expected/1200967992/manifest.json) |
| [1200968001.pdf](../pdf/1200968001.pdf) | [expected.md](expected/1200968001/expected.md) | [manifest.json](expected/1200968001/manifest.json) |
| [1200975009.pdf](../pdf/1200975009.pdf) | [expected.md](expected/1200975009/expected.md) | [manifest.json](expected/1200975009/manifest.json) |
| [1201786046.pdf](../pdf/1201786046.pdf) | [expected.md](expected/1201786046/expected.md) | [manifest.json](expected/1201786046/manifest.json) |
| [1201791349.pdf](../pdf/1201791349.pdf) | [expected.md](expected/1201791349/expected.md) | [manifest.json](expected/1201791349/manifest.json) |
| [1201816142.pdf](../pdf/1201816142.pdf) | [expected.md](expected/1201816142/expected.md) | [manifest.json](expected/1201816142/manifest.json) |
| [1201830493.pdf](../pdf/1201830493.pdf) | [expected.md](expected/1201830493/expected.md) | [manifest.json](expected/1201830493/manifest.json) |
| [1201860324.pdf](../pdf/1201860324.pdf) | [expected.md](expected/1201860324/expected.md) | [manifest.json](expected/1201860324/manifest.json) |
| [1201917092.pdf](../pdf/1201917092.pdf) | [expected.md](expected/1201917092/expected.md) | [manifest.json](expected/1201917092/manifest.json) |
| [1202033380.pdf](../pdf/1202033380.pdf) | [expected.md](expected/1202033380/expected.md) | [manifest.json](expected/1202033380/manifest.json) |
| [1202164176.pdf](../pdf/1202164176.pdf) | [expected.md](expected/1202164176/expected.md) | [manifest.json](expected/1202164176/manifest.json) |
| [1202180643.pdf](../pdf/1202180643.pdf) | [expected.md](expected/1202180643/expected.md) | [manifest.json](expected/1202180643/manifest.json) |
| [1202194188.pdf](../pdf/1202194188.pdf) | [expected.md](expected/1202194188/expected.md) | [manifest.json](expected/1202194188/manifest.json) |
| [1202194191.pdf](../pdf/1202194191.pdf) | [expected.md](expected/1202194191/expected.md) | [manifest.json](expected/1202194191/manifest.json) |
| [1202202591.pdf](../pdf/1202202591.pdf) | [expected.md](expected/1202202591/expected.md) | [manifest.json](expected/1202202591/manifest.json) |
| [1202506196.pdf](../pdf/1202506196.pdf) | [expected.md](expected/1202506196/expected.md) | [manifest.json](expected/1202506196/manifest.json) |
| [1202524093.pdf](../pdf/1202524093.pdf) | [expected.md](expected/1202524093/expected.md) | [manifest.json](expected/1202524093/manifest.json) |
| [1202650764.pdf](../pdf/1202650764.pdf) | [expected.md](expected/1202650764/expected.md) | [manifest.json](expected/1202650764/manifest.json) |
| [1202668810.pdf](../pdf/1202668810.pdf) | [expected.md](expected/1202668810/expected.md) | [manifest.json](expected/1202668810/manifest.json) |
| [1202854267.pdf](../pdf/1202854267.pdf) | [expected.md](expected/1202854267/expected.md) | [manifest.json](expected/1202854267/manifest.json) |
| [1202969650.pdf](../pdf/1202969650.pdf) | [expected.md](expected/1202969650/expected.md) | [manifest.json](expected/1202969650/manifest.json) |
| [1203209331.pdf](../pdf/1203209331.pdf) | [expected.md](expected/1203209331/expected.md) | [manifest.json](expected/1203209331/manifest.json) |
| [1203248188.pdf](../pdf/1203248188.pdf) | [expected.md](expected/1203248188/expected.md) | [manifest.json](expected/1203248188/manifest.json) |
| [1203531870.pdf](../pdf/1203531870.pdf) | [expected.md](expected/1203531870/expected.md) | [manifest.json](expected/1203531870/manifest.json) |
| [1203588693.pdf](../pdf/1203588693.pdf) | [expected.md](expected/1203588693/expected.md) | [manifest.json](expected/1203588693/manifest.json) |
| [1203617015.pdf](../pdf/1203617015.pdf) | [expected.md](expected/1203617015/expected.md) | [manifest.json](expected/1203617015/manifest.json) |
| [1203675121.pdf](../pdf/1203675121.pdf) | [expected.md](expected/1203675121/expected.md) | [manifest.json](expected/1203675121/manifest.json) |
| [1203675127.pdf](../pdf/1203675127.pdf) | [expected.md](expected/1203675127/expected.md) | [manifest.json](expected/1203675127/manifest.json) |
| [1203694667.pdf](../pdf/1203694667.pdf) | [expected.md](expected/1203694667/expected.md) | [manifest.json](expected/1203694667/manifest.json) |
| [1204887329.pdf](../pdf/1204887329.pdf) | [expected.md](expected/1204887329/expected.md) | [manifest.json](expected/1204887329/manifest.json) |
| [1206396628.pdf](../pdf/1206396628.pdf) | [expected.md](expected/1206396628/expected.md) | [manifest.json](expected/1206396628/manifest.json) |
| [1207153364.pdf](../pdf/1207153364.pdf) | [expected.md](expected/1207153364/expected.md) | [manifest.json](expected/1207153364/manifest.json) |
| [1207353786.pdf](../pdf/1207353786.pdf) | [expected.md](expected/1207353786/expected.md) | [manifest.json](expected/1207353786/manifest.json) |
| [1207353803.pdf](../pdf/1207353803.pdf) | [expected.md](expected/1207353803/expected.md) | [manifest.json](expected/1207353803/manifest.json) |
| [1210860446.pdf](../pdf/1210860446.pdf) | [expected.md](expected/1210860446/expected.md) | [manifest.json](expected/1210860446/manifest.json) |
| [1211290753.pdf](../pdf/1211290753.pdf) | [expected.md](expected/1211290753/expected.md) | [manifest.json](expected/1211290753/manifest.json) |
| [1216072184.pdf](../pdf/1216072184.pdf) | [expected.md](expected/1216072184/expected.md) | [manifest.json](expected/1216072184/manifest.json) |
| [1217156345.pdf](../pdf/1217156345.pdf) | [expected.md](expected/1217156345/expected.md) | [manifest.json](expected/1217156345/manifest.json) |
| [1217156349.pdf](../pdf/1217156349.pdf) | [expected.md](expected/1217156349/expected.md) | [manifest.json](expected/1217156349/manifest.json) |
| [1217451893.pdf](../pdf/1217451893.pdf) | [expected.md](expected/1217451893/expected.md) | [manifest.json](expected/1217451893/manifest.json) |
| [1219858186.pdf](../pdf/1219858186.pdf) | [expected.md](expected/1219858186/expected.md) | [manifest.json](expected/1219858186/manifest.json) |
| [1225464761.pdf](../pdf/1225464761.pdf) | [expected.md](expected/1225464761/expected.md) | [manifest.json](expected/1225464761/manifest.json) |
| [1225473526.pdf](../pdf/1225473526.pdf) | [expected.md](expected/1225473526/expected.md) | [manifest.json](expected/1225473526/manifest.json) |
| [1225474139.pdf](../pdf/1225474139.pdf) | [expected.md](expected/1225474139/expected.md) | [manifest.json](expected/1225474139/manifest.json) |
| [1225474693.pdf](../pdf/1225474693.pdf) | [expected.md](expected/1225474693/expected.md) | [manifest.json](expected/1225474693/manifest.json) |
| [1225474739.pdf](../pdf/1225474739.pdf) | [预期正文](expected/1225474739/expected.md) | [manifest](expected/1225474739/manifest.json) |
| [1225475333.pdf](../pdf/1225475333.pdf) | [expected.md](expected/1225475333/expected.md) | [manifest.json](expected/1225475333/manifest.json) |
| [1225475375.pdf](../pdf/1225475375.pdf) | [expected.md](expected/1225475375/expected.md) | [manifest.json](expected/1225475375/manifest.json) |
| [1225475642.pdf](../pdf/1225475642.pdf) | [预期正文](expected/1225475642/expected.md) | [manifest](expected/1225475642/manifest.json) |
| [43433155.pdf](../pdf/43433155.pdf) | [expected.md](expected/43433155/expected.md) | [manifest.json](expected/43433155/manifest.json) |
| [bse-08b17aa6c5295fc4.pdf](../pdf/bse-08b17aa6c5295fc4.pdf) | [expected.md](expected/bse-08b17aa6c5295fc4/expected.md) | [manifest.json](expected/bse-08b17aa6c5295fc4/manifest.json) |
| [bse-13beac4ea1e02995.pdf](../pdf/bse-13beac4ea1e02995.pdf) | [expected.md](expected/bse-13beac4ea1e02995/expected.md) | [manifest.json](expected/bse-13beac4ea1e02995/manifest.json) |
| [bse-1e65d2587f60a402.pdf](../pdf/bse-1e65d2587f60a402.pdf) | [expected.md](expected/bse-1e65d2587f60a402/expected.md) | [manifest.json](expected/bse-1e65d2587f60a402/manifest.json) |
| [bse-1fcecd9347e71a8e.pdf](../pdf/bse-1fcecd9347e71a8e.pdf) | [expected.md](expected/bse-1fcecd9347e71a8e/expected.md) | [manifest.json](expected/bse-1fcecd9347e71a8e/manifest.json) |
| [complex-alibaba-2025-annual.pdf](../pdf/complex-alibaba-2025-annual.pdf) | [expected.md](expected/complex-alibaba-2025-annual/expected.md) | [manifest.json](expected/complex-alibaba-2025-annual/manifest.json) |
| [complex-bis-economic-2024.pdf](../pdf/complex-bis-economic-2024.pdf) | [expected.md](expected/complex-bis-economic-2024/expected.md) | [manifest.json](expected/complex-bis-economic-2024/manifest.json) |
| [complex-china-mobile-2024-annual.pdf](../pdf/complex-china-mobile-2024-annual.pdf) | [expected.md](expected/complex-china-mobile-2024-annual/expected.md) | [manifest.json](expected/complex-china-mobile-2024-annual/manifest.json) |
| [complex-hkex-2024-annual.pdf](../pdf/complex-hkex-2024-annual.pdf) | [expected.md](expected/complex-hkex-2024-annual/expected.md) | [manifest.json](expected/complex-hkex-2024-annual/manifest.json) |
| [complex-huawei-2024-annual.pdf](../pdf/complex-huawei-2024-annual.pdf) | [expected.md](expected/complex-huawei-2024-annual/expected.md) | [manifest.json](expected/complex-huawei-2024-annual/manifest.json) |
| [complex-huaweitech-2024-096.pdf](../pdf/complex-huaweitech-2024-096.pdf) | [expected.md](expected/complex-huaweitech-2024-096/expected.md) | [manifest.json](expected/complex-huaweitech-2024-096/manifest.json) |
| [complex-iea-energy-ai-2025.pdf](../pdf/complex-iea-energy-ai-2025.pdf) | [预期正文](expected/complex-iea-energy-ai-2025/expected.md) | [清单](expected/complex-iea-energy-ai-2025/manifest.json) |
| [complex-midea-2024-annual.pdf](../pdf/complex-midea-2024-annual.pdf) | [预期正文](expected/complex-midea-2024-annual/expected.md) | [清单](expected/complex-midea-2024-annual/manifest.json) |
| [complex-moutai-2024-annual.pdf](../pdf/complex-moutai-2024-annual.pdf) | [expected.md](expected/complex-moutai-2024-annual/expected.md) | [manifest.json](expected/complex-moutai-2024-annual/manifest.json) |
| [complex-nvidia-2025-annual.pdf](../pdf/complex-nvidia-2025-annual.pdf) | [expected.md](expected/complex-nvidia-2025-annual/expected.md) | [manifest.json](expected/complex-nvidia-2025-annual/manifest.json) |
| [complex-pboc-stability-2024.pdf](../pdf/complex-pboc-stability-2024.pdf) | [预期正文](expected/complex-pboc-stability-2024/expected.md) | [清单](expected/complex-pboc-stability-2024/manifest.json) |
| [complex-sf-2024-annual.pdf](../pdf/complex-sf-2024-annual.pdf) | [expected.md](expected/complex-sf-2024-annual/expected.md) | [manifest.json](expected/complex-sf-2024-annual/manifest.json) |
| [complex-sinopec-2024-annual.pdf](../pdf/complex-sinopec-2024-annual.pdf) | [expected.md](expected/complex-sinopec-2024-annual/expected.md) | [manifest.json](expected/complex-sinopec-2024-annual/manifest.json) |
| [complex-tencent-2025-bond-programme.pdf](../pdf/complex-tencent-2025-bond-programme.pdf) | [expected.md](expected/complex-tencent-2025-bond-programme/expected.md) | [manifest.json](expected/complex-tencent-2025-bond-programme/manifest.json) |
| [sse-10e39be0f06bd59f.pdf](../pdf/sse-10e39be0f06bd59f.pdf) | [expected.md](expected/sse-10e39be0f06bd59f/expected.md) | [manifest.json](expected/sse-10e39be0f06bd59f/manifest.json) |
| [sse-13df676e3995fb86.pdf](../pdf/sse-13df676e3995fb86.pdf) | [expected.md](expected/sse-13df676e3995fb86/expected.md) | [manifest.json](expected/sse-13df676e3995fb86/manifest.json) |
| [sse-444ec1bf344edea0.pdf](../pdf/sse-444ec1bf344edea0.pdf) | [expected.md](expected/sse-444ec1bf344edea0/expected.md) | [manifest.json](expected/sse-444ec1bf344edea0/manifest.json) |
| [szse-0f5d6dd27e224832.pdf](../pdf/szse-0f5d6dd27e224832.pdf) | [expected.md](expected/szse-0f5d6dd27e224832/expected.md) | [manifest.json](expected/szse-0f5d6dd27e224832/manifest.json) |
| [szse-1031f1efdd7da997.pdf](../pdf/szse-1031f1efdd7da997.pdf) | [expected.md](expected/szse-1031f1efdd7da997/expected.md) | [manifest.json](expected/szse-1031f1efdd7da997/manifest.json) |
| [szse-134dc729c2ee29bc.pdf](../pdf/szse-134dc729c2ee29bc.pdf) | [expected.md](expected/szse-134dc729c2ee29bc/expected.md) | [manifest.json](expected/szse-134dc729c2ee29bc/manifest.json) |
| [szse-623c57cdfb6048cc.pdf](../pdf/szse-623c57cdfb6048cc.pdf) | [expected.md](expected/szse-623c57cdfb6048cc/expected.md) | [manifest.json](expected/szse-623c57cdfb6048cc/manifest.json) |
| [collection-cn-1207461295.pdf](../pdf/collection-cn-1207461295.pdf) | [expected.md](expected/collection-cn-1207461295/expected.md) | [manifest.json](expected/collection-cn-1207461295/manifest.json) |
| [collection-cn-1208675667.pdf](../pdf/collection-cn-1208675667.pdf) | [expected.md](expected/collection-cn-1208675667/expected.md) | [manifest.json](expected/collection-cn-1208675667/manifest.json) |
| [collection-cn-1209142176.pdf](../pdf/collection-cn-1209142176.pdf) | [expected.md](expected/collection-cn-1209142176/expected.md) | [manifest.json](expected/collection-cn-1209142176/manifest.json) |
| [collection-cn-1217139160.pdf](../pdf/collection-cn-1217139160.pdf) | [expected.md](expected/collection-cn-1217139160/expected.md) | [manifest.json](expected/collection-cn-1217139160/manifest.json) |
| [collection-cn-1217635706.pdf](../pdf/collection-cn-1217635706.pdf) | [expected.md](expected/collection-cn-1217635706/expected.md) | [manifest.json](expected/collection-cn-1217635706/manifest.json) |
| [collection-cn-1222944784.pdf](../pdf/collection-cn-1222944784.pdf) | [expected.md](expected/collection-cn-1222944784/expected.md) | [manifest.json](expected/collection-cn-1222944784/manifest.json) |
| [collection-cn-1224066007.pdf](../pdf/collection-cn-1224066007.pdf) | [expected.md](expected/collection-cn-1224066007/expected.md) | [manifest.json](expected/collection-cn-1224066007/manifest.json) |
| [collection-cn-1225415718.pdf](../pdf/collection-cn-1225415718.pdf) | [expected.md](expected/collection-cn-1225415718/expected.md) | [manifest.json](expected/collection-cn-1225415718/manifest.json) |
| [collection-cn-37183712.pdf](../pdf/collection-cn-37183712.pdf) | [expected.md](expected/collection-cn-37183712/expected.md) | [manifest.json](expected/collection-cn-37183712/manifest.json) |
| [collection-cn-59270407.pdf](../pdf/collection-cn-59270407.pdf) | [expected.md](expected/collection-cn-59270407/expected.md) | [manifest.json](expected/collection-cn-59270407/manifest.json) |
| [collection-cn-60579841.pdf](../pdf/collection-cn-60579841.pdf) | [expected.md](expected/collection-cn-60579841/expected.md) | [manifest.json](expected/collection-cn-60579841/manifest.json) |
| [collection-hk-1224811245.pdf](../pdf/collection-hk-1224811245.pdf) | [expected.md](expected/collection-hk-1224811245/expected.md) | [manifest.json](expected/collection-hk-1224811245/manifest.json) |
| [collection-hk-1224998551.pdf](../pdf/collection-hk-1224998551.pdf) | [expected.md](expected/collection-hk-1224998551/expected.md) | [manifest.json](expected/collection-hk-1224998551/manifest.json) |
