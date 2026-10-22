# MO-Parse 部署入口

具体配置、模型准备、启动、检查和回退统一维护在[运行手册](runtime-recipes.md)，本页用于选择入口。

## 安装前提

- Docker Engine 和支持当前 Compose 规范的 Compose 插件；使用 NVIDIA 模型服务时安装 NVIDIA Container Toolkit。
- CPU Docling 建议至少准备 8 GiB 内存，实际容量由文档与并发决定；MinerU worker 和模型服务的独立配额见[服务与配置](runtime-recipes.md#2-服务与配置)。
- 模型可联网准备，或已将完整文件和缓存交接到目标卷；MinerU 下载器按锁校验，GLM 离线准备另见[模型准备](runtime-recipes.md#3-首次准备)。

## 按任务进入

| 任务 | 文档入口 |
| --- | --- |
| 选择 CPU、内置模型或远程服务 | [运行模式](runtime-recipes.md#1-选择运行模式) |
| 配置进程、端口、GPU、资源与数据卷 | [服务与配置](runtime-recipes.md#2-服务与配置) |
| 构建镜像、准备与核验模型 | [首次准备](runtime-recipes.md#3-首次准备) |
| 启动 Compose 或源码环境 | [启动](runtime-recipes.md#4-启动) |
| 检查、升级、回退或排查故障 | [运行维护](runtime-recipes.md#5-检查升级与故障定位) |
| 了解最终内容和输出包的要求及实现差距 | [输出规范](../specs/moparse-output-spec.md) |

研究配置及运行条件由[待测管线](../../benchmark/pipelines-to-test.md)维护；服务部署模式与八组研究配置分别核实。全部文档入口见[文档导航](../README.md)。
