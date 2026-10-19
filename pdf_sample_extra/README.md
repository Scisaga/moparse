# 额外 PDF 样本

**状态：暂不处理。** 本目录集中保存历史工作额外引入的六份公开 PDF 原件，共 46 页。解析预期结果与语料的生成已在其他项目开展，原本地样本目录已删除；本目录不作为替代语料，不纳入解析、评测、调优、预热、回归验收或上线决策，不继续为这些样本增加复核、模型兜底或特定内容修补。只有用户明确恢复这些样本的工作后，才重新确定处理范围。

原件从现存服务任务的输入副本复制，已逐件核对 SHA256 和物理页数，未重新下载、转换或调用解析模型。历史任务输入副本保留，避免破坏任务记录和结果。PDF 与原有样本目录一样仅保存在本地，不进入 Git 和 Docker 构建上下文；本说明保留来源身份，不恢复已删除的评测报告、标注或工具。

| 文件 | 页数 | 原始来源 | 状态 |
| --- | ---: | --- | --- |
| [irs-form1040-2025.pdf](irs-form1040-2025.pdf) | 2 | [IRS](https://www.irs.gov/pub/irs-prior/f1040--2025.pdf) | 暂不处理 |
| [census-samoa-1930.pdf](census-samoa-1930.pdf) | 12 | [Census](https://www2.census.gov/library/publications/decennial/1930/bulletins/demographics/population-agriculture-american-samoa.pdf) | 暂不处理 |
| [nist-tn2354.pdf](nist-tn2354.pdf) | 25 | [NIST](https://nvlpubs.nist.gov/nistpubs/TechnicalNotes/NIST.TN.2354.pdf) | 暂不处理 |
| [nasa-maax-factsheet.pdf](nasa-maax-factsheet.pdf) | 2 | [NASA](https://science.nasa.gov/wp-content/uploads/2023/11/maax-submitted-dec7-2022-factsheet.pdf) | 暂不处理 |
| [gsa-sf95-2007.pdf](gsa-sf95-2007.pdf) | 2 | [GSA](https://www.gsa.gov/system/files/SF95-07a.pdf) | 暂不处理 |
| [nara-telegram-32171186.pdf](nara-telegram-32171186.pdf) | 3 | [NARA](https://www.archives.gov/files/research/jfk/releases/2021/docid-32171186.pdf) | 暂不处理 |

| 文件 | SHA256 |
| --- | --- |
| `irs-form1040-2025.pdf` | `3d31c226df0d189ced80e039d01cf0f8820c1019681a0f0ca6264de277b7e982` |
| `census-samoa-1930.pdf` | `4ebad09d258f11e8d4e04c3f5f0af1493d0622672209a71bb175f7f0fc4ac77d` |
| `nist-tn2354.pdf` | `171dec979423da69147527794a29d056e8e0751fe7d20d32484e402d39b4dcff` |
| `nasa-maax-factsheet.pdf` | `79ab8e7686605ece7144aaa7d1d95e0c43dc4066ad35db9629f7b10075369411` |
| `gsa-sf95-2007.pdf` | `7c58078520934a0dc2c28ec9e59064548a38df3ac26f63c6a7d83a3280c9afe4` |
| `nara-telegram-32171186.pdf` | `adbe2f9e5428734c3ab259353afac28a971d2d89bfa871ac21c7858b7c317fc4` |

这些原件已用于历史开发，不属于新的未见测试集。公开来源链接不额外授予材料再分发许可；历史固定 Office 转换 PDF 也不自动纳入后续外部交接语料的处理范围，不为此重新生成转换件。
