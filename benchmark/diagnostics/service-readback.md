# 服务最终输出的读取回归

本页仅记录候选文字与来源读取的软件回归，不发布质量结论。正式状态见[评测索引](../reports/README.md)，三层解释及当前阻塞见[保存输出诊断](three-layer-native-readback.md)。当前正式输入只读实际final.md，内部IR及私有跨度不能为未打印内容补分。

| 保留的读取机制 | 受控证据与界限 |
| --- | --- |
| CommonMark换行与真实分页保全 | [导出回归](../../tests/unit/test_export_fidelity_repairs.py)、[多页交接](../../tests/unit/test_postprocessing_preservation.py)保留实际字符、出现次数和来源页，不以原评分器的定位通过认定文字正确 |
| 单元格行内字面保全 | [最终观察回归](../../tests/unit/test_moparse_eval_service_observation.py)保存短横线、代码、HTML实体、原文字面、span及页声明，不凭格子数量生成业务判断 |
| 保存对象与实际正文隔离 | [局部范围回归](../../tests/unit/test_service_partial_scope_readback.py)及[过程阶段回归](../../tests/unit/test_service_stages.py)保留私有证据和公开正文边界，不恢复已经移除的答案 |
| 已有共享单位声明的读取 | 最终观察回归保存紧邻列表的实际caption及其局部证据；这不是新三层中单位适用性、计数和完整业务关系已经验证的结论 |

旧评分核心删除后，依赖旧字段路径、旧普通文字匹配和旧业务列通过的断言已经移除或迁移。原生内容、实际正文、分页来源、原计时和私有IR隔离断言保留；软件尚不能解释的记录明确阻断发布，不改写为评分通过。新三层反例分别检验身份、单位、显式关系和独立文字保全，不能用这里的读取回归代替正式共同评分。
