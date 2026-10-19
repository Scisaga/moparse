# 待比较的8条完整解析管线

本文件定义下一轮主对比的8个固定配置，不记录历史成绩，不预先选择优胜方法。数据集、测试任务和评分要求见[评估任务](evaluation-tasks.md)；MinerU内部参数研究见[MinerU调优](mineru-tuning.md)，不增加本表的主比较组数。

本表定义[研究顺序](../docs/research-framework.md#2-管线研究的顺序)第 3 步的固定配置，用于第 4 步执行和第 5 步分析。比较对象是各管线本身的解析结果与处理成本，不要求直接满足 MO-Parse 接口最终语义格式。服务接入与转换另见[技术路线](../docs/technical-route.md)；新增路由由比较后的类别差异决定。

## 主比较配置

| 编号 | 完整管线 | 原生PDF页 | 扫描页与混合页 | 必须固定的区别 |
| --- | --- | --- | --- | --- |
| P01 | Docling 2.139.0 TableFormer V1 + GLM-OCR SDK | CPU Docling；V1；accurate；matching=False；PyPdfium；原生OCR关闭 | GLM-OCR SDK | 与P02只改变TableFormer模型版本 |
| P02 | Docling 2.139.0 TableFormer V2 + GLM-OCR SDK | CPU Docling；V2；accurate；matching=False；PyPdfium；原生OCR关闭 | 与P01相同的GLM-OCR SDK | 与P01保持相同Docling包、布局模型、后端、线程及其他参数 |
| P03 | 全页PaddleOCR-VL 1.5 | PaddleOCR-VL 1.5自身完整解析 | 同一PaddleOCR-VL 1.5自身完整解析 | 所有页均由本模型完成，不调用GLM替代扫描页 |
| P04 | 全页PaddleOCR-VL 1.6 | PaddleOCR-VL 1.6自身完整解析 | 同一PaddleOCR-VL 1.6自身完整解析 | 与P03使用同一方向前处理、渲染、输出适配和资源预算 |
| P05 | 全页GLM-OCR SDK | GLM-OCR SDK自身布局与识别 | 同一GLM-OCR SDK | 所有页走SDK，不保留原生解析器旁路 |
| P06 | MinerU 4.0.12 Standard + TXT + GLM-OCR SDK | `tier=standard`、`ocr_mode=txt`、`image_analysis=False` | 与P01、P02、P07相同的GLM-OCR SDK | 与P07只改变MinerU的tier |
| P07 | MinerU 4.0.12 Advanced + TXT + GLM-OCR SDK | `tier=advanced`、`ocr_mode=txt`、`image_analysis=False` | 与P01、P02、P06相同的GLM-OCR SDK | 保留PDF原文字层，不能静默改成纯视觉 |
| P08 | MinerU纯视觉全页vLLM | PDF渲染为页面图像，再由官方纯视觉SDK完成提取与Markdown转换 | 同一纯视觉路径 | 所有页使用图像输入；不读取PDF原字层补字，不调用GLM |

P03与P04的1.5和1.6指PaddleOCR-VL模型版本，不是PaddleOCR Python包版本。P06与P07的4.0.12是MinerU解析软件版本；下面的MinerU2.5-Pro是其调用的视觉模型身份。P08只比较vLLM执行器，不额外引入Transformers组。

## 相同输入、方向前处理与页面路由

输入使用外部项目交接并明确纳入本轮的同一版完整 PDF 与独立标注，交接要求见[评测任务](evaluation-tasks.md#外部语料与预期结果交接)；`pdf_sample_extra/` 的六份额外原件暂不处理，也不用于预热或回归。每条管线接收同一份完整原件，禁止根据金标或某个解析器的输出筛选页面。原件人工来源类别只用于独立分层和评分；运行时使用预先冻结的共同自动来源判断，记录其预测及误路由，不能用人工标签免费路由。统一前处理记录原件 SHA、页数、自动来源判断与方向变换，形成共享页清单；P01、P02、P06、P07按此清单路由，原生页进入本组原生解析器，扫描和混合页进入同一GLM SDK。无法分类的页须先按统一规则解决或明确记录unknown，不能让各方法自行挑选有利页面。

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

| 对象 | 固定要求 | 运行前需要完成的准备 |
| --- | --- | --- |
| Docling | Python包`docling==2.139.0`；P01和P02仅TableFormer V1/V2不同 | 显式选择模型类与模型目录，分别冻结V1/V2权重、布局模型、配置和SHA；`fast/accurate`不能代替V1/V2模型选择 |
| MinerU | `mineru==4.0.12`；Standard、Advanced共享同一小模型集合与依赖锁 | 使用保留的[小模型与视觉权重锁](../native_worker/models.lock.json)，固定实际wheel、镜像和转换补丁SHA |
| MinerU视觉模型 | `opendatalab/MinerU2.5-Pro-2605-1.2B`；revision `08aaea840498d49ce16247b6263196cf02814885`；FP16 | P06、P07、P08共用这一权重及服务别名`mineru2.5-pro`，核对实际文件SHA和处理器配置 |
| GLM-OCR | P01、P02、P05、P06、P07使用完全相同的`zai-org/GLM-OCR`权重、SDK布局模型和解码配置 | 先读取实际模型缓存，冻结不可变revision、权重SHA、SDK代码版本及布局模型身份；不能用浮动仓库名冒充已冻结revision |
| PaddleOCR-VL | P03固定模型1.5，P04固定模型1.6；统一FP16及方向处理 | 分别冻结实际模型仓库、revision、权重与处理器SHA，固定PaddleOCR包及推理后端版本；不能从显示名称推断权重已相同或已锁定 |
| 结果读取与导出 | 固定各组读取代码及共同忠实 Markdown 导出规则，保留原始输出 | 记录构建镜像SHA、依赖、实际启动命令与完整配置；不在导出中加入 MO-Parse 语义转换或修正答案 |

GLM与Paddle权重revision目前属于待准备项，本文件不填未经读取确认的commit。准备完成后把实际身份记入执行配置，再开始测量；本文件中的待准备状态不算已完成实验。

## 公平资源与执行参数

8组使用同一型号、同一功率上限的GPU，默认单张RTX 2080 Ti、200 W；一次只运行一条受测管线。CPU前处理、布局分析、PDF解析与SDK的CPU工作合计限定8 CPU、8 GiB宿主内存；GPU推理服务的宿主CPU合计限定4 CPU、宿主内存合计20 GiB。CPU配额和affinity分别记录，不能把8 CPU配额描述成独占8个物理核。

混合管线中的MinerU与GLM必须共享同一个GPU资源预算，不能为每个后端暗加一张卡。运行前锁定实际GPU实例、统一的总显存预算和同时驻留策略，所有GPU后端合计核验显存峰值；正式文档处理中由路由触发的必要卸载或模型切换计入处理耗时；进程首次初始化与预热单列。若某组无法在同预算内运行，记录无法完成及原因，不静默增加资源或换模型。

完整原件串行提交，外层并发1；每个推理后端的客户端请求并发上限4，服务端`max_num_seqs=4`或等价调度上限4。CPU数值库及ORT统一intra_op=8、inter_op=1，Docling页面worker=1、num_threads=8。某框架不暴露等价参数时须记录其实际调度方式，先核对总资源约束，不能把“无此参数”写成相同设置。

MinerU VLM固定FP16、上下文8192、`max_num_batched_tokens=2048`、KV cache `134217728`字节、`max_num_seqs=4`；使用`MinerULogitsProcessor`。P06/P07客户端`VlmConfig.max_concurrency=4`，P08纯视觉SDK请求并发同为4；输出长度上限、停止条件、图像缩放和失败截断状态在执行配置中显式保存。

所有支持CUDA Graphs且能在资源预算内运行的GPU后端必须启用，并用真实捕获及推理日志核实。MinerU使用compile mode=0、`FULL_DECODE_ONLY`、capture sizes `[1,2,3,4]`、maximum capture size=4；torch.compile与CUDA Graphs分别记录。GLM及Paddle先核实实际后端支持和捕获配置，不能因为尚未测试就默认eager；确有失败或超预算时保留原始错误、例外原因与恢复条件。

预热与正式测量分开记录，8组使用相同预热原件、次数和冷热缓存定义。主耗时在 worker 内部用单调时钟直接测量，从开始处理完整 PDF 到原始解析、研究侧忠实 Markdown 和必要资产就绪；包含公共前处理、路由、PDF 渲染、全部解析推理、必要模型切换和声明的结果导出。不包含 MO-Parse 的表格语义化、图形关系补充、页面家具清理、服务正文组装，也不包含 HTTP、接口排队、轮询、下载及纯持久化。不能减常数估算或累加重叠阶段；P08 不能从已渲染图像开始计时。共同超时、取消清理与重试规则预先固定。

## 研究侧结果与忠实导出

每组保留其原始 Markdown、HTML、XML、JSON、SDK 结构及媒体引用，按共同规则导出便于保存和比较的 Markdown。研究侧 Markdown 允许 GFM/HTML 表格、图像、页码及页眉页脚；它不是 MO-Parse 公开接口的 `result.md`，不适用服务的无表格、多层语义列表和页面清理要求。

读取或导出只转译本方法已有文字、格位、跨度、角色及来源，不补标题、改数字、推断节点连线或修复模型结果。复杂结构不能由 Markdown 完整表达时，保留原始结构供独立评分，不能把导出能力限制误报成原方法不提供，也不能为追求相同语法先把所有结果语义化。

共同条件包括原件字节、标注、前处理、来源许可、忠实导出规则、评分、资源和失败处理。各框架的内部字段可以不同，不要求共同语义模型、完整矢量网格或 MO-Parse 转换器。原始响应已有信息但读取丢失时先修读取；原方法本身缺失的内容和结构如实进入覆盖与质量统计。

主比较核对原件文字、顺序、表格字值与网格、跨度与表头、单位期间原文、跨页内容、图形保全、未知及失败，另报方法实际提供的原生关系能力。未输出语义列表或保留页面家具不算解析格式失败。服务转换、格式和接口一致性另行测试，不能据服务是否完成来决定某组能否进入对照。

当前[表格来源服务](../app/services/table_service.py)、[PDF 表格证据补充](../app/services/pdf_table_evidence_service.py)与[表格语义转换](../app/services/table_semantics_service.py)属于 MO-Parse 已有工程实现，不能作为八组共同出口或准入门槛。后端既有结构与导出后由服务补出的标题、关系分开保存，后者不能覆盖原始解析成绩。MinerU 后不运行独立 Docling 复核，也不按解析器分歧修正结果；跨页缺证时保留完整物理表及未知关系。

运行前按[研究框架](../docs/research-framework.md#6-实验执行质量与计时)检查配置、读回及计时能力即可。预先声明的子集可用于执行预检，不能当正式排名；正式对照保留失败、未知和资源不足，不要求八组先达到相同质量。

## 执行前的适配准备

P01可从[现有Docling适配器](../app/parsers/docling_standard.py)和[解析路由](../app/services/parser_service.py)建立实验入口；P02需要增加明确的TableFormer V2选择，并证明除模型版本外其他参数一致。P06/P07可复用[原生worker](../native_worker/server.py)的`parse_async`与`VlmConfig`接法，但当前worker把tier写为advanced，P06仍需显式Standard选择，不能只改显示名称。

正式研究需要准备直接执行声明解析工作的入口，目前尚不能把现有 `ParserService.parse()` 当作该入口：它还包括来源补充、文档导出、IR、资产与表格语义转换。仅关闭语义开关仍不等于原始解析对照。原生 worker 的 `_parse` 又只覆盖一个分支，现有 `duration_ms` 也有漏项；具体调用与计时位置见[技术路线](../docs/technical-route.md#61-现有调用与计时字段)。不增加公开模型选择路由，也不以服务最终契约验收作为研究入口准备。

P03/P04需要完整的Paddle页面执行器、统一方向控制、原始输出留存和忠实导出；P05需要让[现有GLM SDK客户端](../app/parsers/glm_sdk_remote.py)覆盖全部页；P08需要完整PDF渲染、官方纯视觉SDK的vLLM入口和结果读取。8组正式对照前检查输入许可、原始结果保存、读取保真和处理计时，不要求完成 MO-Parse 表格/图形转换及页面清理。实际解析质量、覆盖与失败由正式比较测量，不能先剔除尚未达标的组。

现有[Compose配置](../docker-compose.yml)可作为模型服务参数参考，但不能直接当作这8个实验配置已经部署。应先补齐上述模型锁、资源隔离、统一前处理和适配器，再按[评估任务](evaluation-tasks.md)执行；本文件只定义待跑配置，不启动推理或修改线上管线。
