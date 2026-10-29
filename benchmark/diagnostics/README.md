# 执行层诊断与修复依据

这里保留软件故障机制和受控验证依据，不保存真实页面的质量、吞吐、排名或旧运行报告。执行修复和当前[工程预检02](../reports/20261026-repaired-preflight-02/)之后，本轮八组正式执行、统一评分、首版报告和原MO服务恢复已完成，结果只见[本轮v3报告](../reports/20261026-lite-v3/report.md)。先前中断测量仍撤回，事件见[运行条件中断诊断](./tts-window-interruption.md)；TTS身份和活动仅观测、负载不控制，状态与限制由[评测索引](../reports/README.md)维护。诊断和预检不能替代正式测量或来源内容验收。原件、数据包与冻结参考保持原样。

| 问题 | 影响路径与确认范围 | 已实现修复与验证边界 |
|---|---|---|
| GLM MRoPE配对错误 | P01/P02/P05/P06/P07的GLM分支；vLLM 0.19.1的CUDA快路径不处理GLM要求的GPT-J相邻配对 | 对GLM显式选择native rotary，保持其他条件及支持的CUDA Graphs；当前工程预检02已完成，新执行身份已冻结 |
| Paddle BGR/RGB接线 | P03/P04的PaddleX 3.7.2 native Transformers识别分支；固定软件CPU像素探针复现上游红蓝互换 | 在识别区域边界将BGR转换为PIL RGB，布局模型继续接收BGR；当前兼容层已用合成text/table/formula输入覆盖 |
| 旋转来源路由 | 混合配置曾把旋转后的page.rect与未旋转图像框相交 | 已统一坐标空间，并用合成PDF覆盖旋转与cropbox组合；原PDF固有旋转和新增旋正角分别保存 |
| 成功邻居保存 | 后续native_error及局部导出异常可能遮蔽已有有效结果 | 已先保存原生结果并隔离页或区域导出失败；合成SDK覆盖成功邻居保留，不补造答案 |
| Paddle线程内存 | 临时推理线程会触发Torch/cuDNN线程计划缓存留存 | 长期owner线程统一初始化、推理与关闭，显式use_queues=False；新预检保存资源和生命周期证据，不引用旧运行峰值 |
| 生成与Graph观测 | Paddle输出上限4096；实际停止规则及Graph支持范围不能从一次捕获推定 | 已记录逐区域有效参数、token长度与EOS观测，实际停止原因未暴露则unknown；新预检保留组件捕获及失败例外，不能把两token试验当作完整生成回放 |

GLM机制与[官方问题49290](https://github.com/vllm-project/vllm/issues/49290)、[修复PR49906](https://github.com/vllm-project/vllm/pull/49906)一致。MinerU模型Qwen2VL使用NeoX配对，Paddle执行Torch/SDPA，不能仅因安装相同vLLM包就判定它们命中GLM同一个内核错误。Paddle线程缓存机制可对照[Torch固定源码](https://github.com/pytorch/pytorch/blob/449b1768410104d3ed79d3bcfe4ba1d65c7f22c0/aten/src/ATen/native/cudnn/Conv_v8.cpp#L349-L371)。

## 保留的受控证据

- [MO-Parse服务后处理保全修复](service-postprocessing.md)：原生读取、正文导出、结构化交接及表格限定语的合成回归；与研究侧执行修复、生产部署和真实材料验收分别记录。
- [服务最终输出读取回归](service-readback.md)：真实分页、行内单元格、路径与网格标签定位一致性、冻结候选重构及报告字段账本；不保留错误中间质量分数。
- [原生正文与表格转换入口诊断](service-entrypoints.md)：原生文字进入IR与最终正文的数据路径、表格结构及语义入口限制和纯内存复现；实际候选数量另列服务报告分析。
- [内部表头作用范围评分修复](table-header-scope.md)：共享网格读取尊重HTML明确关联及内部表头组，完整标签联合定位解决重复叶名及路径分段问题；限定信息与值分别判定，合成验证不使用真实语料，失效成绩由统一重评分替换。
- [GLM张量探针](glm-rotary/probe.py)及[数值结果](glm-rotary/result.json)：仅随机张量、配对误差和Graph回放，没有PDF、参考或页面分数。GPU重放须另行进入受控维护窗口，本次清理没有执行。
- [Paddle颜色探针](paddle-color-probe.py)及[pixel结果](paddle-color-probe.json)：仅CPU合成红、蓝、绿、灰像素，到processor入口截停，不加载模型。
- [执行修复合成测试](../../tests/unit/test_moparse_eval_execution_repairs.py)：使用临时合成PDF和模拟SDK验证旋转路由、成功邻居保存及局部导出隔离，已替代依赖旧故障行为的共同层及MinerU边界探针。故障注入不证明实际模型返回过相同异常。
- [Paddle兼容层合成测试](../../tests/unit/test_moparse_eval_paddle_compat.py)与[owner生命周期测试](../../tests/unit/test_moparse_eval_paddle_owner.py)：验证区域颜色、生成遥测、原异常透传、线程身份和关闭等待，不加载真实模型或读取语料。
- [已检查的软件源码](inspected-software/)：仅软件字节和来源，不含模型权重、语料、旧页面输出或测量成绩。Paddle像素探针固定使用被检查的上游软件快照，说明该上游版本的机制，不代表已修复执行器仍会产生同一故障。

CPU重放命令如下，不启动模型或服务，不接收语料参数：

```bash
PYTHONPATH=. .venv/bin/python benchmark/diagnostics/paddle-color-probe.py
.venv/bin/python -m pytest -q tests/unit/test_moparse_eval_execution_repairs.py tests/unit/test_moparse_eval_paddle_compat.py tests/unit/test_moparse_eval_paddle_owner.py
```

## 本轮执行状态

当前工程预检02八组共88项任务完成，其中64项独立单页超时标定成功；范围、配置及实际Graph记录见[执行就绪证据](../reports/20261026-repaired-preflight-02/execution-readiness.json)。本次[执行锁](../execution-lock.json)据此冻结后，P01—P08各完成800页一次及固定80页三轮，MO服务恢复通过，统一评分与首版报告已生成。质量、成本和未知仅由[本轮v3报告](../reports/20261026-lite-v3/report.md)呈现，不在诊断中复制成绩；TTS身份变化、活动或unknown只披露，先前撤回产物不接续、拼接或重建比较，权威状态见[评测索引](../reports/README.md)。

共同条件是受测后端共享16 GiB自有显存预算，TTS保持运行且负载不控制，评测不启动、停止、重启或改配置。受测进程自有显存、TTS和整卡余量分别记录，身份活动与未知如实披露，不宣称独占或TTS空闲；预检任务完成不证明语料正确、解析质量合格或完整长文档性能。环境观测策略变化不修改评分指标、匹配规则和分母。
