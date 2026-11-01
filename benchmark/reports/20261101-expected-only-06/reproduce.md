# 本轮结果复现

当前评分软件身份为`2828b9bbcdb702196a873d008b3465c76221d5a752fe87049ac794df0fa14411`，读取修订为`canonical_expected_5`。工程冻结见`benchmark/diagnostics/expected-only-r5-validation-20261101.json`；Python和依赖版本以及逐文件代码身份保存在`summary.json`的software中。运行期间的Git HEAD是修改前提交，实际执行身份由源文件摘要及依赖共同确定，不能只看该旧HEAD。

原生输入来自`benchmark/reports/20261026-lite-v3`已完成且有效的保存运行。04版是`20261031-units-continuations-04`，05版是`20261101-business-coverage-05`，06版是`20261101-expected-only-06`，每个目录内均为P07/P08实际final.md。canonical expected只读。完整复算需要本地保留的Lite声明、canonical expected、八组原生产物和三个正文版本；这些大型或私有材料没有整体加入Git。

以下命令重新计算全部14组。输出目录必须尚不存在；示例名称须在再次执行时换为新的名称。该过程不执行模型和后处理，也不打开原PDF，不复用旧分数或人工排除。

```bash
.venv/bin/python -m moparse_eval.expected_evaluation \
  --baseline benchmark/reports/20261026-lite-v3 \
  --previous-root benchmark/reports/20261031-units-continuations-04 \
  --intermediate-root benchmark/reports/20261101-business-coverage-05 \
  --current-root benchmark/reports/20261101-expected-only-06 \
  --freeze benchmark/diagnostics/expected-only-r5-validation-20261101.json \
  --output benchmark/reports/20261026-lite-v3/artifacts/scores/new-expected-only-reproduction \
  --report-output benchmark/reports/new-expected-only-reproduction \
  --workers 8
```

只重生报告时，下面的命令只读已完成评分产物，不读取expected、数据包或候选，也不重新判分。目标、分母、软件身份或完整性不一致会被拒绝。

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from moparse_eval.expected_report import render_expected_report
index = Path('benchmark/reports/20261026-lite-v3/artifacts/scores/expected-only-06-final-r3/index.json')
print(render_expected_report(index, output=Path('/tmp/moparse-expected-report-reproduction')))
PY
```

`scoring-reproducibility.json`记录3个真实样本、14组共42份输出的独立重评分，完整评分JSON一致；该复算先从canonical expected和候选重新计算，再与保存结果比较，旧结果没有作为答案输入。上述完整复算命令覆盖这些样本及其余全部样本，分析重复不增加质量样本数。

`report-reproducibility.json`记录13个指定产物的逐字节比较，包括报告、汇总、覆盖、成本、采用、阶段统计、三种图件、配对变化和逐项CSV。字体准备文件和人工说明不属于这13项。图件检查记录见`figure-verification.json`；只查看生成图件，不查看原PDF。

`execution-costs.json`包含完整历史资源采样，约200 MB，保留本地并从Git排除。`execution-cost-summary.json`保留各轮计时、初始化、预热、运行环境、分配与实际工作进程限制以及记录过的RSS峰值，去掉重复的逐案例资源调试负载。两者不产生新的测量，也不把重叠阶段相加。`conversion-errors.json`只筛选共同评分中“原生相同目标正确、当前最终正文错误”的条目，保留原分数、原因和证据路径，不改判。

P07/P08执行软件身份为`8b292af10747c75ab187fcbb46d2839434faf71d24b85b4cac1a686cc3c8d74d`，评分软件身份与之分开记录。候选运行后只修正了评分读取，实际后处理代码与已保存正文没有变化，所以保留已有800页回放和80页三轮计时。再次改动后处理时按`moparse_eval/README.md`的prepare、warmup、freeze、measured流程新建隔离运行，不覆盖本轮，不挂载expected，不调用模型。

本轮Lite已用于开发。完整对照及复现不等于全部输出正确；剩余错误没有排除，见正式报告和逐项结果。图片语义不在范围内，image_alt_text仅为文字诊断。
