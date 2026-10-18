# 跨页表头修复验收（2026-10-15）

> 历史记录：项目于 2026-10-18 更名为 moparse。下文保留当时的名称、路径和部署标识；当前配置见 [部署说明](deployment.md)。

已修复并部署至 `http://10.0.6.22:12303/`。对完整 4 页原件进行真实
`POST /v1/content/parse` 重跑，`scan_policy=auto`，未提交 `unit_range`。
最终 Markdown 保留第 2 页和第 3 页各自的完整表头及所属财务行。

## 原件、复现和实际错误路径

- 文件：`pdf_sample/1225474693.pdf`，浙江出版传媒股份有限公司2026年半年度报告摘要。
- SHA256：`dc7f5b3bfdc5a5c69b9cf4b2a9e0d28e2f9ee0b2464770fb8a910fea688ee775`。
- 原任务：`job_01M4XT6Y66G6X9EWKYHPB8B4WV`。
- 修复前重新复现任务：`job_01M4XX8Y9VW27G7VMXCC8T7EYT`，HTTP 200，4/4 页。
- 修复后验收任务：`job_01M4XXZVGFK9DF8BX3JAEEM2ZJ`，HTTP 200，4/4 页。

修复前 `app/services/table_service.py` 的 `header_signature` 只读取第一行；
`_headers_match`（原第 294 行）以 `SequenceMatcher(...).ratio() >= 0.80` 判定相同。
第 2、3 页表头去除排版空白后的相似度为 **0.8076923076923077**。
两片段同时通过页底/页顶和列布局条件，`link_cross_page_tables` 因而建立
`table_p2_t3_p3_t1`。随后 `_merged_rows`（原第 420 行）再次使用同一模糊阈值，
执行 `continuation = continuation[1:]`，删除了第 3 页实际不同的期间表头。
资产与损益行因此共同出现在“期末／上年度末”之下。

原代码及判定数值保存在证据目录的 `before-table_service.py` 和
`before-header-match.json`，原任务和修复前接口结果也已独立归档。
原件通过 PyMuPDF 文本及线网格提取，并对第 2、3 页渲染图进行目视复核。

## 修复行为

`header_row_indices` 从实际单元格及跨度识别连续、完整的前置表头层级。
合并必须同时满足完整表头文本、列位置、rowspan/colspan、表头标记、已识别单位、
标题以及原有页边界/布局条件；只忽略排版空白。缺失单元格、覆盖不完整、重叠、
跨越表头边界、空表头或只有首行标记时，保留分表。

`_merged_rows` 在删除前独立复核同一完整签名，仅删除已经证明重复的全部表头行。
移除基于相似文字补造空列的 `_repair_continuation_shapes`。期间完全来自原件表头，
指标名称不参与生成期间。标题、单位及表格前后文字保留；附近明确单位/币种冲突或
新的未知单位声明阻止合并。允许已知单位作用于连续续页，续页省略声明后再次重复
相同单位仍可接续。

原渲染片段必须在页内容中恰好出现一次，才进行替换和删除。多页续表可继续扩展
既有逻辑表。原物理片段、行列跨度、证据和页信息保留，逻辑表增加 `table-source`
注释：来源页、原片段行号、逻辑表行号和去除的重复表头行数，均为从 1 开始的行号。
多级表头在 GFM 中保留各层的锚点和跨格空位；内部 IR 记录全部已证明的表头行，
结构不完整时保留原有首行表头元数据，但该元数据不授权删头。

## 真实接口验收结果

修复后两表分别为 `p2_t3` 和 `p3_t1`，不再形成错误的跨页逻辑表。

| 项目 | 本报告期末 | 上年度末 | 本报告期末比上年度末增减(%) |
| --- | --- | --- | --- |
| 总资产 | 21,467,154,275.58 | 21,158,183,575.04 | 1.46 |

| 项目 | 本报告期 | 上年同期 | 本报告期比上年同期增减(%) |
| --- | --- | --- | --- |
| 营业收入 | 4,607,261,132.46 | 5,093,234,252.91 | -9.54 |
| 归属于上市公司股东的净利润 | 645,981,172.66 | 676,061,297.92 | -4.45 |
| 基本每股收益（元／股） | 0.2907 | 0.3042 | -4.44 |

以上为核对摘要；最终接口原文完整保存为 `after-reparse-response.md` 和
`after-reparse-persisted-result.md`，两者逐字节一致。独立复核验证两组全部财务行、
期间、单位及数值，17 项原件/结果检查全部通过。

真实相同表头续表采用原件 `pdf_sample/1225473526.pdf`，共 27 页；验收请求上传原文件，
选择 `unit_range=6-7`，`scan_policy=auto`。
SHA256：`787297535ba74a4170cc859ae68f15f946f6dfd0bfc14a1e1fa0e6d068ba2b19`。
原件第 6、7 页均为“序号／股东名称／持股数量／持股比例／有限售条件的股份数量”。
修复前任务 `job_01M4XXHCTX0EHKXWKNA5AWJP0D`；修复后任务
`job_01M4XY0EW77HZKY0CKDE8ZZE75`，HTTP 200，2/2 页，正确合并为
`table_p6_t2_p7_t1; source-pages: 6,7`，完整表头出现一次。全部 10 名股东和合计保留：
`610,984,731 / 58.64% / 271,941,376`，单位“股”保留。
合计在原件横跨前两列，GFM 保留首格文本及次格空位；具体 colspan 的内部保留由
结构回归测试验证，GFM 本身不编码 rowspan/colspan 数值。

## 测试与接口兼容性

- 32 项新增回归测试；修复前核心 5 项均失败，修复后全部通过。
- 后端完整测试：**257 passed, 1 skipped**。跳过项是需应用镜像执行的真实 FFmpeg
  验收，与跨页表头修改无关。
- Ruff、两处服务文件的 mypy 及 `git diff --check` 通过。
- OpenAPI 修复前后内容相同。真实任务状态、Markdown 结果、SSE、资产接口均返回 200；
  同步请求的 SSE 无事件正文，状态及结果文件完整归档。
- 同时提交第二份同步解析时，现有容量为 1 的控制返回一次 429；第一份完成后顺序
  重试成功。该次原始响应保存在 `after-continuation-attempt1-*`，最终结果未覆盖失败证据。

## 部署版本与 Eventrail 证据

运行镜像：`mosaic-parse:0.4.0-local`，另有唯一标记
`mosaic-parse:0.4.0-headerfix-20261015`。
镜像 ID：`sha256:234182cbb70e5f33644f6ef71aac131a7a0fc9dbfad696d7774d74dd1b49fc3d`。
Git 基点：`61866776893975a9821f624b0ed0da5a5c0a0df7`，工作区含修复及已有未提交修改，
并非该提交的纯净构建。构建后的应用目录 SHA256：
`5d1711b96d2d6a6309e6e1509fd03eddc3e23519c2c4f4d1eb482640f03edf53`。
运行中 53 个 Python 文件与构建清单一致，构建镜像 ID 与容器镜像 ID 相同。
与修复前运行服务相比，本次应用文件仅改变 `table_service.py`、`ir_service.py`。
部署前后均无 queued/running 任务，未取消或删除任务；`/ready` 正常。
旧镜像保留为 `mosaic-parse:0.4.0-before-headerfix-20261015`。

完整证据目录为 `/opt/mosaic-parse/benchmark-results/cross-page-header-fix-20261015/`，
沿用项目忽略的本地评测目录，独立于任务结果的过期清理：

- `original-job*`、`original-result.md`、`before-*`：原任务、修复前请求及复现结果。
- `after-request.json`、`after-continuation-request.json`、`after-*-headers.txt`：请求字段及
  HTTP 响应；完整 4 页请求明确未发送 `unit_range`。
- `after-*-response.md`、`after-*-persisted-result.md`、`after-*-job.json`：最终原文及任务状态。
- `source/`：原 PDF 副本、原件文字/单元格提取、页渲染图及 SHA256。
- `independent-acceptance.json`、`api-acceptance.json`：独立原件核对及真实接口验证。
- `tests/`：修复前失败基线、32 项回归、完整测试和静态检查日志及基线重放脚本。
- `before-deployment.json`、`after-deployment.json`、`after-checkout-source.json`、
  `*-runtime-source-sha256.txt`、`build.log`、`deploy.log`：实际部署及逐文件版本证据。
- `fix.patch`、`SHA256SUMS`：本次修复补丁及完整证据校验清单。
