# MosaicParse 项目规格

唯一维护中的项目规格见 [docs/project-spec.md](docs/project-spec.md)。

当前架构结论：本项目只发布 GFM Markdown 文档结果；坐标与候选证据仅用于请求内解析，
不作为结果持久化或返回。实体、关系、财务指标和事件抽取由 EventRail 等下游系统负责。

PDF 管线：原生页使用 Docling 2.139／TableFormer V1／matching=False／PyPdfium；扫描、
混合页使用 GLM-OCR＋官方 SDK，并开启方向预处理。配置与对比结论见 [README](README.md)。
