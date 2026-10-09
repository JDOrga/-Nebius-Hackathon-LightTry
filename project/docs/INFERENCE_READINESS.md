# 2026-10-09 WJX 本地推理准备

## 实际核对

LAPTOP-WJX，工作路径 `C:\Project\Nebius`，产品目录 project，main / HEAD `17d1fe0c35ef8eb25aa0c3fcd6654468751e043b`。开始时 Git 工作区干净，无已有未提交修改需合并。读取 README、DEVELOPMENT、迁移/交付说明、接口、架构、依赖、验证及云流程；仓库与上级路径未发现适用 AGENTS.md / 项目专用 SKILL.md。浏览器验证使用 computer-use 技能与本机浏览器接口。

按用户确认，origin 从 JVerdL 改为 `https://github.com/JDOrga/-Nebius-Hackathon-LightTry`。HEAD 与 WJC 报告的 17d1fe0 一致；独立 demo-assets 和去历史目录依赖的代码齐全。旧交接中 71fe251/候选未提交是当时记录，不据此重做迁移。未 fetch/pull/reset、提交/推送或操作 WJC。只能比较用户提供的 WJC 信息，未远程核查其文件。

旧 docs/VALIDATION 的迁移链只完成 Tokenizer smoke；独立四素材记录另有完整 forward 真结果，云端最终验收因 Windows mask path parsing 失败，后续本地结构通过、视觉质量混合。新照片链路本轮未执行 GPU，不追认历史结果为本次成功。

## 已准备的用户流程

既有界面上：载入新照 → 选既有预设 → 显式提交 → 后端真实状态 → 本次有效 JPEG → 实际输入滑杆/并排比较 → 查看未改写原照/下载。默认不连接：新照只作本机 blob 预览，提交/下载禁用，无假阶段/百分比。

补齐任务后端、受守护 driver、单图单预设 worker。格式/大小/尺寸/解码；独立目录；原照/预处理/nonce/配置/结果身份；重复提交；失败/错误；超时、刷新和响应丢失恢复；过期/下载 allowlist；不支持运行取消且明确告知。复用 sources/state 和接口，样例独立。

普通启动仍只需 Python 3.11 标准库；任务输入处理需要已有 Pillow（离线测试 11.1.0），本轮未安装。推理兼容既有 Linux Python 3.10.21 / Torch 2.6.0+cu124 / TE 1.12，固定 commit `0f3e2dc435032ecbad654c2fc2153df85384b138`、HDR patch 与 Cosmos entry。1280×704、15 steps、seed1000、guidance0，两个模型分别加载，单预设索引 0/1/2。

只有禁用模板 inference.example.json，未创建启用的机器配置。未来复制到忽略的 inference.local.json，填 WJX 自己的本次 guard_run_directory，显式 enabled/model_license_ack 后用 `--inference-config inference.local.json` 启用。普通启动不读取该文件、不自动开机。真实路径、私钥、认证、token、pin 不入库、不进浏览器。

私有任务默认 project/.tasks，超时最多 1080 秒，结果默认可用 24 小时。过期禁用读取/下载，不自动清除原照/日志；清理由操作者在本机指定目录完成。关闭应用不等于取消已授权远端任务。

## 验证记录

- 基线产品 Python 14 / Node 8 通过。默认 Python 总自检缺 NumPy/PyYAML；改用已有 .local/review-venv，未安装依赖。仓库 20 组离线自检：19 组通过，test_running_guard 一次 Windows 临时 heartbeat PermissionError；原代码不改，单组重跑 7/7 通过。保留首次失败事实，可选 Torch/upstream skip 不代表实机通过。
- 新增后产品 Python 42 / Node 11 通过；日志在 qa/inference-20261009/python-tests.txt 与 node-tests.txt。只用合成图、独立 OfflineExecutor / transport double，覆盖完整适配器编排序列、模糊 launch、不确定状态等；无 SSH/API/GPU 调用。
- 四张独立样例重新预处理后逐像素与历史实际输入一致；新 ICC profile 有创建时间，PNG 字节不必等同历史文件，每个新任务记录自身真实哈希。
- 本机浏览器默认服务：4 样例 × 3 HDR × slider/side 共 24 次身份/尺寸检查，全部 1280×704。载入独立 640×960 合成图，切预设仍只有自身 blob、提交/下载禁用、无结果/百分比。坏 PNG 显式错误；样例下载保持原字节。
- 独立 fixture：醒目标记“离线测试替身 · 非 GPU”，通过选择器提交新图/粉色晨光，running 无百分比、取消真实提示、刷新恢复同任务；显式测试事件完成后可比较/下载。下载哈希与本次替身 result.jpg 一致，不能声称 GPU 已跑通。
- 390×844 窄屏样例上下比较完整、无横向溢出，新照片仍禁用提交/下载。替身结果过期后只留实际输入，下载禁用；损坏 PNG 提示清楚；本机浏览器下载样例 JPEG 哈希与源记录一致。
- 截图仅存忽略的 qa/inference-20261009。真实传输、本轮 GPU/品质、收费与实际停机未验证。本轮启动的普通/替身验证服务已停止；首次失败遗留的 SYNTHETIC 守护 fixture 已按其离线协议释放，不触及真实云守护。

## 下一轮最小收费验收（尚未授权）

1. 用户指定一张自有图和一个预设（候选 sunny），确认允许传输该图的预处理版本及必要白名单代码；明确含税预算上限、窗口、固定 UTC 硬截止、模型许可。历史授权/主机批准不可继承。
2. 按 docs/CLOUD 在 WJX 自己的配置上：守护先就绪 → 只读确认当前资源 → 一次显式启动 → 新 VM/IP/SSH 指纹独立核实 → 本轮 pin。产品不负责启动/重启。现有环境/权重/HDR 不足时停下，不安装/下载或换模型。
3. 把新 run 填入 inference.local.json，单任务提交一张图/一个预设。driver 自动打包、传输、安装、launch、inspect、export、download，不需每阶段重复操作。只看真实阶段。
4. 成功需原照/输入/任务/预设/配置/输出匹配，五个 G-buffer + 一个当前 HDR JPEG，进程成功、解码/尺寸/非恒定/哈希通过；验刷新、比较、下载。人眼检查主体轮廓与光照，不扩展细字/材质保真研究。
5. 成败都写本次 complete.json 请求原守护停机。超时不假装取消，未确认退出保留 uncertainty、阻止重交。另用既有 Confirm-RunningStopped.ps1 独立 API 验收 STOPPED/instances=[]，核对守护退出和防休眠释放；stop 被接受不等于已停机。

## 时间、预算与授权依据

已有四素材 performance.json：完整权重扫描 547.27 秒（约 9.1 分钟），inverse 四图五通道外层 353.62 秒，forward 四图三预设 339.17 秒，包含各一次数分钟模型加载。单图单预设减少生成次数，不免除两次加载；历史值不是当前新图测速。

估计历史 metadata 模式运行侧约 8–12 分钟，加启动/信任/传输约 3–6 分钟；默认 full 额外约 9 分钟，总约 20–27 分钟，可能超出当前工作窗口。保持现有 RUNNING 起 18 分钟工作截止、25 分钟停机触发、27 分钟核验目标，并受更早绝对截止约束；不延长守护。时间不足即失败、保留证据、停机，无自动重试/再开机。

为短窗口提取了原 fastpath 的 weights_reuse 算法，无历史目录运行依赖。可另行显式选择 `weights_mode=historical_metadata`，本地配置填历史 manifest/receipt/reference。历史与当前 manifest 的 path/size/sha256/git_blob/md5 身份一致、历史文件哈希匹配 reference、15 项历史内容检查完整为 true 才可打包。reference 去掉个人来源路径；不改写历史哈希以追认结果。云端只检查现有大小/范围，记录本轮 content_verified=false；不能发现同大小损坏/替换，不是 checksum cache hit。若用户不接受，保持 full，接受固定窗口可能超时的结果。

预算初拟参考既往单窗口 US$3 含税上限；不是本轮授权、当前报价或费用承诺。本轮未查询收费 API。实际须按下一轮已核对含税单价 × 收费时长，加启动期、存储/出口等核定；最多一次启动，25 分钟 RUNNING 触发停止（更早硬截止可缩短）。实际停止时间取 API，不能把触发时间当精确扣费上限。预算/窗口不匹配则不启动。

下一轮需确认：一张图/一个预设、允许本次上传、full 或历史 metadata 选择、金额/硬截止/许可、新目标信任、一次启动与守护停机授权。本轮停在本地准备，不预约、不启动收费窗口。
