# MO-Parse expected-only：第四阶段续做入口

工作区为`/opt/moparse`，`/opt/mosaic-parse`为同一入口。先读AGENTS.md、benchmark/evaluation-tasks.md、唯一Lite报告及现有来源诊断，以本地HEAD和工作区为准，不回退或覆盖已有修改。第四阶段固定5份已完成完整来源独立审查及必要修复；逐份结论、B/L、真实剩余阻塞及最终身份只从report.md与actual-source-diagnosis.json.phase4_independent_acceptance读取。

固定成员为huawei-compliance-management-p051-053、huawei-management-toc-p014、tencent-conditions-entity-payment-definitions-p108-114、tencent-redemption-bearer-payments-p135-140、tencent-registered-tax-default-trustee-p141-148。手写来源声明在tests/validation/lite_stage4_assertions.py；统一Oracle仍为tests/validation/lite_source_oracle.py，默认执行原56份及新增5份，并保留五处BIS/IEA局部来源。不要以责任完整、没有pending、当前视图自洽或测试数量替代独立整样本验收，也不要重建AST、Oracle或来源义务系统。

必要回归加强了旧腾讯L1680/L1693的续段父链：分别为[1674,1676]及[1684,1685,1689]，按原始缩进及插值条件保留完整责任。原华为前言L39–L50的12个明确目录项也增加强制类型化导航及顺序断言；其余来源断言及原56份成员保留。旧失败在既有验证目录，不能删除失败或放宽为双表示来恢复通过。

列表续段、软换行父链、页码在前的导航、同名不同父组、目录顺序及正文/目录身份均有完整链反例。候选必须暴露自己的导航证据，不能继承expected的section-toc标签。正文阅读顺序只在两端独立来源唯一、完整内容所有权和全部中间顺序边都成立时转为唯一计票证明；其他关系不能因同类型或同一来源被删除。表示和责任规则以evaluation-tasks.md为准。

最终证据在benchmark/runs/lite/requirements/validation/：oracle-validation.json、comparison-validation.json、mutations-validation.json、software-validation.json、baseline-preservation.json、stage4-controlled-outcomes.json、stage4-preservation.json及stage4-final-binding.json。核验实际software_id、测试、手写断言聚合和current索引身份；git_head早于后续提交本身不否定同软件证据。不得修改核心源码后沿用旧通过记录。

执行范围说明在stage4-execution-scope.json：第四阶段沿用的全量回归包含读取、渲染合成PDF、图像及合成字层的既有测试，已明确记录为执行边界偏差；真实来源未读取，五份验收判断未使用这些fixture。后续source-only任务执行前须排查此类测试，不能把旧回归清单当作读取许可，也不能重述为“完全未读取PDF或图片”。

继续保护1639项完整计量、顺丰221项原payload及其161项typed/60项既有内容责任、华为L1586三项、平安C首句及4条关系、互斥余段和混合顺序，以及五个原始输入范围。源码及断言冻结后先核对software-validation.json中原受控命令与当轮授权边界，排除未经授权的PDF、图像及字层测试，明确记录实际执行范围；再执行授权范围内的完整回归，以16个CPU分析进程同版重建173份JSON/XML并核对逐项B/L变化、来源及当前绑定。退出码2须检查真实阻塞，不删目标或裁selection求0。旧生成视图经核验后原位替换，不归档过期答案。

下一阶段仍须按用户授权确定范围。集合外自动责任完整只进入待独立验收，不能自动称整样本通过。保留comparison_contract_coverage中的全部未完成样本、语言分析限制与五个输入范围；56+5局部验收不等于全局语义或质量完成。

当前只允许source-only软件工作及独立合成candidate。禁止PDF、图片、字层、OCR、VLM、推理、模型裁判、真实候选比较、保存输出诊断、八组真实回放、正式评分、GPU/TTS/服务操作、部署、公开API修改、提交和推送；这些后续阶段不因本轮通过自动开放。所有canonical expected、映射、selection、页包、语料、有效native、历史正文及原始成本只读。只维护唯一Lite报告和现有诊断验证目录；通用检查排除语料、datasets、reference-decisions、runs及reports，不向AGENTS.md追加任务全文。
