# P03：全页 PaddleOCR-VL 1.5

当前共同评测从保存native.json经`moparse_eval/saved_native.py`调用本格式读取器，忠实读取Paddle parsing_res_list中的block_content、HTML/Markdown、区域顺序和媒体。读取器不接收expected答案。最终正文另只读取实际final.md；主指标、失败政策及同版重评由[评测任务](../../benchmark/evaluation-tasks.md#current-task-expected-only)维护。

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

2026-11-12本组已通过Paddle格式族读取器进入既有NativeContentContract和公共source-free内容链。使用本组自己的三页保存native.json及配对observation生成实际final.md和Storage结果；页面、正文、HTML源格、polygon和状态分别核验，不借P04、P01/P05或原件补文。固定范围交付为partial，具体正文、阶段、差异矩阵及独立工程验收由[唯一报告](../../benchmark/reports/lite/report.md)维护，不是解析质量或全P03验收。

## 1. 配置与执行边界

全部页由 PaddleOCR-VL 模型 1.5 的完整管线处理，不接 GLM 分支；研究使用原生 Transformers 推理后端，Python 包与模型 revision 由各次配置及原生产物记录，正式运行前须完成新一轮预检冻结，工程验证边界见第 5 节。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

全页 PaddleOCR-VL 1.5 的页面结果对象或其完整 JSON、原生 Markdown 与 Markdown 图片集合，关联每页实际输入图像、原 PDF 页号和方向变换。包含全部来源类别，不另挂 GLM 分支。

### 2.1 PaddleOCR-VL 页结果

本节依据[官方完整管线说明](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)和[结果序列化源码](https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/inference/pipelines/paddleocr_vl/result.py)，核对日期为 2026-10-21；上游分支会变化。这里描述 P03 的候选接口；锁定实际包与模型后须确认字段和序列化形状，不能将模型名称 1.5 当作 Python 包版本或输出 schema 版本。

```text
predict(...) -> 页面结果对象序列
├── json -> 当前官方示例中的 res 包装与实际页面数据
│   ├── 页面信息 / 尺寸 / model_settings
│   └── parsing_res_list[]
│       └── block_label / block_content / block_bbox / block_order 等
└── markdown
    ├── markdown_texts
    └── markdown_images -> 图片名或引用到图像对象的映射
```

| 内容 | 官方接口中的载体与含义 |
| --- | --- |
| 完整页结果 | `PaddleOCRVL.predict()` 产生页面结果对象，可读 `json`、`markdown` 并保存 JSON、Markdown；只调用 VLM 聊天接口不是本组完整解析 |
| 页面与布局 | JSON 中的页面信息、尺寸、有效配置和 `parsing_res_list`；图片输入的 `page_index` 可能为空，必须保留调用清单的原 PDF 页号 |
| 区域 | `block_label`、`block_content`、`block_bbox`、`block_id`、可空的 `block_order`；某些版本还有分组、多边形及跨页标识，存在时原样保留 |
| 坐标与表格 | 框或多边形绑定输入页面及其尺寸；表格内容按实际返回的 HTML/Markdown 读取，不把布局区域框等分成原生源格坐标 |
| Markdown 与图片 | `markdown_texts`、`markdown_images` 和可能的 `page_continuation_flags`；图片集合含真实图像对象，不能只保存文字或把布局可视化当业务图片 |
| 序列化差异 | 结果对象、JSON 的 `res` 包装和保存文件不必同形；格式化、忽略标签及选项会影响字段和文本，须以固定版本实物确认 |

研究导出检查是否默认忽略页眉页脚或特定标签，按已有区域保存完整内容；服务清理另做。跨页标志是候选观测，不直接授权段落拼接、继承表头或合表。可选图表理解不纳入当前服务范围，不额外开启图片语义化；已有原生附加内容仍保存在原始结果中，不扩展本轮关系评分。

### 2.2 标题角色与级别来源

2026-10-27追踪正式Paddle镜像内PaddleX 3.7.2的markdown_format_funcs.py：doc_title固定导出一级标题；paragraph_title有title_level时使用该声明，否则按标题内点号数量及固定偏移生成二级或更深标题。纯合成导出验证中，普通标题产生二级标题，1.2开头及普通文字含一个点号的标题均产生三级标题，说明这些级别可以来自软件格式规则。可选restructure_pages才调用额外层级分配，本轮逐页predict执行入口未调用该步骤。当前标题归属按expected明确文字与原生顺序读取，不要求私有关系字段；这些SDK显示级别不证明模型恢复了真实多级树。

## 3. 研究侧读取与导出

先固定 Python 包、推理后端及 1.5 模型身份，再核对[本页字段说明](#21-paddleocr-vl-页结果)对应的真实包装和默认导出。保存原始 `parsing_res_list` 与可用图片，忠实导出已有内容；标签忽略设置造成的遗漏要从本组已有结构核对，不能从 PDF 原生文字补回。

候选上下文读取保留原生`number`区域的文字。所检固定版pipeline将`number`与页眉、页脚列为默认Markdown忽略区域；本轮忠实读取不会丢弃这些文字，仅在表题范围读取时将该独立编号角色视为分页家具。`formula_number`等其他编号角色不作同样处理。共享列名读取规则及边界由[共同评测任务](../../benchmark/evaluation-tasks.md#layout-relations)维护，不从expected补列名。

## 4. MO-Parse 适配逻辑

1. 用调用页清单关联逐页结果；不以图片输入可能为空的 `page_index` 丢弃原始页身份。
2. 读取区域列表、顺序及可选分组，保留 `block_order=None` 等未知状态；不按 bbox 简单重新排序全部块。
3. 表格内容有 HTML 时保存单元格和跨度，仅有 Markdown 时明确结构缺口；用途判定独立于 `block_label=table`。
4. 保存 `markdown_images` 中的图片字节与引用，布局可视化另作诊断；正文、图片和页边角色进入服务组装与清理。

## 5. 实现状态与验证项

P03研究执行路径已修复，[P03工程预检02](../../benchmark/runs/lite/preflight/)独立完成同一清单的11个任务并提供本次冻结依据。本组保存quality800一次和perf80三轮的有效原生结果及测量；错误评分及结论已删除；本轮以完整身份、候选上下文和源位置核对后的同一程序重评，完成范围以评测索引为准；结果只见[当前统一评测报告](../../benchmark/reports/lite/report.md)，状态与限制由[评测索引](../../benchmark/reports/README.md)维护。TTS只观测不控制，先前撤回测量不恢复；执行和自动评分完成不构成内容、Gold或图片内容验收。

研究执行器、完整页面 native RPC 服务及薄读取器已实现。固定 PaddleX 3.7.2 路径的 BGR/RGB 交接缺陷已在研究路径修复；该问题与线程生命周期引发的宿主内存留存分开处理。模型及调用由长期线程统一持有，并显式使用 use_queues=False；本组独立工程预检不借用 P04 的产物，也不据此宣称内容或效率已验收。机制诊断见[执行层诊断](../../benchmark/diagnostics/README.md)。

HGNetV2 布局子模块不支持全局 SDPA，与 VLM 的 attention 设置分别配置；模型、processor 与原生注册名按冻结身份记录。颜色交接、区域 token/EOS 和截断、有效邻居、媒体、取消清理及资源状态由本组工程证据和运行记录分别追溯，不把任务完成当作逐项内容验收。CUDA Graphs 按真实有界捕获与推理记录描述，失败及 eager 例外保留；格式字段、工程预检或合成探针不能替代完整管线测量。

本组保存配置声明PaddleOCR-VL-1.5，paddle_vlm revision为`2a4195faa5e7914c12f2fc601d72c81caf8d2da5`。选定主结果保留“证券简称：万科 A、万科 H 代”的原生空格，表头日期没有P04的字面反斜杠+n；这些是本组自己的保存内容，不按版本名补全或统一。本轮未在线核验模型和镜像。

### 5.1 固定三页保存格式与共同服务验收

2026-11-13的共同状态修正保留以下全部原生unknown，不再仅因reader报告未知便降级。group语义只有被当前输出责任依赖时才阻断；单独区域没有成对读序责任。当前三页实样仍有多区域读序未获证实及三处媒体未交付，新的开发复验仍为partial，历史正文与状态工件不改写；当前影响依据与完整回归仅见唯一报告。

本轮选择vanke-repurchase-share-changes-p001-003仅因实际格式覆盖：三页区域数14、14、3，含标题、正文、真实HTML表格、polygon、nullable block_order和媒体声明。主视图为各页raw.res.parsing_res_list；raw.research_region_exports及entry.faithful_markdown存在，但只保留审计、不补主答案。res.page_index/page_count均为None，输入物理页由原页调用清单建立，不把None改为0，也不按分支局部索引代替原PDF页。

实际区域提供block_id、block_label、block_content、block_bbox、block_order、group_id和block_polygon_points，没有本轮可用的原生独立OCR源格、cell bbox/polygon或原生语义父链。每页group_id在当前样本中唯一，跨页重复；同版SDK序列化可将缺失group_id回退为数组idx，因此本轮不能判定这些值来自真实合并组还是回退。共同输入保留页内group identity，不生成父子或跨页关系；真实多成员组尚未覆盖，仅由独立JSON测试保护。

同版PaddleX 3.7.2缓存源码的_to_json只为未列入skip_order_labels的区域递增block_order，表格、附注及图片保留None。它是部分标签的SDK序列化序号，未提供完整全局阅读顺序证明；保留原rank和数组位置，服务显示维持数组顺序，内部明确unknown，不按bbox重排或强行续接同组文字。

页面尺寸为1654×2339，model_settings.use_doc_preprocessor=false；原生region bbox和polygon分别保留，即使局部边界不同也不互相替换。像素单位及TOPLEFT由同版CropByBoxes的xyxy和img[ymin:ymax,xmin:xmax]合同投影支持，尺寸来自结果记录的处理后图像shape；没有从0至1000数值猜测归一化，也没有套用Docling原点。反向原PDF变换仍为unknown，旋转和cropbox仅保留已有元数据；缺尺寸、退化框或无法确认的预处理变换保留未知，按实际输出依赖决定partial。缓存源码只作静态阅读，未导入或执行Paddle、图像裁剪或模型。

HTML表为8行6列、44个DOM源格，含rowspan/colspan但全部使用td，没有显式header role。MO-Parse解析出的格位属于HTML投影，未冒充SDK独立OCR格或原PDF单元格几何；共同有界用途/计量规则随后建立5个记录、25个值关系及完整表头/期间路径，37个非空格定位到真实final，7个空字面未补值。普通HTML网格、混合/不足结构继续保留或partial，number标签本身不证明页码，因此当前该标签中的公司文字保留。

共同路径为replay_native → app.adapters.saved_native.adapt_saved_document → read_paddle_blocks → NativeContentContract核验 → SavedContentService.finalize → Export/实际IR/TableContext/TableSemantics/FinalContent → Storage。原执行completed、格式读取read、公共转换partial、交付partial分别记录；partial仍有未知完整读序和三处图片未交付的独立依据；group语义未知保留为元数据，不自行阻断。原生vision_footnote文字保留，不据相邻或group_id补出记录附注关系。原生字段、工件/视图/locator、原始与显示文字、状态、对象去向及阶段编辑均可复查，最终正文和持久化按实际UTF-8字节核对。

## 6. 格式核对依据

格式依据为 Paddle 官方候选接口的静态核对。上述结构是类型与字段示意，实际包、模型、镜像和执行参数由各次配置及工程预检原生产物记录，正式运行前须完成新一轮预检冻结；工程验证边界见第 5 节。

官方接口与序列化源码见本页第 2 节。引用的浮动分支用于说明候选字段，不作为本组执行锁。
