# 复现本轮结果

本轮评分读取修订为`canonical_expected_8`，软件身份与依赖见`summary.json`及`benchmark/diagnostics/expected-preservation-validation-20261102.json`。实际源文件和依赖共同标识软件，Git HEAD仅记录当时的提交位置。执行快照和评分快照分别保留。

复算需要本地已有的canonical expected、Lite声明、八组有效原生产物和P07/P08保存的实际Markdown。expected只读；完整数据包、大型候选和资源采样继续保存在本地。04版为较早的最终正文，06版为此次修复前的最终正文，08版为此次修复后的CPU回放正文。错误中间版本、旧评分及其产物已直接删除，不归档。04/06/08只保留有效候选与实际执行记录，所有成绩由当前程序重新计算。

以下命令对相同173个样本、14组输出重新评分，再生成报告。输出目录必须尚不存在。该命令只读保存输出，不执行模型或后处理，不打开原PDF。

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/reports/20261026-lite-v3 \
  --previous-root benchmark/reports/20261031-units-continuations-04 \
  --intermediate-root benchmark/reports/20261101-expected-only-06 \
  --current-root benchmark/reports/20261101-preservation-repair-08 \
  --freeze benchmark/diagnostics/expected-preservation-validation-20261102.json \
  --output benchmark/reports/20261026-lite-v3/artifacts/scores/new-preservation-reproduction \
  --report-output benchmark/reports/new-preservation-reproduction \
  --workers 8
```

只重生报告可执行下列命令。报告生成器从逐项结果核对目标、软件身份、完整性与采用门槛；过程不读取expected或候选。

```bash
.venv/bin/python - <<'PYREPORT'
from pathlib import Path
from moparse_eval.expected_report import render_expected_report
index = Path('benchmark/reports/20261026-lite-v3/artifacts/scores/preservation-clean-20261102/index.json')
print(render_expected_report(index, output=Path('/tmp/moparse-preservation-report-reproduction')))
PYREPORT
```

`scoring-reproducibility.json`记录4个真实样本在14组输出上的独立重评分；`report-reproducibility.json`记录27个指定生成产物的逐字节复现。它们验证重现性，实际质量范围由完整173样本评分及`coverage.json`定义。

`private/native-preservation.json`记录原生到08正文的业务信息保留；`private/incremental-changes.json`记录06到08的实际变化；`private/paired-changes.json`记录04到08的完整变化。完整逐项错误、候选证据及最早观察到错误的输出阶段保存在`private/target-details.csv`和逐样本评分JSON中，正式汇总由同一程序生成。

`execution-costs.json`保留完整原生历史资源采样，体积较大而不加入Git。`execution-cost-summary.json`去掉重复的原生逐案例资源调试负载，保留各轮直接计时、预热、初始化及执行环境；原始资源记录仍可从本地评分索引追溯。历史原生处理与新CPU后处理分别列出。

P07/P08各按既有隔离口径执行800页及固定80页三轮，预热单列。候选容器不挂载expected，网络关闭，无GPU，不调用模型。重新改变后处理代码时，按`moparse_eval/README.md`新建prepare、warmup、freeze和measured运行；仅修共同评分时，冻结后对所有受影响组重新评分，保留原处理计时。

摘要、报告展示身份、错误索引及资源章节由下列第二步生成。它读取当前已完成评分和原执行的资源记录，不读取expected或候选答案，也不重新判分。执行两步才会得到包含资源成本章节的完整report.md。

```bash
.venv/bin/python scripts/render_preservation_summary.py \
  --index benchmark/reports/20261026-lite-v3/artifacts/scores/preservation-clean-20261102/index.json \
  --output /tmp/moparse-preservation-report-reproduction
```

27项复现在两步报告生成全部完成后比较：共同报告14个产物、摘要及配套8个产物，以及resource-costs.json、resource-costs.md与resource-tradeoffs的PNG、SVG、PDF共5个资源产物。原执行的artifacts/P01-P08下worker-resources.json和inference/resources.json，以及当前CPU回放run.json均需保留；资源证据文件路径与身份见resource-costs.json。压缩错误索引每行的`source`指向同文件的来源表；完整expected内容、实际片段及判定仍在该来源的逐样本评分JSON中，以`target`定位。报告展示程序的身份单独记录，不改变冻结的判分软件身份。
