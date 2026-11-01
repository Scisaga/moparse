# 待比较的8条完整解析管线

本文件定义本轮主对比的8个固定配置，不记录历史成绩，不预先选择优胜方法。数据集、测试任务和评分要求见[评估任务](evaluation-tasks.md)；MinerU内部参数研究见[MinerU调优](mineru-tuning.md)，不增加本表的主比较组数。

本轮八组已按冻结身份各完成quality800一次和perf80三轮，统一评分、首版报告及原MO服务恢复完成。结果只见[当前统一评测报告](reports/20261101-preservation-repair-08/report.md)，当前状态与限制由[评测索引](reports/README.md)维护。TTS仅观测不控制，先前撤回测量不恢复；执行和预检完成不构成内容、Gold或图片内容验收，缺陷机制与修复边界见[工程诊断](diagnostics/README.md)。

本表定义[研究顺序](../docs/research/research-framework.md#2-管线研究的顺序)第 3 步的固定配置，用于第 4 步执行和第 5 步分析。比较对象是各管线本身的解析结果与处理成本，不要求直接满足 MO-Parse 接口最终语义格式。逐组原生输出、格式依据与适配逻辑统一见[管线输出与适配](../docs/pipelines/README.md)；服务集成按[技术路线](../docs/engineering/technical-route.md)先确认本组输出再设计适配和共同组装，新增路由仍由比较证据决定。

## 主比较配置

| 编号 | 完整管线 | 原生PDF页 | 扫描页与混合页 | 必须固定的区别 |
| --- | --- | --- | --- | --- |
| [P01](../docs/pipelines/p01-docling-v1-glm.md) | Docling 2.139.0 TableFormer V1 + GLM-OCR SDK | CPU Docling；V1；accurate；matching=False；PyPdfium；原生OCR关闭 | GLM-OCR SDK | 与P02只改变TableFormer模型版本 |
| [P02](../docs/pipelines/p02-docling-v2-glm.md) | Docling 2.139.0 TableFormer V2 + GLM-OCR SDK | CPU Docling；V2；accurate；matching=False；PyPdfium；原生OCR关闭 | 与P01相同的GLM-OCR SDK | 与P01保持相同Docling包、布局模型、后端、线程及其他参数 |
| [P03](../docs/pipelines/p03-paddleocr-vl-1.5.md) | 全页PaddleOCR-VL 1.5 | PaddleOCR-VL 1.5自身完整解析 | 同一PaddleOCR-VL 1.5自身完整解析 | 所有页均由本模型完成，不调用GLM替代扫描页 |
| [P04](../docs/pipelines/p04-paddleocr-vl-1.6.md) | 全页PaddleOCR-VL 1.6 | PaddleOCR-VL 1.6自身完整解析 | 同一PaddleOCR-VL 1.6自身完整解析 | 与P03使用同一方向前处理、渲染、输出适配和资源预算 |
| [P05](../docs/pipelines/p05-glm-sdk.md) | 全页GLM-OCR SDK | GLM-OCR SDK自身布局与识别 | 同一GLM-OCR SDK | 所有页走SDK，不保留原生解析器旁路 |
| [P06](../docs/pipelines/p06-mineru-standard-glm.md) | MinerU 4.0.12 Standard + TXT + GLM-OCR SDK | `tier=standard`、`ocr_mode=txt`、`image_analysis=False` | 与P01、P02、P07相同的GLM-OCR SDK | 与P07只改变MinerU的tier |
| [P07](../docs/pipelines/p07-mineru-advanced-glm.md) | MinerU 4.0.12 Advanced + TXT + GLM-OCR SDK | `tier=advanced`、`ocr_mode=txt`、`image_analysis=False` | 与P01、P02、P06相同的GLM-OCR SDK | 保留PDF原文字层，不能静默改成纯视觉 |
| [P08](../docs/pipelines/p08-mineru-visual.md) | MinerU纯视觉全页vLLM | PDF渲染为页面图像，再由官方纯视觉SDK完成提取与Markdown转换 | 同一纯视觉路径 | 所有页使用图像输入；不读取PDF原字层补字，不调用GLM |

P03与P04的1.5和1.6指PaddleOCR-VL模型版本，不是PaddleOCR Python包版本。P06与P07的4.0.12是MinerU解析软件版本；下面的MinerU2.5-Pro是其调用的视觉模型身份。P08只比较vLLM执行器，不额外引入Transformers组。

## 相同输入、方向前处理与页面路由

本轮输入由用户已授权的独立可迁移Lite数据包提供，具体范围见[数据集与独立输入](evaluation-tasks.md#2-数据集选样与视觉标注)。Lite为800个实际页，可为单页、连续页段或完整短文档；Full保留完整原件，本轮不运行。页面选择与分类必须先视觉确认并在查看待测输出前冻结，禁止由解析结果或成绩挑页。额外六份公开PDF继续暂不处理，不用于预热或回归。

每组接收同一份冻结独立输入，使用相同前处理策略和缓存口径。人工类别只用于独立分层评分，不能免费路由；运行时共同来源判断是被测管线工作，不是语料复核。P01、P02、P06、P07按共同判断将原生页送本组原生解析器、扫描和混合页送相同GLM SDK；不确定页明确记录，不能各组挑有利分支。必要分类、渲染、方向变换均计入本组处理成本，不免费复用另一组计算结果。

方向处理统一执行一次。使用同一CPU方向模型和版本，对需要视觉识别的页面确定旋转角度，保存角度及原坐标变换；统一生成纠正方向的PDF视图和200 DPI RGB页面图。原生PDF视图必须保留文字层和矢量结构，不得通过栅格化抹掉TXT路径的输入优势。所有模型自身的重复方向分类或旋转模块关闭；若某个适配器无法做到，先补齐适配能力再纳入主对比。

统一方向模型采用`PaddlePaddle/PP-LCNet_x1_0_doc_ori_safetensors`，revision为`b2716954d2e321dd4436400b37584fab641027ab`，并核对实际权重SHA。可复用[方向模型下载器](../scripts/download_orientation_model.py)和[CPU方向服务](../app/services/orientation_service.py)。共同前处理的耗时和缓存策略必须对8组一致，计入完整管线时间。

P03、P04、P05、P08不使用页分类进行模型路由：原生、扫描、混合页全部由本组指定模型处理。它们可读取同一份分类清单用于分层统计，不能据此改用Docling、MinerU TXT或其他模型。

## 各配置的信息许可

相同 PDF 输入不等于免费共用所有字层、矢量及其他解析器的答案。下列许可适用于解析和研究侧结果读回、忠实导出；MO-Parse 后续服务转换不是本次管线输出的一部分，其补充信息不能回填为本组解析结果。

| 配置或执行分支 | 可用于解析的来源 | 禁止的补全 |
| --- | --- | --- |
| P01/P02/P06/P07 的原生分支 | 声明配置的原生文字、几何、该方法的模型与结构观测 | 金标、其他解析器输出及为单组额外加入的未声明模型 |
| 上述混合配置的 GLM 分支 | 同一 SDK 的图像、布局、文字及结构观测 | 在结果整理时追加原生字形匹配补值，改变既定视觉分支的内容来源 |
| P03/P04/P05 全页视觉路径 | 指定模型从共同渲染页面得到的全部观测与必要图像几何 | 读取原生文字、矢量单元格/字形匹配或其他解析器结果修正输出 |
| P08 纯视觉路径 | 官方纯视觉 SDK 从页面图像得到的观测 | 原生字层或矢量文字补字、GLM 或第二解析器兜底 |

尺寸、旋转及必要 PDF 渲染不属于字层补全。评分侧原件标注可读取必要来源，但不得流入候选运行路径。研究读回代码只能转译已有信息，不能免费加入正确结构、标题或图关系。

## 模型与软件身份

| 对象 | 固定要求 | 冻结与核实要求 |
| --- | --- | --- |
| Docling | Python包`docling==2.139.0`；P01和P02仅TableFormer V1/V2不同 | 显式选择模型类与模型目录，分别冻结V1/V2权重、布局模型、配置和SHA；`fast/accurate`不能代替V1/V2模型选择 |
| MinerU | `mineru==4.0.12`；Standard、Advanced共享同一小模型集合与依赖锁 | 使用保留的[小模型与视觉权重锁](../native_worker/models.lock.json)，固定实际wheel、镜像和转换补丁SHA |
| MinerU视觉模型 | `opendatalab/MinerU2.5-Pro-2605-1.2B`；revision `08aaea840498d49ce16247b6263196cf02814885`；FP16 | P06、P07、P08共用这一权重及服务别名`mineru2.5-pro`，核对实际文件SHA和处理器配置 |
| GLM-OCR | P01、P02、P05、P06、P07使用完全相同的`zai-org/GLM-OCR`权重、SDK布局模型和解码配置 | 先读取实际模型缓存，冻结不可变revision、权重SHA、SDK代码版本及布局模型身份；不能用浮动仓库名冒充已冻结revision |
| PaddleOCR-VL | P03固定模型1.5，P04固定模型1.6；统一FP16及方向处理 | 分别冻结实际模型仓库、revision、权重与处理器SHA，固定PaddleOCR包及推理后端版本；不能从显示名称推断权重已相同或已锁定 |
| 结果读取与导出 | 固定各组读取代码及共同忠实 Markdown 导出规则，保留原始输出 | 记录构建镜像SHA、依赖、实际启动命令与完整配置；不在导出中加入 MO-Parse 语义转换或修正答案 |

当前[工程预检02](reports/20261026-repaired-preflight-02/)已完成，八组分别执行同一清单的11个输入任务；实际配置、直接单页标定、共同截止及Graph证据见[执行就绪记录](reports/20261026-repaired-preflight-02/execution-readiness.json)。据此冻结的[执行锁](execution-lock.json)记录本轮执行代码、镜像、依赖、后端、权重revision、解码参数、资源与导出规则，禁止使用浮动模型身份或失效执行锁。逐组字段、媒体、失败及未验证范围由各管线专文维护；工程预检与已完成的800页正式测量分别记录，结论仅适用于实际可评范围。

旧比较成绩及相关执行锁已撤销删除，不保留为历史基线，也不得恢复。P01—P08按新的冻结身份和同一协议统一比较，不拼接此前不同执行身份的结果。新报告的唯一入口为[评测索引](reports/README.md)，修复机制与未解决事项由[工程诊断](diagnostics/README.md)维护。

## 公平资源与执行参数

8组使用同一型号、同一功率上限的GPU，默认单张RTX 2080 Ti、200 W；一次只运行一条受测管线。CPU前处理、布局分析、PDF解析与SDK的CPU工作合计限定8 CPU、8 GiB宿主内存；GPU推理服务的宿主CPU合计限定4 CPU、宿主内存合计20 GiB。CPU配额和affinity分别记录，不能把8 CPU配额描述成独占8个物理核。

本轮固定GPU 1、200 W、受测进程合计16 GiB自有显存；TTS共驻及计量口径以[评测标准](evaluation-tasks.md)为准。混合管线的MinerU与GLM共享预算，不能加卡。锁定同时驻留策略，全部受测GPU后端合计记录峰值，TTS驻留与整卡余量分别记录；处理中的必要卸载或切换计入耗时，首次初始化与预热单列。无法在预算内运行时保留失败，不增加资源或换模型。按用户2026-10-26最新指令，TTS保持运行且身份活动只观测，其负载不控制，变化或unknown不阻断执行、评分和报告；仅暂停并按原配置恢复目标卡上的原MO-Parse模型，GPU 0及其他项目不动。

独立样本串行提交，外层并发1；后端客户端请求上限4，服务端`max_num_seqs=4`或等价调度上限4。CPU数值库及ORT采用intra_op=8、inter_op=1，Docling页面worker=1、num_threads=8。某框架无等价参数或同进程集成不能按阶段隔离时，必须明确真实调度、配额和测量限制，不能写成相同硬隔离。不得超出已声明总预算。

MinerU VLM固定FP16、上下文8192、`max_num_batched_tokens=2048`、KV cache `134217728`字节、`max_num_seqs=4`；使用`MinerULogitsProcessor`。P06/P07客户端`VlmConfig.max_concurrency=4`，P08纯视觉SDK请求并发同为4；输出长度上限、停止条件、图像缩放和失败截断状态在执行配置中显式保存。

所有支持CUDA Graphs且能在资源预算内运行的GPU后端必须启用，并用真实捕获及推理日志核实。MinerU使用compile mode=0、`FULL_DECODE_ONLY`、capture sizes `[1,2,3,4]`、maximum capture size=4；torch.compile与CUDA Graphs分别记录。GLM及Paddle先核实实际后端支持和捕获配置，不能因为尚未测试就默认eager；确有失败或超预算时保留原始错误、例外原因与恢复条件。

预热与正式测量分开记录，8组使用相同预热原件、次数和冷热缓存定义。主耗时在 worker 内部用单调时钟直接测量，从开始处理完整 PDF 到原始解析、研究侧忠实 Markdown 和必要资产就绪；包含公共前处理、路由、PDF 渲染、全部解析推理、必要模型切换和声明的结果导出。不包含 MO-Parse 的数据表语义化、布局正文还原、页面家具清理、服务正文组装，也不包含 HTTP、接口排队、轮询、下载及纯持久化。不能减常数估算或累加重叠阶段；P08 不能从已渲染图像开始计时。共同超时、取消清理与重试规则预先固定。

## 研究侧结果与忠实导出

每组保存自己实际提供的原生对象或回包、Markdown、真实媒体和状态，逐项格式见[八组输出说明](../docs/pipelines/README.md#管线索引)。允许 HTML/XML/JSON/SDK 等不同载体，不代表八组均返回其中每一种；按共同规则忠实导出研究 Markdown。研究侧 Markdown 允许 GFM/HTML 表格、图像、页码及页眉页脚；它不是 MO-Parse 公开接口的 `result.md`，不适用服务的无表格、多层语义列表和页面清理要求。

读取或导出只转译本方法已有文字、格位、跨度、角色及来源，不补标题、改数字、推断节点连线或修复模型结果。复杂结构不能由 Markdown 完整表达时，保留原始结构供独立评分，不能把导出能力限制误报成原方法不提供，也不能为追求相同语法先把所有结果语义化。

共同条件包括原件字节、标注、前处理、来源许可、忠实导出规则、评分、资源和失败处理。各框架的内部字段可以不同，不要求共同语义模型、完整矢量网格或 MO-Parse 转换器。原始响应已有信息但读取丢失时先修读取；原方法本身缺失的内容和结构如实进入覆盖与质量统计。

主比较核对原件文字、顺序、表格字值与网格、跨度与表头、单位期间原文、跨页内容、图形保全、未知及失败，另报方法实际提供的原生关系能力。未输出语义列表或保留页面家具不算解析格式失败。服务转换、格式和接口一致性另行测试，不能据服务是否完成来决定某组能否进入对照。

当前[表格来源服务](../app/services/table_service.py)、[PDF 表格证据补充](../app/services/pdf_table_evidence_service.py)与[表格语义转换](../app/services/table_semantics_service.py)属于 MO-Parse 已有工程实现，不能作为八组共同出口或准入门槛。后端既有结构与导出后由服务补出的标题、关系分开保存，后者不能覆盖原始解析成绩。MinerU 后不运行独立 Docling 复核，也不按解析器分歧修正结果；跨页缺证时保留完整物理表及未知关系。

运行前按[研究框架](../docs/research/research-framework.md#6-实验执行质量与计时)检查配置、读回及计时能力即可。预先声明的子集可用于执行预检，不能当正式排名；正式对照保留失败、未知和资源不足，不要求八组先达到相同质量。

## 执行前的适配准备

先核实本组完整原生输出及各分支的交接，记录页序、坐标、源格、媒体、页面角色、异常和未提供字段，再确定无损读回与研究导出。下面是代码复用位置，不是已经完成的八组输出或八个服务适配器；MO-Parse 适配逻辑在独立说明中维护，不以最终组装完成作为主比较门槛。

当前研究入口为[moparse_eval](../moparse_eval/README.md)，独立于服务转换。P01/P02已分别显式选择TableFormer V1/V2；P06/P07已分别显式选择Standard/Advanced，并保留完整原生SDK对象。现有[原生worker](../native_worker/server.py)仍保留生产Advanced配置，研究执行器没有以修改显示名称代替实际模型或tier选择。

研究入口直接执行声明的解析工作，不能把现有 `ParserService.parse()` 当作该入口：它还包括来源补充、文档导出、IR、资产与表格语义转换。仅关闭语义开关仍不等于原始解析对照。原生 worker 的 `_parse` 又只覆盖一个分支，现有 `duration_ms` 也有漏项；具体调用与计时位置见[调用与计时边界](../docs/engineering/architecture.md#现有调用与计时字段)。不增加公开模型选择路由，也不以服务最终契约验收作为研究入口准备。

P03/P04使用完整Paddle原生SDK，GPU推理服务与CPU前处理分离；P05使用官方完整GLM SDK配置覆盖全部页；P08使用完整PDF渲染和官方纯视觉SDK的vLLM路径。8组正式对照前确认输入许可、原始结果保存、读取保真和直接处理计时，不要求完成MO-Parse数据表转换、网格排版还原及页面清理。实际解析质量、覆盖与失败由正式比较测量，不能先剔除尚未达标的组。

现有[Compose配置](../docker-compose.yml)可作为模型服务参数参考，但不能直接当作这8个实验配置已经部署。本轮研究按独立冻结配置及[评估任务](evaluation-tasks.md)执行；本文件不启动推理或修改线上管线，工程预检也不构成生产部署验收。
