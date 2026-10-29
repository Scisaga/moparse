# 服务最终输出的读取回归

本页只记录软件缺陷与受控回归，不保存真实材料的错误质量分数或旧报告。最终质量结果由[评测索引](../reports/README.md)链接到当前P07服务报告，标准见[服务配对协议](../evaluation-tasks.md#7-p07与mo-parse最终输出的配对评测)。

| 缺陷 | 修复 | 受控证据 |
| --- | --- | --- |
| Python的通用分行把真实分页符当成Markdown换行，造成后页偏移或重复代码 | 按CommonMark的CRLF、CR、LF保存原字符范围，普通块忠实读取最终显式页声明 | [导出回归](../../tests/unit/test_export_fidelity_repairs.py)、[多页交接回归](../../tests/unit/test_postprocessing_preservation.py)、[最终观察回归](../../tests/unit/test_moparse_eval_service_observation.py) |
| 单格内容再次作为块级Markdown解析，短横线等被读为空 | 对格、标签、值和限定语采用实际行内投影，保留代码和实体语义 | [最终观察回归](../../tests/unit/test_moparse_eval_service_observation.py) |
| 网格与明确语义路径对同一标签采用不同的定位口径 | 两者复用既有标签定位函数，完整路径层数、顺序及独立表范围继续生效，值不被修正 | [路径与网格政策回归](../../tests/unit/test_service_path_policy.py)、[既有范围约束回归](../../tests/unit/test_moparse_eval_table_scoring_repairs.py) |
| 最终观察读取修复后缺少无损重建入口 | 从保存的最终Markdown、最终IR及明确私有证据恢复当前对象，矛盾或未知结构报工程错，不读取PDF、参考或隐藏的转换前正文 | [候选产物重构回归](../../tests/unit/test_moparse_eval_service_artifacts.py) |
| 报告将普通未判定单元混入表格字段转移，且全NA图崩溃 | 仅按真正字段索引统计转移；缺测图显示NA；生成器身份与执行、评分分开 | [报告回归](../../tests/unit/test_moparse_eval_service_report.py) |

这些修复保持参考、匹配门槛、字符政策、完整路径约束及严格业务值比较不变。原生P07及最终输出两侧采用同一修复版标准评分，处理结果和已测耗时不被评分阶段改写。涉及八组共同网格读取的内部表头修复由[作用范围诊断](table-header-scope.md)维护，受影响成绩统一替换，不引用旧版本数值作为质量基线。

评分输入、派生读取、代码快照与身份分别保留，已错误计分的中间产物删除；未知范围不被记成正确，自动评分不构成语料重新审核。文档、通用检查和受控测试不读取真实语料或参考。
