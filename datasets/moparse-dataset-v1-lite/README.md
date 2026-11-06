# moparse-dataset-v1-lite

本包为2026-10-24冻结的800个实际PDF输入页，允许单页、连续页段和完整短文档。visual-a、visual-b、visual-c分别实际阅读原件并对照当前expected后交接400、200、200页；数量来自作者手工页段账，不是包装程序的计数验收。原始expected正文未改写。

manifest.json保存输入、原文档、家族、源物理页与本地页、分类、开发暴露、子集和冻结记录。inputs包含实际页对象PDF，references包含相关原文档的完整参考和必要资产，evaluation只保存明确评分范围与评价说明。运行所需数据路径位于本包内，不依赖原语料目录。原参考manifest中的旧工作区路径只是历史导航，不用于运行。

固定lite子集为800页；perf80由其中完整样本组成，A60页加B20页；preflight8保持万科1–2、浦发1–2、平安1–4三个原样本的8个物理页。正式运行先共同预热8页，再quality800一次，最后perf80三轮。重用物理页不增加独立文档数，也不将性能三轮称为800页三轮。

确认范围由各评价单元状态和作者交接决定。早期密集表格的字段尚未穷尽，部分参考含人为整理前缀或公式排版，文字比较明确NA。页面家具和合法输出未建立闭合穷尽范围，内容precision/F1不能被假定可评。底层native、scan、mixed类别没有独立确证，保持source-unknown；运行时分支预测不能改写这些标签。

图片是已目视确认的保全目标；图题和图外原文可另评文字，图片语义不在任务范围。不同候选资产名不表示丢图，缺少输出视觉身份对应时，图像保全成绩保持未测。已确认目标及自动对应、视觉评价的覆盖分别报告。

所有选定原文档和相关家族都已向作者暴露，本包与Full共享来源，不能称为独立未见测试集。未选导航页及额外暴露以作者交接为准。独立页段上下文与完整长文档不同，Lite结果不能推广为Full表现。

评测协议的权威文件是MO-Parse仓库benchmark/evaluation-tasks.md；[冻结协议副本](provenance/evaluation-tasks.md)仅用于溯源。实际视觉和保存后回读范围见[A交接](provenance/visual-a-handoff.md)、[B完成记录](provenance/visual-b-completion.json)、[C交接](provenance/visual-c-handoff.md)。包装没有机械复核或接受语料。

在准备好评测软件与锁定环境的机器上运行：

```bash
python -m moparse_eval run --dataset <本包目录> --suite lite --pipeline all --config <MO-Parse目录>/benchmark/execution-lock.json --output <新的运行目录> --maintenance-window
python -m moparse_eval score --run <新的运行目录>
python -m moparse_eval report --run <新的运行目录>
```

run不向候选挂载参考；score只读冻结参考，写到运行目录。输出、配置、计时、资源、失败和评分版本须一起保留。原资料来源与许可沿用现有声明；本地打包不授予新的公开再分发许可。
