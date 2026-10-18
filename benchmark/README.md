# moparse benchmark

`benchmark/` 是数据集、方法登记、评分工具与当前比较报告的正式入口。
当前比较只维护 [report.md](report.md)；历史 `benchmark-results/` 保留原始证据。

- [moparse-v1 数据清单](datasets/moparse-v1/dataset.json)记录来源字节、文档组和分割。
- [方法目录](methods/)记录原生／扫描路由、权重版本、并发和出口；规范化配方有 SHA256。
- [历史证据登记](evidence/)引用原结果及其 SHA，不重新声称做过推理。
- [源件标注](datasets/moparse-v1/annotations/)使用原件金标，未标注内容不算正确。
- [JSON schemas](schemas/)定义文档、数据集、标注和结果记录；CLI 同时检查字节和分割约束。

初始回归集为 10 份 PDF／502 页及 Office 转 PDF 两页。46 项难页验收、额外四项观察和
第 62 页的 99 位置／9 跨度与 209／402 集合存在来源重叠，分母分别报告。
已有原件都参与过调试，不能切几页后改称封存测试集。新增封存集按原始文档及模板家族
分组，其裁图、扫描版本和转换件跟随同组。原件放在忽略的 `sources/` 或既有 `pdf_sample/`，
提交清单、下载来源和必要的源件标注，不提交未经授权的原件、模型或 HTTP 大响应。

从仓库根目录执行；`uv run python` 或已安装项目依赖的 Python 均可：

```bash
python -m benchmark validate --require-sources
python -m benchmark compare --output benchmark/runs/comparison.json
python -m benchmark.tools.render_report
```

历史引用先验证原始文件，再导入新证据记录；默认不覆盖已有文件：

```bash
python -m benchmark import-evidence \
  benchmark/evidence/historical-20261018-concurrency-2.json \
  --output benchmark/runs/imported-concurrency-2.json
```

完整 HTTP 验证始终上传完整文件、`scan_policy=auto`、不设置 `unit_range`：

```bash
python -m benchmark run-http \
  --method production-docling-glm --cohort regression-502 \
  --base-url http://127.0.0.1:12303 --api-key-env MOPARSE_API_KEY \
  --deployment benchmark/runs/deployed-identity.json \
  --output benchmark/runs/baseline-full-http
python -m benchmark evaluate \
  --input benchmark/runs/baseline-full-http \
  --output benchmark/runs/baseline-public-scores
```

`run-http` 保持接口的 200／202 行为：大文档取得 202 后轮询原 job，下载最终 `/result`；
小文档的 200 也与持久化 `/result` 逐字节对照。保存请求、原始响应、job／events、最终
Markdown、全部公共资产及其 SHA，并采样共享 GPU。密钥通过 `--api-key-env` 或
`--api-key-file` 读取，永不写入请求证据。
方法标签仅声明期望配置；部署镜像／权重身份须在单独实际读回文件中给出。客户端无法证明
模型进程归属，因此不会把整卡利用率或整卡功率冒充该模型的独占用量。需要独占归属时，
同时保留实验容器 PID 与 vLLM 指标。完整 HTTP 与组件计时不合并，冷启动与预热另列。

API 明确保留未知结构时，文档状态可能为 `partial`。需要单独评估这类完整输出时，显式使用传输范围捕获器：

```bash
python -m benchmark.tools.capture_transport run-http \
  --dataset benchmark/datasets/moparse-addon-20261018/dataset.json \
  --method mineru-advanced-txt-vllm-c2-docling-source-glm-v6 --cohort fresh7-20261018 \
  --base-url http://127.0.0.1:12363 --api-key-env MOPARSE_API_KEY \
  --deployment benchmark/runs/deployed-identity.json \
  --completion-scope capture --output benchmark/runs/candidate-fresh7
```

它保留每份文档实际 `status=partial`，仅在首响应／持久 MD 原字节一致、全部公共资产与 events 端点收齐后，
单独记录 `capture_status=completed`。总 run 的 `completion_scope=transport_capture`、`transport_complete`、
`actual_job_status_counts` 和 `partial_document_ids` 说明采集范围；`quality_fully_resolved=false` 仍表明质量状态未完全解析。
`/events` 是 SSE，终态 200 的空事件流可被正常采集，不冒称完整历史事件时间线。原 `python -m benchmark run-http`
及新捕获器默认 `--completion-scope documents` 继续要求全部文档为 completed。
评分仍读取同一份实际 Markdown、固定金标与冻结判分；采集完成不能替代原图／字层保全和未知结构原因的独立验收，
更不能把未知内容计为正确。V6 之前的失败捕获记录保持原样，补充收据另行绑定原文件 SHA。

新增经过原件独立标注的文档：

```bash
python -m benchmark add-documents \
  --documents benchmark/runs/new-source-records.json \
  --annotations benchmark/runs/new-source.assertions.json \
  --cohort holdout-20261018 --version 1.1.0
python -m benchmark run-http \
  --method mineru-advanced-txt-vllm-c2-glm --cohort holdout-20261018 \
  --base-url http://127.0.0.1:12303 --output benchmark/runs/holdout-http
python -m benchmark evaluate --suite assertions \
  --annotations benchmark/datasets/moparse-v1/annotations/holdout-20261018.assertions.json \
  --input benchmark/runs/holdout-http --output benchmark/runs/holdout-scores
```

本轮主清单 `moparse-v1` 1.1.0 保持 543 页及原 SHA；原 39 页在首次输出暴露后，
任何修复版本的重跑都登记为 `development_after_holdout_exposure`，首次失败不会被覆盖。
另行封存的 [7 页 addendum](datasets/moparse-addon-20261018/dataset.json) 包含三个新来源家族和
28 条源件条件；其 `parent_dataset` 仅引用主清单，原件、金标与封存证明各自有 SHA。
主清单顶层 `policy.exposure` 留有最早 504 页回归集的旧描述；文件级 `split`／`exposure`
及每次请求时间用于判定实际暴露。原 39 页金标于 2026-10-17 18:05 UTC 封存，首次请求始于
19:14 UTC；其输出暴露后再修复就属于开发复测。新 7 页于 19:31 UTC 封存、v2 源码于
19:36:16 UTC 冻结，首次请求始于 19:36:46 UTC。v3 后续依据老 27 页回归修复来源注释顺序及 UI；
识别配方／新 7 页谓词不变且当时 v3 candidate 未运行新 7 页，但完整 v3 管线并非在基线新 7 页输出前冻结。
V4 后来已完成这 7 页并发现 NASA 时间轴严重无源重复；V5／V6 是全部 550 页输出暴露后的开发修复，
不能再称独立测试。原 28 条金标保持不变，事后来源网格及原图／字层保全证据分开报告。
保留既有主清单字节和 SHA，后续版本再清理旧描述。
对附录使用同一个 CLI 的 `--dataset`，不修改正在比较的主清单：

```bash
python -m benchmark validate \
  --dataset benchmark/datasets/moparse-addon-20261018/dataset.json --require-sources
python -m benchmark run-http \
  --dataset benchmark/datasets/moparse-addon-20261018/dataset.json \
  --method production-docling-glm --cohort fresh7-20261018 \
  --base-url http://127.0.0.1:12303 --api-key-env MOPARSE_API_KEY \
  --deployment benchmark/runs/deployed-identity.json \
  --output benchmark/runs/baseline-fresh7
python -m benchmark evaluate --suite assertions \
  --annotations benchmark/datasets/moparse-addon-20261018/annotations/fresh7.assertions.json \
  --input benchmark/runs/baseline-fresh7 --output benchmark/runs/baseline-fresh7-scores
```

首次独立测试、暴露后的开发复测及原回归集分开报告；跨文档家族覆盖尚有限，
未标注页与未复核的正文不能按正确处理。

源件字段见 [document.schema.json](schemas/document.schema.json)；标注见
[assertions.schema.json](schemas/assertions.schema.json)。`text`／`ordered_text` 等文字断言读取
可见 Markdown，注释不算正文；`table_grid` 对比实际公开网格，`table_span` 核对公开声明的
`[row,column,rowspan,colspan]`。选表使用原件标签而不使用答案金额；缺页、缺元数据或选表歧义
记为 `unknown`。原来的 209／402 评分保留冻结评分器及金标不变，并分别显示旧读取器和
公开结构读取器结果，结构可读取性的提升不冒充模型识字提升。

发布先满足正文、数值、完整表头／期间作用域、合并跨度和 `table-source` 门槛，再结合
完整 HTTP 延迟、吞吐、CPU/RAM、GPU/显存、共享能耗、失败率选择配置。不按行名补期间，
不按特定文档 ID 切换模型，不用整体输出含某个数字替代正确表／行／列的绑定验收。

将新鲜 HTTP 证据加入正式报告：

```bash
python -m benchmark evaluate --suite content14 \
  --input benchmark/runs/candidate504 --output benchmark/runs/candidate504-content
python -m benchmark register-http \
  --id candidate504 --method mineru-advanced-txt-vllm-c2-glm --cohort regression-504 \
  --input benchmark/runs/candidate504 \
  --evaluation benchmark/runs/candidate504-public/evaluation.json \
  --content-evaluation benchmark/runs/candidate504-content/evaluation.json \
  --deployment benchmark/runs/deployed-identity.json --power-limit 220 \
  --hardware RTX2080Ti22GiB-shared-GPU1 --warmup service-resident \
  --output benchmark/evidence/candidate504.json
python -m benchmark.tools.render_report
```

`content14` 还单列额外四项观察及第 62 页 99 位置／9 跨度；缺 Office 原件结果时对应
检查记为 `unknown`。新鲜接口证明与模型推理证明区分，缺请求级模型日志时不填“已验证新推理”。
冻结评分依赖已按原字节封装在 `scorers/frozen/`，只重定位 OLD／REPO／GOLD 路径，
无需机器上存在旧仓库路径或未跟踪的旧评分文件。

需要在正式比较中补充财务 30 项、股东人数、正常续表 33 项及 10 个表头叶项时，
从完整公共输出的既有评分提取；它们与 209／402 范围重叠，分别列示。
外部镜像／源码读回证明与客户端自身未验证身份的记录可以同时保留：

```bash
python -m benchmark.tools.enrich_evidence \
  --evidence benchmark/runs/candidate504-registration.json \
  --evaluation benchmark/runs/candidate504-public/evaluation.json \
  --deployment benchmark/runs/deployed-identity.json \
  --release-check benchmark/runs/candidate504/release-acceptance.json \
  --output benchmark/evidence/candidate504.json
```

先将 `register-http` 的 `--output` 指向临时登记路径，再将补充后的新记录放进 `evidence/`。
工具核对评分／验收证明与收到的 Markdown SHA；不覆盖输入记录、不修改评分或金标，
也不会单凭附加证明把记录自动升级为发布通过。

原字符严格不等时，可额外生成来源表面诊断，将完整网格／跨度／表头与逻辑合并、
重复表头跳过及来源行映射分别列出：

```bash
python -m benchmark.tools.diagnose_source_surface \
  --input benchmark/runs/candidate504 \
  --output benchmark/runs/candidate504-source-surface.json
```

它保留原始严格结论，仅并列映射全角 ASCII 与全角空格后的字符差异；不使用 NFKC，
不修正数字、正负号或分隔符。没有单独标注的外部单位说明保持未知。
印刷等价不能使未合并、漏跨度或来源映射错误的表格通过功能诊断。

`python -m benchmark.tools.render_report` 保留冻结评分读取器，只将报告后半部的逐项分组折叠。
基础 `python -m benchmark report` 仍可生成展开版；两者读取完全相同的证据与分数。
