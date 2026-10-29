# MinerU执行层审计的软件源码快照

这些文件仅用于复现执行层源码检查与CPU合成探针，不包含语料、模型权重或解析答案。来源及软件摘要见[sources.json](sources.json)；摘要只用于软件来源留档，不用于语料复核或验收。

vLLM文件来自官方v0.19.1固定tag；mineru-vl-utils文件来自已检查METADATA为2.0.7的本地分发缓存，upstream main链接只提供导航，不能当成固定版本字节身份。原文件保持原样，SDK许可证随快照保存。

2026-10-27补存正式worker镜像中2.0.7的[json2markdown.py](mineru_vl_utils/post_process/json2markdown.py)，用于核对标题类型与官方导出的区别。它只拼接content并处理merge_prev，不按type添加标题层级；软件来源记账列在同一sources.json中。

返回[执行层诊断](../../README.md)。本目录的Qwen2 decoder、RoPE factory及SDK响应方法源码用于静态检查与受控返回验证，不加载模型或发出推理请求。
