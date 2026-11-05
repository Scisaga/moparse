# P07/P08 保存正文的原生与组装归因

本文是[当前唯一 Lite 报告](../reports/lite/report.md)的文字诊断证据，只判断下述两个真实选段中差异首次能在哪里被观察到。读取范围为同一配置自己的保存原生文字/结构、baseline/current Markdown、已有 exported/final 快照与编辑账本；没有回放、模型执行、PDF/图片读取或候选改写，没有质量成绩、采用结论或完整覆盖声明。另一配置仅沿自己的保存链核对，不能替 P07 补出任何字词、日期或关系。

保存执行身份也与正在开发的评分软件身份分开：四份 service run.json 中，baseline 的 software_id 为 `f5e9063bfd2ac64be79796389d4cdaf3ad3770a8820a0628a1b245fff05a8a03`，current 为 `bcb3b2d3ac3a2546c0108f75a178a065c27d81aef8a8756afcbeabb51704a9f7`。本轮未重算这些执行或改动其正文、快照、时长。记录见 [P07 baseline](../runs/lite/service/baseline/p07/run.json)、[P07 current](../runs/lite/service/current/p07/run.json)、[P08 baseline](../runs/lite/service/baseline/p08/run.json)、[P08 current](../runs/lite/service/current/p08/run.json)。

## NVIDIA 会议准入字段：标签交错已在原生片段中

样本 `nvidia-meeting-notice-toc-p015-016` 的[只读 expected](../../pdf_sample/parsing/expected/complex-nvidia-2025-annual/expected.md) L373-L374 实际要求如下，其中 `Virtual meeting admission` 和 `Pre-meeting forum` 各是完整标签，`you will need` 是连续正文：

```text
- Virtual meeting admission: We will be holding the 2025 Meeting virtually at the location listed above. To participate, you will need the Control Number included on your notice of proxy materials or printed proxy card.
- Pre-meeting forum: To communicate with our stockholders in connection with the 2025 Meeting, we have established a pre-meeting forum located at www.proxyvote.com where you can submit advance questions.
```

P07 该页为 MinerU 分支。[原生 native.json](../runs/lite/artifacts/P07/measured-quality800-r1/nvidia-meeting-notice-toc-p015-016/native.json) 的 `#/documents/0/pages/0/blocks/8/content` 已按以下顺序保存，并非到 current 最终正文才插入 `admission:`：

```json
[
  {"type":"text","content":"Virtual meeting","styles":["bold"]},
  {"type":"text","content":" We will be holding the 2025 Meeting virtually at the location listed above. To participate, you will ","styles":[]},
  {"type":"text","content":"admission:","styles":["bold"]},
  {"type":"text","content":" need the Control Number included on your notice of proxy materials or printed proxy card.","styles":[]}
]
```

同一原生文件 `#/pages/0/raw/blocks/8/content` 也保存这四段，`#/pages/0/raw/blocks/8/markdown` 与 `#/pages/0/faithful_markdown` 已打印 `you will **admission:** need`。下一块 `#/documents/0/pages/0/blocks/9/content` 同样依次为 `Pre-meeting`、` To communicate ... we have established a `、`forum:`、` pre-meeting forum ...`。这是同页另一个已观察到的标签与正文交错实例，不是全量发生次数。

| 同一 P07 保存阶段 | 实际位置与字面 |
| --- | --- |
| [baseline exported](../runs/lite/service/baseline/p07/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/stages/exported.md) | L23 `you will **admission:** need`；L25 `established a **forum:** pre-meeting forum` |
| [baseline final](../runs/lite/service/baseline/p07/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/final.md) | L23 `you will <strong>admission:</strong> need`；L25 `established a <strong>forum:</strong> pre-meeting forum` |
| [current exported](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/stages/exported.md) | L23 与 baseline exported 的上述文字相同；L25 同样交错 |
| [current final](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/final.md) | L23 与 baseline final 的上述文字相同；L25 同样交错 |

[P07 current service-evidence.json](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/service-evidence.json) 的 `final_text_evidence.assembly_markdown` 已包含相同交错，`edits` 对应项的 reason 是 `explicit_native_inline_style`：把原已出现的 `**admission:**` 渲染成 `<strong>admission:</strong>`，没有在这一步新增这个词或改变其词序。保存的[执行软件](../runs/lite/service/current/p07/software/app/services/final_content_service.py) L120-L143 按 children 原顺序连接，只在其旧渲染与完整 block.markdown 一致时替换样式；L198-L203 以 `explicit_native_inline_style` 记账。已保存的 exported 和 assembly 是实际文档渲染，不是从 expected 重建的正文。

P08 必须独立读取自己的证据：[P08 native.json](../runs/lite/artifacts/P08/measured-quality800-r1/nvidia-meeting-notice-toc-p015-016/native.json) 的 `#/pages/0/raw/13/content` 为完整的 `Virtual meeting admission: ... To participate, you will need the Control Number ...`，`#/pages/0/raw/14/content` 为完整的 `Pre-meeting forum: ... established a pre-meeting forum ...`。这两个原生 content 自己已提供完整标签及连续谓语；[baseline exported](../runs/lite/service/baseline/p08/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/stages/exported.md)、[baseline final](../runs/lite/service/baseline/p08/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/final.md)、[current exported](../runs/lite/service/current/p08/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/stages/exported.md) 和 [current final](../runs/lite/service/current/p08/candidate/artifacts/quality800-r1-nvidia-meeting-notice-toc-p015-016/final.md) 的 L31/L33 均维持各自上述完整文字。

可归因到的最早保存点是 P07 原生 SDK typed content 的顺序。现有快照没有更早的模型 token/行绑定阶段，因此不能进一步断言由识别、SDK 行组装还是更早的适配步骤造成。证据不支持把它写成 current 转换器新增正文损失，也不支持从 expected 或 P08 把标签搬回后声称 P07 自己表达了该关系。若后续修改这类重排，须先有候选自己提供的标签/正文绑定证据和独立反例；本例的四个文字片段本身只证明当前顺序，不能单靠正确答案决定搬动位置。

## HKEX 时间线：事件日期在原生结果中已经缺失

独立样本 `hkex-operational-timeline-p008-009` 属于另一文档与布局文字类型。[只读 expected](../../pdf_sample/parsing/expected/complex-hkex-2024-annual/expected.md) L89-L91 的 `Regulation` 分组下要求日期与事件正文绑定：

```text
- 19 Apr: Consultation conclusions on Enhancement of Climate-related Disclosures under the Environmental, Social and Governance Framework published, with Listing Rules amendments effective from 1 January 2025
```

P07 该页为 GLM 分支。[P07 native.json](../runs/lite/artifacts/P07/measured-quality800-r1/hkex-operational-timeline-p008-009/native.json) 的 `#/pages/0/raw/raw_json_result/0/8/content` 与 `#/pages/0/raw/json_result/0/8/content` 均是下列完整事件正文，没有开头日期：

```text
Consultation conclusions on Enhancement of Climate-related Disclosures under the Environmental, Social and Governance Framework published, with Listing Rules amendments effective from 1 January 2025
```

该原生页的 `markdown_result`、`research_raw_stage_markdown` 和 `faithful_markdown` 中，`Regulation` 后同样直接接此句，没有 `19 Apr`。这不是把事件正文内的生效日期 `1 January 2025` 当作事件日期；两个角色不能相互补足。

| 同一 P07 保存阶段 | 实际位置 |
| --- | --- |
| [baseline exported](../runs/lite/service/baseline/p07/candidate/artifacts/quality800-r1-hkex-operational-timeline-p008-009/stages/exported.md) | L17 `## Regulation`；L19 为上述事件正文，未打印 `19 Apr` |
| [baseline final](../runs/lite/service/baseline/p07/candidate/artifacts/quality800-r1-hkex-operational-timeline-p008-009/final.md) | L17/L19 保持上述表达 |
| [current exported](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-hkex-operational-timeline-p008-009/stages/exported.md) | L17/L19 保持上述表达 |
| [current final](../runs/lite/service/current/p07/candidate/artifacts/quality800-r1-hkex-operational-timeline-p008-009/final.md) | L17/L19 保持上述表达 |

P08 的日期有自己独立的原生出处：[P08 native.json](../runs/lite/artifacts/P08/measured-quality800-r1/hkex-operational-timeline-p008-009/native.json) 的 `#/pages/0/raw/14/content` 是 `19 Apr`，紧随其后的 `#/pages/0/raw/15/content` 是上述事件正文。[baseline exported](../runs/lite/service/baseline/p08/candidate/artifacts/quality800-r1-hkex-operational-timeline-p008-009/stages/exported.md)、[baseline final](../runs/lite/service/baseline/p08/candidate/artifacts/quality800-r1-hkex-operational-timeline-p008-009/final.md)、[current exported](../runs/lite/service/current/p08/candidate/artifacts/quality800-r1-hkex-operational-timeline-p008-009/stages/exported.md) 和 [current final](../runs/lite/service/current/p08/candidate/artifacts/quality800-r1-hkex-operational-timeline-p008-009/final.md) 均在 L30 打印 `## 19 Apr`，L32 打印事件正文。这里只核对这两个相邻输出位置；日期标题是否在完整时间线中可靠绑定到各事件，仍需统一 L 判定，不以存在日期直接认定整组选段关系正确。

可归因到的最早保存点是 P07 GLM 原生内容及其原生 Markdown 已缺少该日期。服务已有的第一份 exported 和最终文档均未显示进一步删除该事件的字词。P07 的缺日期不能由 P08 或 expected 填回，也不能归为有证据可修的服务清洗删除。

## 这份诊断支持的实现范围

这两例纠正的是软件缺陷归因：NVIDIA 原生标签顺序交错、HKEX 原生事件日期缺失，与 service 阶段新增丢词需要分开。所检查的具体正文片段未证实 baseline 到 current 新增转换损失，不能扩写为全选段正确、全部 P07/P08 零转换损失、转换已完成或可以采用。NVIDIA 普通正文读取仍需把已打印的中断词保留为候选实际内容，不能在评分读取器里跳过 `admission:` 后补成正确连续谓语。

这两例没有提供足以支持正文重排或补字的候选自有证据，因此没有新增针对这些片段的转换修复。共享measurement helper另有单位角色修正并用于评分读回验证，未据此重放后处理或修改现存正文，不能宣称交付收益。后续若要定位服务真实删除，应继续要求同一候选的 native 明确包含目标正文，并在更晚的某一已保存阶段首次消失或换绑，再以该最早相邻阶段及其编辑账本限定代码修改范围；源已缺失和无来源推断保持分开。
