# MO-Parse 统一评测工具

本轮复用有效保存输出及原始测量，不重新执行模型。方法、指标、分母、失败政策和完成条件只维护于[评测任务](../benchmark/evaluation-tasks.md#current-task-expected-only)。当前状态及唯一正式报告由[评测索引](../benchmark/reports/README.md)维护。

## 读取与判分

`expected_readback`只读canonical expected及现有manifest/source-map选段，展开完整正文与明确记录要求，不读取旧标注答案。`target_coverage`追溯完整文字范围至业务要求或正文目标，保留字段提取后的剩余文字；这种程序记账不认证参考真实性，也不单独证明语义覆盖。

`saved_native`从保存的native.json调用各组真实格式读取器，再由`native_readback`暴露显式关系；P05只使用json_result主视图。候选读取器不接收expected。最终Markdown由`markdown_observation`直接读取，不使用内部IR、未打印跨度或隐藏关系。`expected_scoring`对所有组共同判分，`prose_metrics`报告正文定位、字符覆盖、字符保全及已对齐严格CER，整段全对只作诊断。业务主结果分列值与标签正确/全部目标及完整信息正确/全部目标。

软件读取失败须先修复，不能批量计成解析错误。缺失候选或真实失败仍接受全部目标且判错。代码身份、依赖和已通过的独立验证冻结后，全部受影响原生与正文使用同版程序重新评分。程序不提供语料检查、参考修复或人工成绩入口。

## 保存输出的统一重评

八组原生及测量位于`benchmark/runs/lite/`，唯一修改前正文为`service/baseline/`，新正文为`service/current/`。earlier/before/after、旧成绩、错误冻结和旧报告框架已删除，不保留兼容入口。

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/runs/lite \
  --service-baseline-root benchmark/runs/lite/service/baseline \
  --current-root benchmark/runs/lite/service/current \
  --freeze benchmark/runs/lite/scoring-freeze.json \
  --output benchmark/runs/lite/scores/current --workers 8
```

输出目录必须不存在。`--current-root`尚未生成时可省略，只重评八组原生及唯一基线。重评不会调用模型或候选后处理，也不回填处理时长。评分JSON、文字范围追溯、候选证据和配对变化保持本地。禁止用旧评分填充新索引。

冻结必须记录当前`cli.code_identity()`、`expected_scoring.PROTOCOL`及独立反例与真实格式读取验证通过的工程证据；入口核对软件身份、依赖与协议，并在完成时再次确认未变。不能用测试数量、文件存在或复现一致代替判分有效性。

## 唯一报告

```bash
.venv/bin/python scripts/render_lite_report.py \
  --index benchmark/runs/lite/scores/current/index.json \
  --output benchmark/reports/lite
```

只有`benchmark/reports/lite/report.md`是正式报告。附录、分项、逐项错误、范围、文档/家族/类别和配对证据在相邻目录；报告入口从实际逐项结果复算汇总及采用门槛，拒绝版本混用、目标不齐、未完成或已知读取缺陷。旧并行报告生成器和分组独立评分入口已删除。

报告只读取同版已完成评分及有效原测量，不重新读取expected或判分。原生历史时间与CPU回放单列；800页和80页三次重复分列，初始化、预热、采样覆盖及缺失另列。不相加独立峰值，不将TTS或整卡显存归给管线。图表使用无衬线字体，SVG字体栈和PDF嵌入以程序验证，不开展原页或候选图片视觉验收。

## 隔离CPU后处理

发现真实转换损失后，修复原生已有信息能够支持的问题，再运行实际服务链。候选容器只挂载输入、对应管线原生产物、软件和输出目录，不挂载参考、历史评分或expected；网络关闭，无GPU设备。P08不读取PDF文字或矢量表格，P07沿用已声明来源处理，不新增补充方法。只改评分器时不重跑候选。

```bash
.venv/bin/python -m moparse_eval.service_evaluation prepare \
  --baseline benchmark/runs/lite \
  --output benchmark/runs/lite/service/current/p07 \
  --pipeline P07 \
  --service-config benchmark/runs/lite/service/baseline/service-config.json
.venv/bin/python -m moparse_eval.service_evaluation run --run benchmark/runs/lite/service/current/p07 --phase warmup
.venv/bin/python -m moparse_eval.service_evaluation freeze --run benchmark/runs/lite/service/current/p07 --validation benchmark/runs/lite/service-validation.json
.venv/bin/python -m moparse_eval.service_evaluation run --run benchmark/runs/lite/service/current/p07 --phase measured
```

P08使用对应管线和目录。预热与800页质量回放、固定80页三轮分别记录。`freeze`验证实际后处理代码与依赖，不重新运行原生预检。实际后处理完成后，由前述统一评分入口对全部受影响组重新评分；正文收益、baseline正确项损失及原生到正文损失分别报告。不部署，不操作GPU、TTS或在线服务。

## 软件验证边界

独立合成反例先固定，再修实现。`tests/unit/test_expected_contract.py`从SDK、HTML、GFM及列表完整读取链约束正文标点、负号、单格多事实、单位、年度、否定、附注、冲突、身份公平和实际正文边界；其余合成格式及定位测试补充多层表头和续接。真实保存结果的专项程序读取验证单独执行，不是语料复核。

通用测试及Markdown检查只读取代码和非语料文档，永久排除`pdf_sample/`、`pdf_sample_extra/`、`pdf_page_images/`、`datasets/`、`benchmark/reference-decisions/`、`benchmark/runs/`和`benchmark/reports/`，显式路径亦不可绕过。原件、参考、标注、映射、资产和数据包保持原样。运行资料与软件快照留本地，本任务仅提交代码、正式文档和报告。
