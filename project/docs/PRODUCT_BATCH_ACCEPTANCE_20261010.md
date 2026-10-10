# 一张照片、多种灯光：本地产品接入验收

2026-10-10，本轮只做本地代码、历史真实结果登记及浏览器验收。未连接云机、上传、开机、运行 GPU、重算 inverse/forward、安装依赖、修改认证或守护；未提交、推送、部署或清理历史。

## 正式登记与真实数据

任务 `73edd6656f9e47db85578d93e42c1e8b` 已通过新增 CLI 登记流程原子进入原有 `project/.tasks`，没有手改任务成功状态，未覆盖旧任务。原 run 为 `cdbca2ab59bb44e39537d8d14f2d3552`，inverse 来源任务 `6d541112fa164c099d9fc06c560b464d` / run `dc011af5186c492d8ffd2f6342e5c07f`。登记不声称本轮生成；页面明确标注“已登记历史真实结果”。

|预设|原实际生成时间（北京时间）|JPEG SHA256|
|---|---|---|
|sunny / 晴日公园|2026-10-10 11:07:34|`4fa20f6f9926e83a4321d1a3d7a3987a4d2fb8277cd6e5fa6300fdb4437f44e6`|
|sunrise / 粉色晨光|2026-10-10 11:07:40|`23474183ce2dea7df9a2fcfbf40072089708f64e69d9948098b6ebed20e69e18`|

核对了实际输入字节/配置/任务nonce、run归档SHA256及归档request、launch目标run、catalog HDR/index/hash、inverse五通道与来源、每项原子完成标记、输出尺寸/解码/非恒定/哈希。输出都是1280×704。历史来源与manifest文件哈希再次核对未变，原测速报告与原始回执保留。

正式入口（只接受 workspace/.local 下相对目录，不提供 HTTP 登记或任意路径接口）：

```powershell
.local/review-venv/Scripts/python.exe -X utf8 -B scripts/register_lighttry_results.py --job reuse-benchmark-20261010-retry1/private-job --run cdbca2ab59bb44e39537d8d14f2d3552 --original-task 6d541112fa164c099d9fc06c560b464d
```

真实任务重复登记已实际运行成功，保留原 registeredAt 和 expiresAt；隔离测试另覆盖同身份不同内容/生成来源冲突拒绝、错误预设/配置/run、损坏/缺文件、尺寸/常量输出、路径越界。先验证 staging 再原子发布，不覆盖已有身份。阶段成功项和失败/pending项分别登记；整体失败没有整批receipt时仍可凭已停止事件和完整阶段证据保留成功项。

## 产品路径与行为

使用现有 TaskStore 和任务接口，新增 presets、presetResults，以及 partial 终态；旧 preset/result 和旧单预设请求兼容。每项状态、结果、错误、真实生成时间与来源独立。新增受限 `/api/tasks/<task>/presets/<preset>/{result,download,result-region,download-region}`，未知预设或种类不能读取文件，不能使其他成功项失效。

上方灯光按钮仅切换查看；另有1–3种勾选准备。生成按钮一次 POST 一份presetIds列表，服务端去重并调用 executor.submit 一次，request.json 的列表经真实 build_bundle 校验贯通至现有 driver/worker/batch。运行中的勾选和提交锁定，查看可以切换；重复requestId避免重复执行。部分失败保留已完成项，无自动收费重试。默认未连接仍禁用真实提交，选择/刷新不启动推理或资源。

当前只能整批结束后取回并发布结果。整批forward状态不推断成每项都在生成；取回前各项等待完成记录。不新增流式传输，不称浏览器已实现5.97秒新灯光交互出图，不支持长期模型常驻。

## 实际本机浏览器验收

生产本地服务默认未连接，地址 [真实已登记任务](http://127.0.0.1:8773/?task=73edd6656f9e47db85578d93e42c1e8b)。真实任务的两张结果来回切换，预设名称、图片URL、尺寸、来源记录一致。刷新后及关闭再打开首页都从服务端恢复同一任务与所查看灯光；localStorage只存引用，图像事实重新查询。各项滑杆/并排、完整画布/原照片区域、原照弹窗通过。窄屏390×844下无横向溢出，并排自动上下排列。

实际点击下载 sunny/sunrise 的两份完整JPEG及两份区域PNG。完整JPEG与各自来源逐字节相同（含上述SHA256）。区域PNG解码像素与对应JPEG按任务canvas.validRegion裁剪完全一致，杯子当前区域为 `[442,0,838,704)`；代码读取任务记录，没有写死坐标，Node另测不同区域。文件名区分task/preset/full或photo-region。PNG不再增加有损编码，不恢复JPEG已丢失的信息。

未生成 street / 夜间街灯只显示实际输入，明确尚未生成、需要显式提交，下载禁用，无自动POST。来源说明与样例来源页面保留。浏览器显示观测 UTC `2026-10-10T04:13:05.844Z`（北京时间12:13:05.844），不是GPU等待时长；旧测速报告productDisplayTime=null未改写，本轮用独立browser-verification.json记录正式产品展示。

![正式产品：历史真实晨光结果](C:/Project/Nebius/.local/product-batch-20261010/sunrise-desktop-final.jpg)

![390像素窄屏：实际记录区域上下比较](C:/Project/Nebius/.local/product-batch-20261010/sunrise-narrow.jpg)

其他截图、实际下载验真、登记与测试日志见 `.local/product-batch-20261010`：`browser-verification.json`、`download-verification.json`、`repeated-registration.json`、`sunny-desktop.jpg`、`third-ungenerated-final.jpg`。

## 离线验证与待验收项

Python **84/84**（其中新增批量/登记测试14项，另增HTTP测试1项），Node **18/18**。`git diff --check`通过，暂存区空。覆盖列表去重、单次调度/打包、重复请求、旧单预设、错误预设、登记重复/冲突、哈希/缺文件/越界、单项损坏、部分失败、批量超时与晚到完成、过期、乱序/换照片响应、每项下载/crop像素一致。

隔离且醒目标识的 `tests/serve_batch_fixture.py` 实际浏览器验证多选显式提交、运行锁定、刷新恢复、第一项成功第二项失败、失败项不串图和成功项可下载；模拟任务只在 `.local/product-batch-20261010/fixture-tasks`，未进入生产任务目录。生产CLI配置没有启用替身的选项，模拟结果不计GPU验收。超时/过期/乱序等为自动化离线测试，并非真实GPU故障复现。测试服务已关闭。

还需要的一项真实验收：未来另行批准云预算/窗口后，从网页多选两种灯光点击一次生成，核对本次网页任务经现有执行入口只创建一个forward对象，并在整批结果取回后逐项显示、恢复和下载。本轮已证明历史真实结果正式接入与批量请求契约，未证明新的网页GPU提交成功，不追加云操作。
