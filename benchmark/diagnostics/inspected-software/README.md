# 受控诊断的软件源码

这里只保存复现软件缺陷所需的源码，不包含原件、参考、标注、模型权重、旧页面输出或比较成绩。[Paddle来源](paddle/sources.json)记录固定镜像中的有效软件文件；[MinerU来源](mineru/sources.json)区分官方固定vLLM与安装版SDK。摘要仅标识软件字节，不用于语料验收。

[Paddle颜色探针](../paddle-color-probe.py)和[MinerU边界探针](../mineru-boundary-probe.py)读取相对源码快照，不发出推理请求。共同执行器及导出探针还导入当前项目代码；修复后须记录新代码身份并重新解释探针结果，不依旧结果声称当前版本行为。
