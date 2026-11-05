# 目录保存输出的定向读回诊断

本记录只读当前已完成score JSON中的canonical expected选段、保存文本结构、来源快照和逐项检索，不重新评分；未读取原PDF、图片或文字层，没有OCR、视觉判断、新推理或服务操作。它是[三层评测](../evaluation-tasks.md#three-layer-evaluation)的软件诊断，不发布分数、排名或完整覆盖结论。

## 证据范围与软件身份

本记录关注`nvidia-meeting-notice-toc-p015-016`与`huawei-management-toc-p014`，重点检查P01、P03、P08原生结果和P07 baseline/current正文。本轮已核对两样本各12组完整记录的软件身份及目录证据状态。记录来自统一16CPU全scope诊断运行已保存的`private/scores/组名/quality800-r1/样本名.json`，其公共入口为`read_expected → compile_expected`、`native_observation或final_observation → read_candidate`及`grade_expected`。本次没有再次调用这些入口，没有改动expected或候选。

本轮证据入口为[当前诊断目录](../runs/lite/diagnosis/three-layer-current/)。两样本各12份最终JSON均已完整写入，已逐份复核的24份记录的`scoring_software_id`均为`21ebba9c70e11bdae557c94cca4686df99e6432228a545d24354c93ec57d6f63`，均无`saved_reader_or_grader_failure`；总分、层分及层分子均为null，`quality_scores_withheld=true`、`publishable=false`。下述原字、来源和检索行为均从本轮文件重新核对，不继承旧软件记录或判断。这里只确认这24份最终记录已写齐并复核。本次未读取根index，也不判定全量运行是否闭合；这只是两个目录样本的局部同版读回诊断，不等于全scope运行或完整语义验收完成。完整运行状态与最终身份以该目录完成后的`index.json`为准。

## NVIDIA：根声明可追溯，Page 17仍因父身份冲突被拒绝

本节以下具体来源、根证明、父身份拒绝及L检索行为均已按本轮完整记录重核。重点组两个根条目和Director条目的标题、页码及Page头，还逐项核对了同份记录保存的`text_evidence.candidate_projection.source_cells`或`source_fragments`原字快照及实际来源，未只以目录对象自身声明为证据。

选段为canonical `complex-nvidia-2025-annual/expected.md` L361-390和L392-441，目录标题在L392。`directory_evidence.required`保留目录原字及其来源；根条目DEFINITIONS（L394，Page 3）与PROXY STATEMENT（L397，Page 12）的`root_evidence`为`flat_text_entry_schema`，来自实际目录标题及本条明确Page标签。Director Qualifications and Nomination of Directors（L400，Page 17）的必需父链则来自L397的PROXY STATEMENT与L399的Proposal 1—Election of Directors实际parent引用，`parentage=explicit`。

目标五组均保留46个候选Page对象；这仅说明有非空读回，不证明完整覆盖。候选目录为平面Title/Page表达，所查根条目和Director条目均为`parentage=explicit`、`parent_path=[]`，各有`flat_title_page_schema`根证据；不再使用unknown空列表代替根证明。实际目录与Page声明来源如下，网格行列为零起点。

| 组 | 候选自己的目录与Page声明 | Director Page 17实际源 |
| --- | --- | --- |
| P01 | 目录`#/documents/0/document/texts/22`；同表`data/table_cells/1`的Page头；保留native document-index声明 | `#/documents/0/document/tables/0/data/table_cells/15`，row7/col1 |
| P03 | 目录`#/pages/1/raw/res/parsing_res_list/0`，原文`NVIDIA Corporation`与`Table of Contents`之间的换行保留；同表`cell[1]`的Page头 | `#/pages/1/raw/res/parsing_res_list/1/block_content::html/cell[15]`，row7/col1 |
| P08 | 目录`#/pages/1/raw/1`；独立Page声明`#/pages/1/raw/2` | `#/pages/1/raw/3/content::html/cell[13]`，row6/col1 |
| P07 baseline | `final.md` L49的Table of Contents与L51的Page声明；表范围L61-108 | `markdown:L61/gfm/rows/7/cells/1`，row7/col1 |
| P07 current | 与baseline相同的打印声明、表范围及来源位置 | `markdown:L61/gfm/rows/7/cells/1`，row7/col1 |

DEFINITIONS与PROXY STATEMENT的本轮逐项B判断为correct，其候选根身份有上述实际证据；这不是两样本或任一组的发布结论。Director查询只含完整title、attribute=`Page`、空scope、空qualifiers及必需`toc_parent=['PROXY STATEMENT','Proposal 1—Election of Directors']`，没有Page正确值17。同名候选的subject、attribute、上下文、scope和qualifiers检查均满足，只有实际`toc_parent=[]`与必需父链冲突；检索记录为`decision=rejected`、`reason=required_identity_missing_or_explicit_conflict`、`conflicting_dimensions=['identity_facets']`，该项B为incorrect。对应`toc_entry_page`及`toc_parent`关系也没有选中候选。页码已经识别，缺口是必需目录父关系，不能借同名或正确页码补父。

P01还存在独立文字缺陷：`table_cells/92`的标题实际为`PPENDIX A—Amended and Restated Certificate of Incorporatio`，而`table_cells/93`确有`A-1`。完整APPENDIX标题没有同名候选，不能凭A-1补字。P03的`cell[92]/cell[93]`、P08的`cell[90]/cell[91]`、P07两版GFM row46的col0/col1保留完整APPENDIX标题与A-1。两版P07的所查目录事实、平面根证据及Director父身份拒绝原因一致，不能把reader修复算作交付正文优化收益。

## 华为：文字保留，Page与目录父级仍待软件解释

本节目录对象、blockers、pending、撤分状态及下表原字来源均已按本轮12组完整记录重核。

选段为canonical `complex-huawei-2024-annual/expected.md` L382-403。L384为`13 愿景、使命与战略`；L387的`16 运营商市场`与L388的`21 政府和企业市场`明确嵌在L386的`16 ICT基础设施业务`之下；L401为根条目`62 财务风险管理`。这些expected内容仍是待解释范围，不能因尚未编译Page要求而退出。

| 组 | 当前score的候选原字快照与源 |
| --- | --- |
| P01 | `#/pages/0/raw/json_result/0/1`的block_lines 1、7、9、35分别保留上述四项，政府条目前缀为`21、` |
| P03 | `#/pages/0/raw/res/parsing_res_list/1`的block_lines 1-8和10-19保留对应条目，政府条目前缀为`21 ` |
| P08 | `#/pages/0/raw/1`、`/5`、`/6`、`/20`分别保留上述四项 |
| P07 baseline/current | `final.md` L5、11、13、39分别保留上述四项，含`21、政府和企业市场`；两版所查表达与来源行号一致 |

12组的`directory_evidence.required`与`.candidate`均为null，B层尚未建立Page要求或事实。候选自己的打印文字没有本次已支持的目录标题、Page轴或明确document-index schema；任务标签、数字前缀及expected父树没有用来填入候选角色。T层`source_fragments`仍保留上述原字及来源；expected L384等位置仍有`unclassified_business_prose`，L387-391仍有`list_group_scope_interpretation_unsupported`。这属于读取软件尚未解释完整业务表达，不能记为零题通过、候选零分或目录父级已保留。

这里的“待解释”由blockers明确保留；序列化的`pending_requirements.expected`及`.candidate`实际均为空，不能声称已经列出完整Page待判题。12组均无`saved_reader_or_grader_failure`；各组`quality_scores_withheld=true`、`publishable=false`，总分、层分及层分子均为null。修复该解释范围后须统一重跑，不能删除这些expected内容或只用已有L关系代替完整目录验收。

## 修复边界与发布门禁

[独立父身份回归](../../tests/unit/test_toc_parentage_contract.py)固定了根目录引用、命名父引用、明确平面文字和Title/Page schema的跨表示正例，以及破损父引用负例。未证明的父身份保留为`toc_parent=None`；缺失或冲突的显式父引用是候选歧义，不能回退平面根身份。Parent列已声明却留空仍是unknown；普通文字的`native_parent`与缺失目标同值不证明结构容器，只有SDK明确body路径或显式结构容器角色可以排除非业务父对象。明确存在但reader未支持的嵌套header引用仍保留原格及软件阻塞。

NVIDIA本轮目标五组没有`toc_*`软件阻塞；目录外的Items of business列表父范围、条件分支及谓词等仍有软件阻塞和pending。华为本轮仍有上述目录解释缺口。因此本记录只记录限定范围的软件读回行为，不据此发布任何组的成绩，也不以Page对象数量、软件测试数量或空pending数组证明完成。
