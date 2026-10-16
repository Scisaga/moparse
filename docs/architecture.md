# Architecture

MosaicParse 是 PDF/Office/图片/视频到 GFM Markdown 的解析层。详细坐标证据是
请求内的解析中间表示，不是交给业务 LLM 的输出；EventRail 等下游直接消费可读正文、
列表和表格，再完成实体、关系、事件与财务指标抽取。

这一输出边界见
[ADR-0001：以忠实的逻辑表 GFM 作为文档内容与下游抽取边界](adr/0001-faithful-gfm-for-downstream-extraction.md)。

```text
Browser / HTTP / MCP
          |
          v
格式校验 + Job + 页范围 + 超时
          |
          +-- 数字 PDF ------> PyPdfium 原生文本 + Docling 2.139 / TableFormer V1
          |
          +-- 扫描/混合 PDF -> 方向预处理 + GLM SDK / PP-DocLayoutV3
          |                         |
          |                         v
          |                   GLM-OCR + 结构验证
          |
          +-- Office ---------> 原生结构 + 嵌入图片关系
          +-- 图片/视频 ------> 资产/关键帧 + GLM 可见文字识别
                                      |
                                      v
                      内部 Evidence IR + TableGridIR
                                      |
                                      v
                  跨页表合并 + GFM Markdown 导出
                    + 独立鉴权资产清单/下载
```

## PDF 路由

原生页固定使用 Docling 2.139.0、TableFormer V1 Accurate、`do_cell_matching=False` 与
PyPdfium 后端，原生文字与表格结构由 CPU 恢复，不做无条件全页 OCR。

`scan_policy=auto` 下，扫描、混合页由官方 GLM-OCR SDK 处理。
`GLM_SDK_ORIENTATION_ENABLED=1` 先旋正页面，再执行 PP-DocLayoutV3 布局与 GLM-OCR
区域识别。结构验证保留完整行格及候选，不依据指标名补期间，不用另一模型重写冲突数值。

`scan_policy=skip` 在 PDF 进入 Docling 时关闭扫描 OCR，扫描/混合页只保留可信原生文字、
明确的 Markdown 跳过提示和整页图像资产。

图片识字和视频关键帧识字复用 GLM-OCR；`describe_images` 保留参数兼容性，生成内容
限定为可见文字。视频摘要按采样时间列出识别文字，不推断未采样片段或无文字场景。

## 内部证据与公共输出

内部 `ContentParseResult`/Evidence IR 保存页、区域、候选来源、bbox、表格单元格和质量，
仅用于同一次解析中的融合、质量判断、跨页关系和资产裁剪。它不进入 OpenAPI，不作为
结果文件持久化，也不发给下游 LLM。

公共 GFM Markdown 包含：

- 标准 Markdown 正文、标题和列表；
- 解析器识别出的 GFM 表格，包括多级/分段表头；
- 合并后的跨页逻辑表，续页重复表头仅在完整表头及列义一致时去重；
- 无坐标结构注释，携带原模型表头角色、合并跨度和来源页；未确认的结构明确标记未知；
- 图片/视频资产的普通 Markdown 列表、描述和下载链接。

解析层不判断某张表应变成财务事实、公司字段或股东关系，也不依据固定首行生成字段名。
公司实体消歧、关系/事件 ontology、财务指标归一化、事件去重和修订由 EventRail 或其他
下游负责。需要审计时使用任务 ID 回到原 PDF 和资产，而不是把全页坐标送入抽取提示词。

## 持久化

```text
/data
├── jobs.db
└── jobs/<job_id>
    ├── input/original.<ext>
    ├── output/result.md
    ├── output/asset-index.json   # 仅资产下载元数据，不含坐标、正文或表格 IR
    ├── output/assets.zip         # 按需生成
    ├── assets/original/*
    ├── assets/derived/keyframes/*
    ├── assets/derived/previews/*
    └── logs/warnings.json        # 无正文诊断
```

`result.md` 是唯一文档结果。SQLite 是 Job 状态真值，SSE 只是增量体验层。资产索引、
告警和 ZIP manifest 是运维/下载控制数据，不是替代的解析 JSON。

## 安全与边界

上传与 URL 均不可信：校验 magic、OOXML 关系、ZIP 展开边界、FFprobe、大小、单元数、
协议、解析 IP 与每次重定向。模型 URL、模型名和 prompt 只能由服务端配置。
图像字节、内部候选正文和模型请求不进入诊断日志；公开正文只包含采用的解析结果。

本项目不负责 Embedding、索引、问答、公司/人物消歧、领域关系与事件编排；它负责把
下游真正需要的可见内容和结构恢复为可高效消费的一份 Markdown 文档。
