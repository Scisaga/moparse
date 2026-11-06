# moparse-dataset-v1-preflight

本目录包含独立运行所需的输入PDF、现有参考与图片副本、manifest和评分索引。运行路径以本包manifest为准；原参考manifest及处理说明按历史字节保留，其中编辑工作区导航不作为运行路径。

制作状态：preflight_only。包装只执行人工清单，没有机械复核或验收语料。Full不因复制完成而成为新验收Gold；未知与历史复核范围以参考记录为准。

评分程序只读冻结且目视确认的参考，不能用于检查或改写语料。评分协议由MO-Parse的benchmark/evaluation-tasks.md维护；本包不复制其规则。

命令：`python -m moparse_eval run --dataset <本目录> --suite lite`；Full本轮不启动推理。未冻结的Lite不能形成正式对照。

原件来源与许可沿用原资料声明；本地打包不提供新的再分发许可。
