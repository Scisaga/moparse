# P08：MinerU 全页纯视觉 SDK + vLLM

[全部管线](README.md) · [固定比较条件](../../benchmark/pipelines-to-test.md#主比较配置)

## 1. 配置与执行边界

全部 PDF 页面渲染成图像，经官方纯视觉 SDK 的 vLLM 路径处理；不读取原生文字层，不接 GLM 或其他解析器。

软件和模型锁、共同前处理、来源权限及资源预算由[待测管线](../../benchmark/pipelines-to-test.md)统一维护；本页说明该配置的输出与适配，不另设实验参数。

## 2. 原生输出

全部输入页面图像的纯视觉 `ExtractResult`/`ContentBlock` 序列、该 SDK 的 Markdown 转换结果、必要图片与页清单。它没有 PDF-native `ParseResult.pages`，也没有自动生成的完整 PDF 页身份与输出包。

### 2.1 MinerU 纯视觉 SDK 结果

核对了安装的 `mineru_vl_utils` 2.0.7 的 `mineru_client.py`、`structs.py` 和 `post_process/json2markdown.py`，对照[官方纯视觉 SDK](https://github.com/opendatalab/mineru-vl-utils)。该版本仅为可检查的实现依据；P08 的实际执行锁仍需确定。

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

P08 的必要裁图只能使用本组输入页面图像及 SDK 区域，保存裁图方式并计入完整管线处理成本，不能读取原生字层、矢量文字或另一解析器补答案。服务需要的区域关系仍须按来源证据判断，不能将 P06/P07 的 PDF-native 结构套到这种平面块列表上。

## 3. 研究侧读取与导出

固定 SDK 和 vLLM 入口，逐页保存块序列、空内容、现有分数与阶段失败。调用官方完整布局和识别路径，并保存 Markdown 转换所用数据；不能把 OpenAI 接口的一段最终文本当作本组完成的全页 SDK 结果。

## 4. MO-Parse 适配逻辑

1. 用输入图像清单绑定物理页、尺寸和方向变换，保留块的 `type`、bbox、角度、顺序和延续观测。
2. 表格按实际 HTML/Markdown 内容读取；缺少源格或角色证据时保持未知，布局区域不自动成为语义数据表。
3. 原生图片字节若未提供，按本组页面图像和 SDK 区域裁出必要资产；保留图题与图片原位引用，不调用原生文字层、GLM 或第二解析器。
4. 将已确认内容交给服务转换和组装，保留未检测、识别缺失和结构未知。`json2md` 没有输出某图片块的文字，不能被解释为该图不存在。

## 5. 实现状态与验证项

仓库尚无完整 P08 执行器或服务适配器。需验证块到页、Markdown 到图片的关联、纯视觉来源许可、空块和失败保全；核对 SDK 的默认重试与图像分析选项，不能隐式启动图片语义化或对执行未知请求再次提交。

## 6. 格式核对依据

格式依据沿用 2026-10-21 的静态核对：`mineru_vl_utils==2.0.7`，P08 实际执行锁待确认。上述结构为类型与字段示意，完整配置的实际输出样本及适配验收状态见第 5 节。

实现参考：[MinerU SDK 依赖参考](../../docker/mineru-vllm/requirements.txt)。官方格式与源码链接在本页相应分支说明中列出。

以下为已核对源码文件的 SHA256，用于复查格式依据；模型权重及运行身份另行固定。

| 安装包源码文件 | SHA256 |
| --- | --- |
| `mineru_vl_utils 2.0.7: structs.py` | `61163066b9084e25f7ef24d55bda2bbcd5d823aabc7c909d7c513284acd59fcf` |
| `mineru_vl_utils 2.0.7: post_process/json2markdown.py` | `1b16b29f789a3b3d8e7bf638a573ecb52623be6304a289fc80c0f6ce97188bd2` |
