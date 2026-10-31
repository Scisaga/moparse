# P08：MinerU 全页纯视觉 SDK + vLLM

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

## 1. 配置与执行边界

全部 PDF 页面渲染成图像，经官方纯视觉 SDK 的 vLLM 路径处理；不读取原生文字层，不接 GLM 或其他解析器。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

全部输入页面图像的纯视觉 `ExtractResult`/`ContentBlock` 序列、该 SDK 的 Markdown 转换结果、必要图片与页清单。它没有 PDF-native `ParseResult.pages`，也没有自动生成的完整 PDF 页身份与输出包。

### 2.1 MinerU 纯视觉 SDK 结果

核对了安装的 `mineru_vl_utils` 2.0.7 的 `mineru_client.py`、`structs.py` 和 `post_process/json2markdown.py`，对照[官方纯视觉 SDK](https://github.com/opendatalab/mineru-vl-utils)。本节说明格式依据；实际软件、模型 revision、镜像及执行参数由各次配置和工程预检原生产物记录，正式运行前须完成新一轮预检冻结，工程验证边界见第 5 节。

```text
输入页清单 -> image[物理页号、尺寸、方向变换]
two_step_extract(image) -> ExtractResult
└── ContentBlock[] -> type / bbox / angle / content / 可选 merge_prev

批量结果 -> 按输入页关联上述列表
json2md(...) -> 已有块内容的 Markdown，不是 PDF-native ParseResult
```

| 内容 | SDK 载体与含义 |
| --- | --- |
| 输入与返回 | `two_step_extract(image)` 返回每页 `ExtractResult`，是 `ContentBlock` 列表；批量路径按输入图像关联每页结果，没有自动获得原 PDF 页号 |
| 块字段 | `type`、`bbox`、`angle`、`content`；文本可有 `merge_prev`，有评分选项时可提供额外评分信息，未提供时不编造 |
| 坐标 | bbox 为输入图像上的 0–1 归一化框；先关联图像尺寸与方向变换，再对应物理页 |
| 表格与正文 | 文字、公式及表格内容按实际返回处理；延续标志和块类型只是观测，不是完整表头或用途真值 |
| Markdown 与媒体 | 原生 `json2md` 主要拼接已有内容，不自动组成完整 PDF、图片包或 MO-Parse 文档；图片块无文本不代表该图已经交付 |

2026-10-27按正式worker镜像内固定2.0.7源码再次核实：`title`、`doc_title`、`paragraph_title`是标题角色，`header`是页眉；`ContentBlock`不提供标题level、父标题或文档标题树。该版`json2md`处理content与merge_prev，不因标题type添加Markdown的`#`。研究适配保留这些类型、内容和官方导出，不能将没有层级字段解释成没有识别标题，也不能自行补层级。层级从属的证据未提供、端点未定位和明确错误按[统一评分标准](../../benchmark/evaluation-tasks.md#41-定位)分别记录；本轮不新增标题树恢复方法。

### 2.2 标题请求、协议与参数边界

2026-10-27进一步追踪固定2.0.7全链路，并将正式worker中的六份关键软件文件与官方发布标签逐字核对：布局阶段使用Layout Detection提示，解码读取bbox、type、angle及正文续接标志；标题区域默认使用Text Recognition提示，结果写入content；HTTP读取只去除末尾结束标记，SDK后处理与json2md均不建立标题层级。当前执行使用正确的MinerU2.5-Pro-2605-1.2B权重revision和对应服务别名，未发现模型名称配错或适配器丢弃SDK已提供level的证据。固定版依据见[请求与解码](https://github.com/opendatalab/mineru-vl-utils/blob/mineru_vl_utils-2.0.7-released/mineru_vl_utils/mineru_client.py)、[块结构](https://github.com/opendatalab/mineru-vl-utils/blob/mineru_vl_utils-2.0.7-released/mineru_vl_utils/structs.py)及[官方导出](https://github.com/opendatalab/mineru-vl-utils/blob/mineru_vl_utils-2.0.7-released/mineru_vl_utils/post_process/json2markdown.py)。

受控合成响应经真实解码函数验证：title、doc_title、paragraph_title均保留类型而没有level；额外尾部层级文本不被读取，未知的分级标题类型被拒绝。这验证协议承载边界，不证明真实模型曾产生这些额外标记，也不证明底层模型无法通过另行设计的任务预测层级。当前产物保存SDK解码结果；请求诊断保存采样、结束和用量信息，不提供解码前完整布局文本，故不把协议判断扩大成对未保存原始生成内容的断言。

该版本没有可漏开的标题层级参数。image_analysis仅控制图片和图表识别，scored增加置信度等诊断，布局尺寸、简化后处理、页眉保留和跨页表格参数不提供标题树。自定义prompts虽可覆盖，但配套的输出协议、解析及质量成本验证均需另行设计，不能当作已存在的优化开关。P06/P07的完整PDF布局步骤和可选外部LLM后处理不能直接算入本组现有身份。当前heading_of证据门槛能够读取其他SDK默认或规则生成的标题级别，而本组角色标题无级别；该差异反映固定管线的输出与处理步骤，不能单独据此给底层模型的层级能力排名。

P08 的必要裁图只能使用本组输入页面图像及 SDK 区域，保存裁图方式并计入完整管线处理成本，不能读取原生字层、矢量文字或另一解析器补答案。服务需要的区域关系仍须按来源证据判断，不能将 P06/P07 的 PDF-native 结构套到这种平面块列表上。

## 3. 研究侧读取与导出

固定 SDK 和 vLLM 入口，逐页保存块序列、空内容、现有分数与阶段失败。调用官方完整布局和识别路径，并保存 Markdown 转换所用数据；不能把 OpenAI 接口的一段最终文本当作本组完成的全页 SDK 结果。

## 4. MO-Parse 适配逻辑

1. 用输入图像清单绑定物理页、尺寸和方向变换，保留块的 `type`、bbox、角度、顺序和延续观测。
2. 表格按实际 HTML/Markdown 内容读取；缺少源格或角色证据时保持未知，布局区域不自动成为语义数据表。
3. 原生图片字节若未提供，按本组页面图像和 SDK 区域裁出必要资产；保留图题与图片原位引用，不调用原生文字层、GLM 或第二解析器。
4. 将已确认内容交给服务转换和组装，保留未检测、识别缺失和结构未知。`json2md` 没有输出某图片块的文字，不能被解释为该图不存在。

## 5. 实现状态与验证项

2026-10-30工作区采用与P07共用的HTML单元格与跨度读取，并增加基于明确字段或计量记录的局部语义入口；消费视觉SDK实际保存的表前说明、标题、局部期间与附注，不要求PDF格网。转换器不读取PDF文字层、矢量表格或P07答案，不恢复原生未保存的子项层级。表格用途、范围和partial状态独立记录，改善须进入真实返回正文；受控测试与实测结果分开，尚未部署。

2026-10-29工作区新增[视觉结果适配器](../../app/parsers/mineru_visual_result.py)，直接读取固定SDK块的`content`、`type`、bbox和`merge_prev`，隔离畸形区域并保留邻居。固定SDK的`content`允许None；无文字的列表容器和图片块保留原始空值及位置，不误报读取失败。HTML表体沿实际单元格与跨度交接，图片沿本组页面图像裁取；不调用原生文字层、矢量表格补充或其他解析器。标题角色形成显示边界，`doc_title`显示为一级标题，其余标题角色显示为二级标题，不宣称真实多级从属。最终正文只采用唯一、相邻且无标题、表格、图片阻隔的显式正文续接，以及输出契约规定的受限同页货币单位断裂处理；不跨非正文块猜接事件上下文。当前接入已保存原生产物的服务replay，未新增线上模型执行入口或更改部署。按[配对协议](../../benchmark/evaluation-tasks.md#7-p07p08与mo-parse最终输出的配对评测)与P07共同验证，结果由评测索引维护。

P08研究执行路径已修复，[P08工程预检02](../../benchmark/reports/20261026-repaired-preflight-02/)独立完成同一清单的11个任务并提供本次冻结依据。本组已完成quality800一次和perf80三轮，八组统一评分、首版报告及原MO服务恢复完成；结果只见[本轮v3报告](../../benchmark/reports/20261026-lite-v3/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS只观测不控制，先前撤回测量不恢复；执行和自动评分完成不构成内容、Gold或图片内容验收。

研究侧已有独立 P08 执行器，直接调用官方 SDK 的 aio_two_step_extract，关闭 image_analysis 与重试，不读取原生文字或其他解析器补答案。源码追踪未发现其 Qwen2VL/NeoX 解码器具有 P05 的 GPT-J rotary 配对冲突；这只是该机制的边界，不构成完整模型数值或解析质量验收。机制诊断统一见[执行层诊断](../../benchmark/diagnostics/README.md)。

故障注入暴露的导出异常阻断原生结果问题已在研究路径修复，原生块与有效邻居先行保全，局部裁图和导出失败单独记录。SDK 默认将 length 截断报错，本组保留 token/EOS、空白、失败、媒体及取消状态，供完整渲染、原生顺序、忠实导出和资产交付的工程追溯。未提供格位或关系保持缺失，不将格式存在或执行成功当作图片保全和来源内容验收。

## 6. 格式核对依据

2026-11-01工作区采用共同的局部期间、行内明确单位、父子列表终点及完整表前业务范围表达，所有文字与关系只来自本组已保存的视觉结果。原生没有给出续表声明或完整来源时保留原表，不使用PDF文字层、矢量结构、P07或expected补限定。具体守卫见[表格证据规则](../specs/table-source.md)，隔离CPU回放、共同评分与实际目读范围见[评测索引](../../benchmark/reports/README.md)，软件实现尚未部署。

2026-10-31工作区沿用共同表格后处理的剩余跨度、已有分组标题保全、明确附注标签转写及局部印刷单位优先规则，证据全部来自本组已保存的视觉原生结果。没有使用PDF文字层、矢量表格或P07结果补充标签；来源约束见[表格证据规则](../specs/table-source.md)，实际回放与内容目读范围见[评测索引](../../benchmark/reports/README.md)。

格式依据为 `mineru_vl_utils==2.0.7` 的静态核对。上述结构是类型与字段示意，实际软件、模型、镜像和执行参数由各次配置及工程预检原生产物记录，正式运行前须完成新一轮预检冻结；工程验证边界见第 5 节。

实现参考：[MinerU SDK 依赖参考](../../docker/mineru-vllm/requirements.txt)。官方格式与源码链接在本页相应分支说明中列出。

以下为已核对源码文件的 SHA256，用于复查格式依据；模型权重及运行身份另行固定。

| 安装包源码文件 | SHA256 |
| --- | --- |
| `mineru_vl_utils 2.0.7: structs.py` | `61163066b9084e25f7ef24d55bda2bbcd5d823aabc7c909d7c513284acd59fcf` |
| `mineru_vl_utils 2.0.7: post_process/json2markdown.py` | `1b16b29f789a3b3d8e7bf638a573ecb52623be6304a289fc80c0f6ce97188bd2` |
