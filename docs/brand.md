# MO-Parse 品牌与界面

正式展示名称为 **MO-Parse**。项目探索消费级 GPU 与 CPU 上的高质量文档内容解析，主标志以一个蓝青色立式文档终端表达本地、亲切和可掌握的工具体验。

## 主标志

![MO-Parse 蓝青色立式文档终端](../assets/moparse-logo-1024.png?v=mo-parse-terminal-20261019-2)

主标志采用立式伙伴款：蓝青色机身、浅色屏幕上的小眼睛与克制笑容、顶部文档、单个琥珀色按钮，以及松弛细长的手脚。屏幕与机身构成一个整体，没有独立头部。透明 PNG 母版保存在 [assets/moparse-logo-3d-master.png](../assets/moparse-logo-3d-master.png)，沿用历史文件名以保持资源路径兼容。README 与网页主标志从该母版导出，保持原始构图比例；生成提示与素材来源见 [brand-generation.json](../assets/brand-generation.json)。

## 小尺寸图标

Favicon 使用独立的透明 PNG 母版 [assets/moparse-favicon-master.png](../assets/moparse-favicon-master.png)。它保留文档终端的蓝青机身、浅屏表情与顶部纸页，改为正面视图，去掉四肢并减少纸面细节，以高对比和清楚轮廓适配 16、32、48、64 像素。Favicon 从这张简化母版独立导出，Apple Touch Icon 使用同一简化造型导出为 180×180；主标志不直接缩小为 favicon。

## 同源界面空态

输入、Markdown 输出、纯文本、页面、加载、说明和错误七种空态均复用主标志母版中的立式文档终端，搭配纸页、表格与状态符号表达场景。SVG 将主标志 PNG 内嵌为数据，不依赖外部图片请求，并同步导出 PNG 兼容资产。主界面的空态与页头、README 使用同一个角色，不再使用旧的独立头部、圆三角机身与三脚支撑造型。

主标志的蓝青机身、浅色屏幕与琥珀色按钮以母版中的渲染光影和渐变为准。场景装饰与应用原有的就绪、错误等状态颜色分别处理，保留状态语义。

## 一致导出

在项目开发环境中运行以下命令，从主标志 PNG 母版生成根目录、README 与前端使用的 PNG 标志及七种同源空态，从独立 favicon 母版生成 16、32、48、64 像素图标及 180 像素 Apple Touch Icon。导出保持透明度与图形比例。

根目录仅保留 `logo.png` 这一张图片。Favicon 与 Apple Touch Icon 的项目导出文件统一放在 `assets/icons/`，前端使用的副本保存在 `frontend/public/`；母版、候选图与文档截图继续保存在各自的资源子目录中。

```bash
.venv/bin/python scripts/export_brand_assets.py
```

空态场景画布保留 640×512 的尺寸，使用自包含 SVG 将同源角色与场景元素组合；生成程序与母版共同决定最终资产。

原有 `moparse` 包名、仓库路径、配置标识、浏览器存储键和公共 API 保持兼容；资源文件仍使用 `moparse-logo` 前缀。维护中的展示文案使用 MO-Parse，历史实验、模型名称及冻结证据保持原名。

## 首页视觉

首页顶部使用深蓝底色、细线纸页、表格网格与结构连线，替换旧随机马赛克画布。背景为静态装饰 SVG，不接收指针事件、不进入辅助技术阅读顺序、不依赖 Canvas、随机数或动画；窄手机屏幕隐藏装饰并将操作图标排列为一行，避免占用正文空间。服务就绪、不可用、未知与检查中的状态语义及操作逻辑保持独立。

README 使用桌面截图，本页同时展示桌面和手机截图，分别按 1440×1060 与 390×1285 像素采集。截图脚本直接打开已部署的真实页面，在干净的浏览器上下文中等待服务状态、字体与图片加载完成；不替换 API 响应，不创建解析任务。画面中的服务状态反映采集时的实际响应，不代表持续可用性。

采集脚本为 [scripts/capture_brand_screenshots.mjs](../scripts/capture_brand_screenshots.mjs)。准备可用的 `playwright-core` 模块与 Chromium 后，用环境变量指定其路径并运行；脚本默认将两张截图写入 `docs/assets`，同时输出采集地址、浏览器版本、图像来源与文件 SHA-256。应先更新真实服务的静态资源，再重新采集。

```bash
PLAYWRIGHT_MODULE=/path/to/playwright-core/index.mjs \
CHROMIUM_EXECUTABLE=/path/to/chromium \
node scripts/capture_brand_screenshots.mjs --base-url http://127.0.0.1:12303/
```

![桌面首页](assets/mo-parse-web-desktop.png?v=mo-parse-terminal-20261019-2)

![手机首页](assets/mo-parse-web-mobile.png?v=mo-parse-terminal-20261019-2)
