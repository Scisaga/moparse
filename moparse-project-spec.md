# MO-Parse 项目规格入口

产品与工程规格统一维护于 [docs/project-spec.md](docs/project-spec.md)，最终交付格式统一维护于[最终语义输出契约](docs/output-contract.md)。

最终 `result.md` 面向下游信息抽取：全部表格、PDF 流程图和组织结构图转换为语义描述，优先使用多层列表，去掉页码、页眉和页脚。中间解析可以使用 Markdown、XML 区域定义或其他结构；原表和原图留在内部证据层。该要求属于 MO-Parse 服务返回的结果，解析管线研究比较原始内容和结构，不要求候选管线直接输出最终语义格式。

当前表格语义实现尚未满足完整目标，实现差距见[最终语义输出契约](docs/output-contract.md#9-当前实现差距与迁移)，研究方法见[研究框架](docs/research-framework.md)，处理层和实现顺序见[技术路线](docs/technical-route.md)，实际发布记录见[运行配方](docs/runtime-recipes.md)。
