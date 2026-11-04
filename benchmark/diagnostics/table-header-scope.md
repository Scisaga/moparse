# 表头作用范围的软件缺陷

本页保留一个受控软件缺陷及其当前处理边界，不提供解析质量或语料验收结论。主定义见[三层评测](../evaluation-tasks.md#layout-relations)，实际支持范围见[保存输出诊断](three-layer-native-readback.md)，成绩状态见[评测索引](../reports/README.md)。旧字段评分核心及其完成结论已删除，不作为新三层的兼容实现或质量基线。

受控HTML在同一body先打印2024表头和Revenue/900，后打印2023表头和Cost/200，值格明确声明`headers="revenue y24"`。只按交叉位置或同body其他标签搜索，会错误接受Revenue/2023/900；候选已经提供的headers/id没有被使用，属于评分读取缺陷。

新语法适配保留thead、ARIA、th/scope、headers、原生id及原attrs。新三层独立反例检验Status/Ready表头与Blocked/No数据行，程序必须读取Status=Blocked；另保留字面和独立数据对象id，仅交换headers引用来验证关系层。重复id、未知引用及没有跨表达端点证明的范围不能靠字典覆盖或正确数字选解。多层表头、跨度和两个轴的完整语义对应仍未实现，当前明确阻断正式评分，不能沿用旧“已修复”范围。

[partial读取回归](../../tests/unit/test_service_partial_scope_readback.py)继续检验实际公开字符、源跨度、分隔的header scope及私有IR隔离。它们只证明限定的读取机制，不为最终Markdown提供未打印答案。新三层独立用例及真实格式链由[工具说明](../../moparse_eval/README.md)索引；旧路径评分测试的通过数量不再提供当前语义覆盖证据。
