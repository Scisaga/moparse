# 服务最终输出的读取回归

本页只记录软件缺陷与受控回归，不保存真实材料的错误质量分数或旧报告。最终质量结果由[评测索引](../reports/README.md)链接到当前P07服务报告，标准见[服务配对协议](../evaluation-tasks.md#7-p07与mo-parse最终输出的配对评测)。

| 缺陷 | 修复 | 受控证据 |
| --- | --- | --- |
| Python的通用分行把真实分页符当成Markdown换行，造成后页偏移或重复代码 | 按CommonMark的CRLF、CR、LF保存原字符范围，普通块忠实读取最终显式页声明 | [导出回归](../../tests/unit/test_export_fidelity_repairs.py)、[多页交接回归](../../tests/unit/test_postprocessing_preservation.py)、[最终观察回归](../../tests/unit/test_moparse_eval_service_observation.py) |
| 单格内容再次作为块级Markdown解析，短横线等被读为空 | 对格、标签、值和限定语采用实际行内投影，保留代码和实体语义 | [最终观察回归](../../tests/unit/test_moparse_eval_service_observation.py) |
| 网格与明确语义路径对同一标签采用不同的定位口径 | 两者复用既有标签定位函数，完整路径层数、顺序及独立表范围继续生效，值不被修正 | [路径与网格政策回归](../../tests/unit/test_service_path_policy.py)、[既有范围约束回归](../../tests/unit/test_moparse_eval_table_scoring_repairs.py) |
| 最终观察读取修复后缺少无损重建入口 | 从保存的最终Markdown、最终IR及明确私有证据恢复当前对象，矛盾或未知结构报工程错，不读取PDF、参考或隐藏的转换前正文 | [候选产物重构回归](../../tests/unit/test_moparse_eval_service_artifacts.py) |
| 报告将普通未判定单元混入表格字段转移，且全NA图崩溃 | 仅按真正字段索引统计转移；缺测图显示NA；生成器身份与执行、评分分开 | [报告回归](../../tests/unit/test_moparse_eval_service_report.py) |
| 同一表的有值父行被其子项复制的父标签误计为多份自身数据 | 先按实际标签及明确表身份辨别自身行和子项上下文，不按列值或参考答案选取；真正重复自身行仍判错 | [有值父行、缺期与冲突反例](../../tests/unit/test_moparse_eval_information.py) |
| 实际列表前有完整单位caption，但未重复后缀的原“不适用”格没有取得共享单位 | 读取公开Markdown中紧邻列表的完整caption，仅限同一列表边界；普通文字、标题及其他块阻断，明确错误局部单位不被救正 | [共享列表单位与隔离反例](../../tests/unit/test_moparse_eval_service_observation.py) |
| 共享行标题在多条记录中完整打印，或正式项目名称同时出现在本行覆盖说明里，导致文字和读序端点被误计歧义 | 仅合并同表、同来源格、完整公开字面的跨记录标题；正式行标签只排除明确覆盖该行列的段内提及，其他独立重复仍保留 | [共享标题、独立重复及范围提及反例](../../tests/unit/test_moparse_eval_scoring.py) |
| 已实际打印年度范围及同表两个年末端点，“本年末比上年末”仍缺少比较期间 | 只读取唯一明确年度与当前表头带或同条公开记录共同支持的年末比较；缺端点、错年、跨表行、月末及反向期间不通过 | [年末比较的两种格式及隔离反例](../../tests/unit/test_moparse_eval_information.py) |

这些修复保持参考、匹配门槛、字符政策、完整路径约束及严格业务值比较不变。原生P07及最终输出两侧采用同一修复版标准评分，处理结果和已测耗时不被评分阶段改写。涉及八组共同网格读取的内部表头修复由[作用范围诊断](table-header-scope.md)维护，受影响成绩统一替换，不引用旧版本数值作为质量基线。

评分输入、派生读取、代码快照与身份分别保留，已错误计分的中间产物删除；未知范围不被记成正确，自动评分不构成语料重新审核。文档、通用检查和受控测试不读取真实语料或参考。
