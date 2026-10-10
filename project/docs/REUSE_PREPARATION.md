# 2026-10-09 WJX 同图复用与测速准备

本轮只修改本地代码、验证历史本地产物并运行离线测试。未启动云机、执行 GPU 推理、安装依赖、下载权重、上传或部署、提交或推送。开始时的十个已修改文件均保留；没有修改认证或停机守护。本轮新增内容不能作为 GPU 验收。

读取了接口契约、INFERENCE_READINESS、成功任务 `6d541112fa164c099d9fc06c560b464d` 的 request/receipt/configuration/两个模型日志，以及 run `dc011af5186c492d8ffd2f6342e5c07f` 的 acceptance、timing、原代码包。较新的 `.local/lighttry-e2e/local-ui-fix/verification.json` 记录自动刷新连续三次通过、396×704 原照片区域比较/PNG 导出通过、完整结果哈希未改；旧 acceptance 中刷新未通过是修复前记录，本轮未改写旧报告。

## 耗时证据与限制

旧模型日志为 UTC，下表换算为北京时间，秒级日志精度不能视为精确基准。

| 可观察边界 | 北京时间 | 粗间隔 | 能说明什么 |
|---|---|---:|---|
| inverse 设置随机种子 → 首次 Run generation | 21:36:49 → 21:41:25 | 276 秒 | 两条日志间隔；内部明细未知 |
| inverse 首次生成 → 五通道最后 Finish | 21:41:25 → 21:41:54 | 29 秒 | 含多通道间的处理/写出间隙；单通道约 8/5/6/5/5 秒 |
| forward 设置随机种子 → 首次 Run generation | 21:42:08 → 21:46:44 | 276 秒 | 初始化、数据/HDR 准备等的混合间隔 |
| forward Run → Finish | 21:46:44 → 21:46:52 | 8 秒 | 一次生成的日志区间 |

上游路径为 set_random_seed → pipeline 构建及内部网络/tokenizer 加载 → dataset/dataloader → 首次数据准备 → generate_video；forward 还包含 HDR 读取与投影。旧日志没有模型构建、权重反序列化、state_dict 赋值、设备迁移、数据准备的独立边界。因此不能将 276 秒全部归因于读权重，也不能据此认定磁盘慢、缓存失效或某个模型加载函数慢。运行记录还能确认 RUNNING 起 18 分钟工作截止、25 分钟停机触发、27 分钟核验目标；本轮不变更。

`timing.py` 使用 perf_counter，带进程/会话 ID、同机单调时间和进程内相对时间。`run_bounded` 可记录 Popen 调用前、返回 PID、已观察退出；`measured_entry.py` 记录进入上游前的进程观测、imports、pipeline 初始化、实际 `_load_model`、`_load_network`、`_load_tokenizer`、torch.load/jit.load、Module.to/cuda、首次及逐次 generate_video、各 HDR 预设、每次图像/视频写出。没有改动上游源码。

这些边界是函数调用的主机墙钟范围。network/tokenizer load 是包含赋值的复合范围；torch.load 与 jit.load 可能嵌套，不能相加；Module.to 也可能包含 dtype 转换。没有额外 CUDA synchronize，不当作纯 GPU kernel 时间或独立磁盘读取时间。只在同一机器的同次执行中比较单调时间，不跨重启比较。freshPythonChild 表示新 Python 进程，文件系统缓存冷热仍未知；pipeline_reused 明确区分同进程复用。离线替身耗时无 GPU 性能意义。

## inverse 复用规则

`reuse.py` 的键绑定：实际 1280×704 RGB 像素内容；预处理版本；画布尺寸、有效区域、灰色留白、颜色/方向/缩放算法记录；固定上游 commit、帧数、steps、seed、guidance、offload；inverse 与 tokenizer 的 manifest 身份；inverse 默认五通道顺序、normal 归一化及随机序列策略；inverse 导入的 rendering_utils 与 env_sampling 补丁身份。不同 PNG 的 ICC 创建时间可导致编码哈希不同，像素与上述语义相同仍可复用；每次仍记录并核对自身输入编码哈希。

HDR 文件、灯光名称/预设、taskId、inputId、文件名、forward-only utils_env_proj 补丁、forward 权重不进入 inverse 键。不同文件同名不会命中。preprocessingVersion 变更、区域改变、模型/配置或 inverse 相关补丁改变均失效；修改预处理算法时必须升级版本。historical_metadata 仍不能发现当前权重同大小损坏或替换，本轮没有提高其完整性承诺。

只有成功退出、五个 JPEG 完整解码、RGB/1280×704、通道唯一且同一 clip/frame、允许的非恒定检查、大小和 SHA256 全匹配后才原子发布 inverse-complete.json。残缺、无标记、运行中、来源身份未知、损坏、配置不符均拒绝。复制先校验源，后复制与复核，再发布标记；不合并残缺目录。注册表按内容键寻址，不接收浏览器路径；符号链接/目录联接、路径穿越、绝对路径与超限文件拒绝。损坏的旧缓存保留，不覆盖为“成功”。

成功历史任务已通过 `prepare_inverse_reuse.py` 与原代码包中的输入、manifest/补丁、固定 inverse argv、receipt 的五个产物哈希交叉核对，复制到新的忽略目录 `project/.inverse-cache/155868063db861b7513f9c78dd0161da123cf3542ee7b72620f6a83c01e318e5`。保留源 task/run/nonce、receipt 与代码包哈希、原编码输入哈希及五个产物哈希；没有向旧任务添加完成标记，也没有改写旧 receipt、manifest、照片或结果。重复登记再次验证已有记录。

driver 在显式授权提交之后才查询此注册表并打包已校验的五通道。worker 再验证当前输入与复用身份；forward 失败不删除 inverse 标记。确认执行端结束后，driver 可在原截止内取回失败任务的已完成阶段证据，注册已验证 inverse；若传输失败或时间不足，本地产物仍未确认，不能声称本地命中，远端原目录保留。

复用 receipt 的 processExitCodes 为 `[null, 0]`，本次 inverse 未运行；inverseReuse 保留历史来源。本机接受结果时再验证本地五通道完成标记及来源，不把历史 exit=0 伪装成本次 inverse 进程退出。原单图单灯光历史 `[0,0]` 契约继续支持。

## 有界多预设与恢复

现有上游 forward 本身支持多个 envlight_ind。新 `batch.execute` 先运行/复用 inverse，确认其子进程结束，再启动一个 forward 子进程。`measured_entry.run_forward` 在该进程中顺序调用现有 upstream demo，constructor factory 只第一次创建真正的 DiffusionRendererPipeline，后续返回同一对象。每个预设重新准备输入/HDR，但网络与 tokenizer 保留于这一次有限会话。没有长期服务，也没有两套 7B 同驻留假设。

每个 0/1/2 预设有独立 pending/running/failed/succeeded 状态、独立 attempt 目录、原子 complete 标记、HDR/forward 配置与输出哈希。最多三个、不可重复。若某项失败，停止该会话，以免继续使用可能受损的 CUDA context；已完成标记不动，后续保持 pending。恢复再次校验 inverse 和已完成 forward，跳过它们。损坏或配置改变的完成记录拒绝，不自动覆盖重跑。OS 文件锁拒绝并发同会话。

上游 inverse 只在进程开始设置全局 seed，五通道顺序消耗随机状态，保持不变。上游 forward 给 generate_video 传 seed，但 model_diffusion_renderer 的 torch.randn 使用全局随机状态；新入口在每个 forward generate 前调用原 set_random_seed(1000)，记录 `reset-before-forward-generate-v1`。这使新预设/失败恢复的随机初始化策略明确，仍不能保证不同进程、硬件、库版本或旧实现逐像素一致。旧 sunny 结果不能作为新策略的逐像素金标准。

worker request 可显式扩展 `presets`（catalog 中一到三个）与主 `preset`，逐项验证 index/HDR 内容。这是本轮准备的受守护执行入口；现有浏览器 POST 仍一次提交一个预设，没有新增自动批量付费按钮。`plan_same_photo.py` 只输出计划，不能开机/上传/提交/推理。worker `--resume` 只允许同一 request/nonce、前一执行确认停止的失败状态，仍检查当前预算和原固定截止；driver 不自动 relaunch，实际恢复由下一轮操作者在既有授权内明确执行。

界面保留同一 inputId 的各预设任务，切已生成灯光显示它自己的结果；未生成显示空结果并要求显式提交，不把上一结果贴新名称。localStorage 只保留相关 taskId，刷新 GET 验证后恢复；没有把浏览器保存的“成功结果”当服务器事实。下一次模型已经退出时，仍可能需要重新初始化 forward，复用 G-buffer 与复用运行中的模型分别说明。完整画布下载、原图、记录区域裁剪 PNG、来源信息和默认未连接行为保留。

## 离线验证

产品 Python 66 项、Node 15 项通过。新增 20 项 Python 复用/编排测试，覆盖同图、多输入/配置/预处理版本失效、无完成标记/残缺/损坏/未知来源、顺序调用次数、重复与并发提交、inverse 完成后 forward 失败、部分成功恢复、真实生产随机状态 hook、实际离线 Python 子进程启动计时、历史登记不改旧文件、阶段导出与复用 receipt 来源校验。替身明确标为 OFFLINE SYNTHETIC / NOT GPU；不能通过生产配置选用。

Node 新增同图已生成切换、未生成无结果/下载、相关任务刷新恢复、异图拒绝、过期/失败不继承下载；既有刷新重试/晚回复归属及区域测试通过。既有 HTTP 测试验证完整/裁剪下载的精确像素、路径 allowlist、私有 request/receipt/log 禁读，样例与来源校验继续通过。本轮没有新增浏览器实机验收或远端传输验收，不追认模拟完成为 GPU 成功。

日志：`.local/reuse-preparation-20261009/python-tests.txt`、`node-tests.txt`、`repository-audit.json`。仓库候选文本审计无风险记录，暂存区空，git diff --check 通过。未自动清理任何历史目录。

## 下一轮最小测速建议（未授权、未执行）

一次新预算/时间批准内，使用同一照片先选择 sunny、sunrise 两个预设。保留 historical_metadata 权重检查与 RUNNING 起 18/25/27 分钟窗口及更早绝对截止。新 run、新 task/nonce；本地 driver 配置 `reuse_inverse=false`，强制本次一次 inverse；然后一次 forward 初始化、顺序两预设。第三个预设只在用户事先批准且剩余时间足够时加入。

记录：从父进程 inverse spawn_start 到首个预设验证完成的等待；再从同会话首预设完成到第二预设完成的增量；分别列出 imports、模型构建、加载/迁移可观察范围、inverse 五通道、forward 初始化、生成、JPEG/MP4 写出与校验。另记录本机显式提交到可显示结果的传输等待，不能将服务器首文件等待等同产品可见等待。

历史约两段 276 秒加生成日志区间只能帮助估计量级，不能保证新模型初始化耗时。下一轮应先选两个预设和必要结构/归属检查，为取回证据与停机留余量；若现有 18 分钟工作窗口预计不足，缩减验证范围，或提出明确的新窗口建议待批准，不自动延长、不再启动。

可选更小范围：直接使用已登记的成功 inverse，令计划显示 inverseExecutions=0，forwardInitializations=1，顺序两预设。它可验证历史 G-buffer 的实际 forward 接口、一次初始化、逐预设状态、增量时间和 GPU 上的新随机策略；它不能验证本轮 inverse 性能、全链路首张等待、当前全量权重内容或新策略与旧结果的逐像素等价。已有 sunny 的界面切换可以纯本地验证，无须 GPU。

预算、实际收费、未来启动/上传与新目标信任另行确认。当前准备完成即停止，不自动申请或开启收费窗口。
