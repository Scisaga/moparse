# MO-Parse 保存输出评测工具

当前仅以canonical expected和现有选段声明为答案。执行约束见[AGENTS](../AGENTS.md)，计分合同见[评测任务](../benchmark/evaluation-tasks.md#three-layer-evaluation)，最新状态见[评测索引](../benchmark/reports/README.md)。新三层核心已实现部分解释和判定，完整质量成绩仍暂停；局部分母、诊断完成和测试通过不能代替正式重评。

## 代码边界

`expected_readback.py`只读取Markdown语法及声明选段，保存原始文字、格子、行号与外部上下文，不生成旧业务record，不把未选单位或期间灌入要求。部分语法选段和外部依赖保留来源，不改写语料。

`saved_native.py`和`adapters.py`分别读取Docling、Paddle、GLM、DocVortex和视觉ContentBlock结构；`native_readback.py`忠实暴露原生明确关系。接口不接收expected。thead、ARIA、th/scope和headers按实际声明保存，全td网格不靠邻格推断角色。

`three_layer.py`分别编译文字、关系和业务要求，候选证据另读，随后独立判定T/L/B。`expected_scoring.py`是同一实现的当前入口，没有旧算法回退。`layer_aggregation.py`分别汇总各层、处理N/A和配对；软件未支持不变成候选0分。

`expected_evaluation.py`统一编排八组原生及P07/P08实际baseline/current正文，默认16个CPU进程。`expected_report.py`从逐项证据复核分母、S/D/I、检索来源及配对；报告器仅接受同版、完整、无软件阻塞的结果。旧字段评分、普通文字评分、硬行列定位和旧报告入口已删除。`information_reading.py`只保留候选单位字面读取，供既有service readback使用。

## 独立软件验证

```bash
.venv/bin/python -m pytest tests/unit/test_three_layer_*.py tests/unit/test_expected_syntax_selection.py tests/unit/test_moparse_eval_scoring_freeze.py tests/unit/test_moparse_eval_report_resources.py
```

测试硬断言业务集合、角色、权重、限定和来源，覆盖多种序列化、Status误读、独立对象引用换绑、重复冲突、合法分块、标签公平、编译遗漏突变、输入边界、五种实际SDK、16进程与串行一致及发布门禁。测试使用受控数据，不读取语料或运行目录。保存输出的文字诊断仍是单独的必要验证。

## 保存输出软件诊断

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/runs/lite \
  --service-baseline-root benchmark/runs/lite/service/baseline \
  --current-root benchmark/runs/lite/service/current \
  --output benchmark/runs/lite/diagnosis/three-layer-current \
  --diagnostic --workers 16
```

输出目录须不存在。诊断遍历全部声明组，保存实际来源、全部命中、身份检查、排除理由及软件阻塞，不生成正式冻结或成绩。`index.json`为`blocked`时进程返回2，表示存在必须修复的软件范围，并非候选失败率。部分要求数量不构成完整语义覆盖。主分和分子被清空，原始处理时间及资源单列，不重跑解析或CPU后处理，不更新原run.json。

## 正式重评及报告

只有独立反例、突变、实际格式及保存输出诊断均可靠且无已知缺陷时，才可生成正式冻结。冻结须匹配当前`cli.code_identity()`和`three_layer.PROTOCOL`。validation的`independent_counterexamples`、`mutations`、`native_formats`及`saved_output_diagnosis`四项分别包含`status: passed`和实际证据路径；这些字段本身不证明判分正确。

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/runs/lite \
  --service-baseline-root benchmark/runs/lite/service/baseline \
  --current-root benchmark/runs/lite/service/current \
  --freeze benchmark/runs/lite/scoring-freeze.json \
  --output benchmark/runs/lite/scores/current --workers 16
.venv/bin/python scripts/render_lite_report.py \
  --index benchmark/runs/lite/scores/current/index.json \
  --output benchmark/reports/lite
```

当前阻塞未解时不得执行正式重评或制造passed冻结。正式入口遇到软件阻塞会停止全部成绩汇总；报告器在覆盖报告前拒绝不完整结果。八组原生与P07/P08三种配对分别报告，不推导旧“零转换损失”或采用结论，不混排正文与原生成绩。

## 保全与范围

不打开PDF或图片，不运行渲染、OCR、视觉、裁判推理、Full或额外PDF；expected、原件、标注、映射、资产、数据包、候选正文和原始测量只读。既有执行及CPU后处理组件保留，本任务不调用它们，不操作GPU、TTS、服务或部署。

通用检查永久排除语料、datasets、benchmark/reference-decisions、benchmark/runs和benchmark/reports，包括显式路径。专项诊断不认证语料。仅提交本任务代码、正式文档与报告，运行资料、大候选和软件快照留本地。
