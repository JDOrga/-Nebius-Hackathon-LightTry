# LightTry 本地可演示候选交付（2026-10-10）

候选为 main / HEAD `93c23724ec85addfcd2f5bad971aef329bd6d502` 加当前未提交差异。未提交、打标签、推送、Release 或部署；暂存区为空。只在 WJX 本地整理和验证，没有连接云机、GPU、上传、安装依赖或改动认证。现有任务仍按原时间约 2026-10-11 16:49 北京时间过期，没有修改任务状态或有效期。

## 最短启动：历史样例

代码根目录运行，已有 Python 3.11 即可，样例不需要 Pillow、Nebius 登录、GPU、云机或历史运行目录：

```powershell
python -X utf8 -B project/install_demo_assets.py "<本地素材包路径>" --assets-dir demo-assets-20261010
python -X utf8 -B project/server.py --assets-dir demo-assets-20261010
```

打开 http://127.0.0.1:8765 ，选择白蓝杯（新安装默认选中），切换晴日公园和粉色晨光，滑杆/并排比较，下载完整 JPEG 或原照片区域 PNG。Ctrl+C 停止；端口占用加 `--port 8766`。WJX 可使用现有 `.local/review-venv/Scripts/python.exe` 替代 python；WJC 用自己的既有 Python，不复制 WJX 虚拟环境。

相对 `--assets-dir demo-assets-20261010` 固定指向 `project/demo-assets-20261010/`，与当前工作目录无关；也可设置 `LIGHTTRY_DEMO_ASSETS=demo-assets-20261010`。优先级为命令参数、环境变量、默认 `project/demo-assets/`。WJX/WJC 用相同相对路径，不写个人绝对路径。新版包安装到新目录，保留旧四样例包与目录；目标存在时安装器拒绝覆盖。已安装后只运行 server 命令。

缺文件/哈希不一致会显示“样例素材缺失/校验失败”及安装指引；来源记录缺失单独报错，不回退到历史目录或其他图片。旧素材仅有20张，不能满足新版27张清单：不要补假图，使用新版包和新目录。端口占用换端口。刷新会保留样例与所查看灯光；新地址首次打开默认白蓝杯。

默认关闭检查：浏览器打开 `/api/inference`，确认 `enabled:false`（JSON 的其他字段无需复制）。普通启动不读取 `inference.local.json`，不发起开机、云连接、上传或收费执行。

## 真实生成的条件

需要操作者显式配置、既有 Pillow 和运行环境、单独批准新的收费窗口及指定上传、独立守护/截止和本轮主机确认，才可显式使用 `--inference-config inference.local.json`。模板为 `project/inference.example.json`，不是可执行的真实配置。已结束 run 的授权不延续；默认演示不用此参数。不复制私钥、令牌、known_hosts、pin、主机配置、守护状态或授权记录到 WJC。

可以用已保存记录讲解真实生成过程，不演示伪造进度、不为了演示开机。第一次需要等待模型初始化；约5.903秒是已加载模型下第二预设执行增量，包含切换、随机重置、生成和写出，不是端到端网页响应。最近网页约471.211秒（7分51秒），仅代表该次测量，不是服务承诺。结果用于灯光氛围预览，可能改变材质、文字、纹理和细节，不能替代商品实拍。任务结果会过期，长期演示使用独立样例。

## 本地素材与许可

包在代码根目录的 `.local/demo-candidate-20261010/lighttry-demo-assets-20261010-candidate.zip`；33,773,595字节（约32.21 MiB），解压素材33,922,183字节。SHA256：

`d28e2a68b77e7705a1aeb45af46345a2b0f1b0932ab2bd47736d0018e2055f40`

保留旧四组独立样例，并新增本次白蓝杯实际上传 PNG、模型输入、sunny/sunrise 原始完整 JPEG、已验收区域 PNG 和按同一记录裁剪的输入区域 PNG。共27张图片、14张完整结果。本轮不重新生成、重新编码完整结果、增强或替换；所有复制文件核对来源/目标 SHA256。原照片区域 `[442,0,838,704)`，396×704，区域结果解码 RGB 与原 JPEG 记录裁剪逐像素相同。

本次来源 task `e7ca7776b5094aba8ea1008c8421f456` / run `01725f1eeab34d899ad7ba02a9124745`。两份完整结果 SHA256：

- sunny：`080bb85e9d13cabdfefc6037276552bebba1dfb38ff43373ee0aba65053b5668`
- sunrise：`8a36f406aa5ac867ba52d11ea4eea097948e41542c9a037a125d2ba650eba1f2`

标明“已完成的真实历史生成样例；不是当前在线生成”。第三灯光本批未生成，仅输入、无结果下载，不借用别轮。任务目录、cloud-runs、云机与历史绝对路径均不是运行依赖。

白蓝杯摄影者 Aoziwe，[Wikimedia照片页](https://commons.wikimedia.org/wiki/File:White-blue_mug.jpg)、[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) 于本轮只读核对一致。页面的来源文件是 JPEG；实际网页上传的既有 PNG 为方向处理后的照片，不宣称其字节等于源站 JPEG。保留既有处理说明：方向/RGB-sRGB、LANCZOS等比缩小、灰色留白；结果为 Cosmos 生成式重打光，区域导出按记录裁剪，不暗示作者背书。照片及派生输入需遵守署名、修改说明和适用的相同方式共享要求。

精简来源为包内 `mug-source-records.json`、`ATTRIBUTION.txt`；包含生成配置（固定 upstream commit、15 steps、seed1000、guidance0、1280×704、historical_metadata未核实本轮权重内容）、HDR名称/索引/哈希、结果身份/哈希。没有完整运行日志、主机、账号配置、权重、HDR本体或G-buffer。

照片许可、HDR独立素材许可、实际模型/组件许可及结果分发分别处理。仍缺 HDR独立许可、实际模型/组件版本对应与输出条款的完整核对、结果公开分发最终结论；代码许可证不能授予素材许可。整个包与截图仅本地、Git忽略，不上传或公开分享。

## 本轮验证及边界

WJX 新隔离目录 `.local/demo-candidate-20261010/isolated/` 按 Git可见文件逐项复制；只用新版包安装到隔离 `project/demo-assets/`，未复制原项目任务、缓存、云配置或历史目录。浏览器连接127.0.0.1:8786。机器上的既有 Python 仅提供解释器；样例实际资源都在隔离目录。隔离文件哈希清单、下载记录和默认关闭证据见同级 `candidate-files.json`、`local-verification.json`。

桌面1280宽与390×844窄屏：两灯光来回切换、刷新保留晨光、1280×704完整画布、396×704区域、滑杆0/100、桌面并排/窄屏上下、窄屏无横向溢出、第三灯光输入-only均通过。实际浏览器两份完整JPEG、两份区域PNG下载，与包内文件哈希完全一致。截图来自隔离样例真实操作，非即时生成。

复用产品 Python 回归86项通过；随后针对区域下载补验 catalog12项通过（含新增一项区域字节/类型检查）。Node状态回归19项通过；主机捕获离线脚本25项、状态过渡5项、PS捕获过渡3项通过。首次 Node失败是旧测试固定三结果/首样例假设，已修正；首次以包模块运行捕获测试的导入路径不适用，按现有脚本入口运行通过。不扩展GPU验收矩阵。

WJC尚未操作。WJX隔离通过只能证明代码与素材自包含，不等于WJC实机验证。

## 变更与候选范围

进入本轮前已有：`cloud/Capture-TeaHost.ps1`、`cloud/host_capture_api.py`、`tests/test_host_capture.py` 的修改；`tests/test_host_transition.py`、`tests/test_host_transition_capture.py` 新文件；产品README/批次验收说明修改；基线、主机修复、两轮网页报告新文件。全部保留，主机捕获修复未被覆盖，不归为本轮新实现。

本轮产品整理：`project/server.py` 样例区域下载/缺结果404；`web/app.js`、`state.js` 区域选择、无第三结果、样例刷新；`web/index.html`、`about.html` 历史样例/署名与说明；`build_catalog.py`、`install_demo_assets.py` 去掉固定图片数量提示；`data/catalog.json`、`demo-package.json` 添加来源及哈希元数据；相关 `tests/test_catalog.py`、`state.test.js` 调整。没有新增模型研究、生成流程或收费功能。

本轮文档：根README、产品README、本交付说明及旧基线末尾补充。演示素材/截图/核验清单在忽略目录。执行所需最小目录为 `project/server.py`、`inference/*.py`（其中默认启动只用本地接口）、`web/*`、`data/catalog.json`、`data/demo-package.json`，安装另需 `install_demo_assets.py`；必要回归/云修复按分组保留，完整逐文件清单见本地manifest。

没有凭据、真实配置、私钥、认证、known_hosts、权重、缓存、原始日志、诊断包或媒体进入新增Git可见范围；没有读取认证文件正文。现有审计仍报告三份文档的真实资源编号和测试合成私网IP。另检出历史文档绝对路径，8份原始文档暂不建议原样公开：基线、DEVELOPMENT、INFERENCE_READINESS、PRODUCT_BATCH_ACCEPTANCE、REUSE_BENCHMARK_RESULT、WEB_BATCH_PRESTART、WEB_BATCH_RESULT、WEB_BATCH_ACCEPTANCE_RETRY2。它们保留原样作为审阅依据；逐项理由见 `public-candidate-files.json` 的 withheld，公开提交前需要去机器信息的审阅副本。合成测试10.0.0.x已核对为夹具，保留原测试。这个清单不代表当前整仓已达到公开发布条件。

开始时所有未提交内容按“既有修改”列出；本轮期间未发现范围外新的并行修改，不能将既有修复归为本轮。未执行 git add/reset/clean，未清理任何历史目录。

## WJC 最短接手

1. 审阅候选代码、必要文件清单和新版包哈希；本轮没有传输，后续仅在获准的本地交接方式中取得文件。
2. 在WJC新隔离目录放候选代码与本地包，使用上面的两条命令（新素材目录），打开8765；确认 `/api/inference` 为 `enabled:false`。
3. 选择白蓝杯，核对两灯光、刷新、完整/区域比較、JPEG/PNG下载及第三灯光无结果；哈希核对包内元数据。无需云登录或真实配置。
4. 隔离验证完成后，WJC实机正式工作目录仍需独立验证Python/端口/路径/浏览器下载权限；记录结果。不要声称WJX隔离测试替代WJC验证。

## 约2分钟提纲与截图

- 0:00–0:20：说明当前是免费的已完成真实历史样例，不会实时生成。显示照片与两个可用灯光；载入新照片只本机预览。
- 0:20–0:50：晴日/晨光切换，用滑杆显示真实输入与结果差异；第三灯光没有本次结果。
- 0:50–1:20：展示完整1280×704留白，再切原照片区域，比较材质与细节变化，说明氛围预览边界。
- 1:20–1:40：下载完整JPEG和区域PNG，说明按记录导出，没有修图。
- 1:40–2:00：刷新保留选择，说明真实模式需显式配置及另行批准收费窗口/上传、首次初始化与本次7分51秒等待，5.9秒不是端到端；任务会过期，独立样例长期可用。

五张选用截图在本地同级目录：`01-sunny-desktop.png`、`02-sunrise-desktop.png`、`03-region-desktop.png`、`04-region-narrow.png`、`05-region-export.png`。前两张对照两种真实灯光，后面覆盖局部查看、窄屏和导出；历史记录可辅助解释生成过程，不伪造即时动画。

## 建议提交分组（仅建议）

1. 主机捕获修复及原有回归：上述两个cloud文件和三个host测试；说明 `fix: keep host capture identity checks across bounded startup transitions`。
2. 本地历史样例接入及相关回归：本轮产品整理文件、两个data清单；说明 `fix: preserve verified batch results as independent local demo assets`。只提交元数据，不提交ZIP、图片或本地包。
3. 最短启动/交付说明：根/产品README、本交付说明、经审阅去机器信息后的验收摘要；说明 `docs: document offline demo handoff and verified preview limits`。原始历史报告不原样进入公开候选。

本轮停在可审阅内容。正式保存Git版本前，等待用户确认提交范围与作者身份；不自行提交或推送。
